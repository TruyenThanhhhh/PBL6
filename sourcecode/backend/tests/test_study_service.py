"""Unit & API integration tests for AI Study Tools model resolution and error handling."""
import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.database as db_mod  # noqa: E402
import app.services.document_service as doc_mod  # noqa: E402
from app.api.study import _run_until_disconnect  # noqa: E402
from app.main import app  # noqa: E402


class StudyServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp_dir.name)
        self.orig_db_path = db_mod.DATABASE_PATH
        self.orig_data_dir = db_mod.DATA_DIR
        self.orig_db_upload = db_mod.UPLOAD_DIR
        self.orig_doc_upload = doc_mod.UPLOAD_DIR

        db_mod.DATA_DIR = tmp_path / "data"
        db_mod.UPLOAD_DIR = db_mod.DATA_DIR / "uploads"
        db_mod.DATABASE_PATH = db_mod.DATA_DIR / "test_study.db"
        doc_mod.UPLOAD_DIR = db_mod.UPLOAD_DIR

        db_mod.init_db()
        self.client = TestClient(app)

        reg = self.client.post(
            "/api/v1/auth/register",
            json={"email": "study@example.com", "password": "Password123!", "name": "Study User"},
        )
        self.assertEqual(reg.status_code, 201, reg.text)
        self.headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

        ws = self.client.post("/api/v1/workspaces", json={"name": "Workspace Test"}, headers=self.headers)
        self.assertEqual(ws.status_code, 201, ws.text)
        self.workspace_id = ws.json()["workspace"]["id"]

        with patch("app.services.workspace_ai_service.embed_texts", return_value=[[0.1, 0.2, 0.3]]):
            with patch("app.services.document_service.embed_texts", return_value=[[0.1, 0.2, 0.3]]):
                up = self.client.post(
                    f"/api/v1/workspaces/{self.workspace_id}/documents/upload",
                    files={"file": ("sample.txt", b"Cau truc de thi JLPT N3 gom Tu vung, Ngu phap, Doc hieu va Nghe hieu.", "text/plain")},
                    data={"defer_metadata": "true"},
                    headers=self.headers,
                )
        self.assertEqual(up.status_code, 200, up.text)

    def tearDown(self):
        db_mod.DATABASE_PATH = self.orig_db_path
        db_mod.DATA_DIR = self.orig_data_dir
        db_mod.UPLOAD_DIR = self.orig_db_upload
        doc_mod.UPLOAD_DIR = self.orig_doc_upload
        self.tmp_dir.cleanup()

    @patch("app.services.study_service.check_ollama_status", new_callable=AsyncMock)
    @patch("app.services.study_service.httpx.AsyncClient")
    def test_summary_falls_back_to_installed_chat_model(self, mock_async_client, mock_ollama_status):
        mock_ollama_status.return_value = {
            "running": True,
            "available_models": ["qwen2.5:3b", "qwen2.5"],
        }
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {"message": {"content": "# Tổng Quan\nĐề thi JLPT N3 gồm 3 phần."}}

        fake_client = AsyncMock()
        fake_client.post.return_value = fake_resp
        mock_async_client.return_value.__aenter__.return_value = fake_client

        resp = self.client.post(
            "/api/v1/study/summary",
            json={"workspace_id": self.workspace_id},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertFalse(body["is_mock"])
        self.assertIn("Tổng Quan", body["markdown"])
        self.assertNotIn("error", body)

        sent_payload = fake_client.post.call_args.kwargs["json"]
        self.assertEqual(sent_payload["model"], "qwen2.5:3b")

    @patch("app.services.study_service.check_ollama_status", new_callable=AsyncMock)
    @patch("app.services.study_service.httpx.AsyncClient")
    def test_summary_returns_clear_error_when_only_embedding_model_installed(
        self, mock_async_client, mock_ollama_status
    ):
        mock_ollama_status.return_value = {
            "running": True,
            "available_models": ["nomic-embed-text:latest", "nomic-embed-text"],
        }

        resp = self.client.post(
            "/api/v1/study/summary",
            json={"workspace_id": self.workspace_id},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertTrue(body["is_mock"])
        self.assertTrue(body.get("error"))
        self.assertEqual(body["markdown"], "")
        mock_async_client.return_value.__aenter__.return_value.post.assert_not_called()

    @patch("app.services.study_service.check_ollama_status", new_callable=AsyncMock)
    @patch("app.services.study_service.httpx.AsyncClient")
    def test_summary_extracts_ollama_http_error_detail(self, mock_async_client, mock_ollama_status):
        mock_ollama_status.return_value = {
            "running": True,
            "available_models": ["qwen2.5:3b"],
        }
        fake_resp = MagicMock()
        fake_resp.status_code = 404
        fake_resp.reason_phrase = "Not Found"
        fake_resp.json.return_value = {"error": "model 'broken' not found"}

        fake_client = AsyncMock()
        fake_client.post.return_value = fake_resp
        mock_async_client.return_value.__aenter__.return_value = fake_client

        resp = self.client.post(
            "/api/v1/study/summary",
            json={"workspace_id": self.workspace_id},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertTrue(body["is_mock"])
        self.assertEqual(body["markdown"], "")
        self.assertIn("404", body["error"])
        self.assertIn("not found", body["error"])

    @patch("app.services.study_service.check_ollama_status", new_callable=AsyncMock)
    @patch("app.services.study_service.httpx.AsyncClient")
    def test_notes_and_quiz_also_resolve_available_chat_model(self, mock_async_client, mock_ollama_status):
        mock_ollama_status.return_value = {
            "running": True,
            "available_models": ["qwen2.5:3b"],
        }
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {"message": {"content": "# Ghi chú\nNội dung ngắn."}}

        fake_client = AsyncMock()
        fake_client.post.return_value = fake_resp
        mock_async_client.return_value.__aenter__.return_value = fake_client

        resp = self.client.post(
            "/api/v1/study/notes",
            json={"workspace_id": self.workspace_id},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertFalse(body["is_mock"])
        self.assertIn("Ghi chú", body["markdown"])
        self.assertEqual(fake_client.post.call_args.kwargs["json"]["model"], "qwen2.5:3b")

        fake_resp.json.return_value = {
            "message": {
                "content": '{"questions":[{"prompt":"JLPT N3 có gì?","options":["Từ vựng","Ngữ pháp","Đọc hiểu","Nghe hiểu"],"answerIndex":0,"explanation":"Theo tài liệu.","sourceIndex":1}]}'
            }
        }
        quiz_resp = self.client.post(
            "/api/v1/study/quiz",
            json={"workspace_id": self.workspace_id, "question_count": 20, "focus_prompt": "JLPT N3"},
            headers=self.headers,
        )
        self.assertEqual(quiz_resp.status_code, 200, quiz_resp.text)
        quiz_body = quiz_resp.json()
        self.assertFalse(quiz_body["is_mock"])
        self.assertEqual(len(quiz_body["questions"]), 1)
        self.assertEqual(quiz_body["questions"][0]["citation"]["documentName"], "sample.txt")
        self.assertEqual(quiz_body["questions"][0]["citation"]["pageNumber"], 1)
        self.assertTrue(quiz_body["questions"][0]["citation"]["documentId"])
        self.assertEqual(fake_client.post.call_args.kwargs["json"]["model"], "qwen2.5:3b")

    def test_run_until_disconnect_cancels_task_when_client_aborts(self):
        cancelled = False

        async def slow_summary():
            nonlocal cancelled
            try:
                await asyncio.sleep(5)
                return {"title": "done", "markdown": "ok", "is_mock": False}
            except asyncio.CancelledError:
                cancelled = True
                raise

        fake_request = MagicMock()
        fake_request.is_disconnected = AsyncMock(side_effect=[False, True])

        async def run_case():
            with self.assertRaises(HTTPException) as ctx:
                await _run_until_disconnect(fake_request, slow_summary())
            self.assertEqual(ctx.exception.status_code, 499)

        asyncio.run(run_case())
        self.assertTrue(cancelled)

    @patch("app.services.study_service.check_ollama_status", new_callable=AsyncMock)
    @patch("app.services.study_service.httpx.AsyncClient")
    def test_quiz_returns_exact_requested_count_and_respects_japanese_vocab_scope(
        self, mock_async_client, mock_ollama_status
    ):
        mock_ollama_status.return_value = {
            "running": True,
            "available_models": ["qwen2.5:3b"],
        }

        vocab_text = (
            "1 | 男性 | だんせい | đàn ông | 61 | 約束 | やくそく | lời hứa | 121 | 渇く | かわく | khát\n"
            "2 | 女性 | じょせい | phụ nữ | 62 | 読書 | どくしょ | đọc sách | 122 | 影響 | えいきょう | ảnh hưởng\n"
            "3 | 高齢 | こうれい | cao tuổi | 63 | 遠慮 | えんりょ | ngại ngần | 123 | 効果 | こうか | hiệu quả\n"
            "4 | 先輩 | せんぱい | tiền bối | 64 | 我慢 | がまん | chịu đựng | 124 | 希望 | きぼう | hi vọng\n"
            "5 | 目上 | めうえ | bề trên | 65 | 迷惑 | めわく | làm phiền | 125 | 検査 | けんさ | kiểm tra\n"
        )
        with patch("app.services.workspace_ai_service.embed_texts", return_value=[[0.2, 0.3, 0.4]]):
            with patch("app.services.document_service.embed_texts", return_value=[[0.2, 0.3, 0.4]]):
                up = self.client.post(
                    f"/api/v1/workspaces/{self.workspace_id}/documents/upload",
                    files={"file": ("mimikara_n3_vocab.txt", vocab_text.encode("utf-8"), "text/plain")},
                    data={"defer_metadata": "true"},
                    headers=self.headers,
                )
        self.assertEqual(up.status_code, 200, up.text)
        vocab_doc_id = up.json()["document"]["document_id"]

        # Model chỉ trả về 2 câu với key 'quizQuestions'/'question'/'answer'
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "message": {
                "content": (
                    '{"quizQuestions":['
                    '{"question":"Từ 「男性」 (だんせい) có nghĩa là gì?","options":["đàn ông","phụ nữ","lời hứa","cao tuổi"],"answer":"đàn ông","sourceIndex":1},'
                    '{"question":"Từ 「約束」 (やくそく) có nghĩa là gì?","options":["khát","lời hứa","tiền bối","làm phiền"],"answer":"lời hứa","sourceIndex":1}'
                    ']}'
                )
            }
        }
        fake_client = AsyncMock()
        fake_client.post.return_value = fake_resp
        mock_async_client.return_value.__aenter__.return_value = fake_client

        quiz_resp = self.client.post(
            "/api/v1/study/quiz",
            json={
                "workspace_id": self.workspace_id,
                "document_id": vocab_doc_id,
                "difficulty": "medium",
                "question_count": 10,
                "focus_prompt": "test",
            },
            headers=self.headers,
        )
        self.assertEqual(quiz_resp.status_code, 200, quiz_resp.text)
        quiz_body = quiz_resp.json()
        self.assertFalse(quiz_body["is_mock"])
        self.assertEqual(len(quiz_body["questions"]), 10)
        for q in quiz_body["questions"]:
            self.assertEqual(len(q["options"]), 4)
            self.assertEqual(q["citation"]["documentId"], vocab_doc_id)
            self.assertEqual(q["citation"]["documentName"], "mimikara_n3_vocab.txt")
            self.assertNotIn("Hybrid RAG", q["prompt"])

    @patch("app.services.study_service.check_ollama_status", new_callable=AsyncMock)
    @patch("app.services.study_service.httpx.AsyncClient")
    def test_flashcards_supports_custom_count_style_examples_and_citations(
        self, mock_async_client, mock_ollama_status
    ):
        mock_ollama_status.return_value = {
            "running": True,
            "available_models": ["qwen2.5:3b"],
        }

        vocab_text = (
            "1 | 男性 | だんせい | đàn ông | 61 | 約束 | やくそく | lời hứa | 121 | 渇く | かわく | khát\n"
            "2 | 女性 | じょせい | phụ nữ | 62 | 読書 | どくしょ | đọc sách | 122 | 影響 | えいきょう | ảnh hưởng\n"
            "3 | 高齢 | こうれい | cao tuổi | 63 | 遠慮 | えんりょ | ngại ngần | 123 | 効果 | こうか | hiệu quả\n"
            "4 | 先輩 | せんぱい | tiền bối | 64 | 我慢 | がまん | chịu đựng | 124 | 希望 | きぼう | hi vọng\n"
            "5 | 目上 | めうえ | bề trên | 65 | 迷惑 | めわく | làm phiền | 125 | 検査 | けんさ | kiểm tra\n"
            "6 | 上司 | じょうし | cấp trên | 66 | 印象 | いんしょう | ấn tượng | 126 | 進む | すすむ | tiến lên\n"
        )
        with patch("app.services.workspace_ai_service.embed_texts", return_value=[[0.2, 0.3, 0.4]]):
            with patch("app.services.document_service.embed_texts", return_value=[[0.2, 0.3, 0.4]]):
                up = self.client.post(
                    f"/api/v1/workspaces/{self.workspace_id}/documents/upload",
                    files={"file": ("mimikara_n3_vocab.txt", vocab_text.encode("utf-8"), "text/plain")},
                    data={"defer_metadata": "true"},
                    headers=self.headers,
                )
        self.assertEqual(up.status_code, 200, up.text)
        vocab_doc_id = up.json()["document"]["document_id"]

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "message": {
                "content": (
                    '{"flashcards":['
                    '{"front":"男性 (だんせい)","back":"đàn ông","example":"Ví dụ: 男性社員","sourceIndex":1},'
                    '{"front":"約束 (やくそく)","back":"lời hứa","example":"Ví dụ: 約束を守る","sourceIndex":1}'
                    ']}'
                )
            }
        }
        fake_client = AsyncMock()
        fake_client.post.return_value = fake_resp
        mock_async_client.return_value.__aenter__.return_value = fake_client

        fc_resp = self.client.post(
            "/api/v1/study/flashcards",
            json={
                "workspace_id": self.workspace_id,
                "document_id": vocab_doc_id,
                "count": 15,
                "card_style": "vocabulary",
                "focus_prompt": "Từ vựng N3 – Bài 1",
            },
            headers=self.headers,
        )
        self.assertEqual(fc_resp.status_code, 200, fc_resp.text)
        body = fc_resp.json()
        self.assertFalse(body["is_mock"])
        self.assertEqual(body["card_style"], "vocabulary")
        self.assertIn("Từ vựng N3", body["title"])
        self.assertEqual(len(body["flashcards"]), 15)
        for card in body["flashcards"]:
            self.assertTrue(card["front"])
            self.assertTrue(card["back"])
            self.assertTrue(card.get("example"))
            self.assertEqual(card["citation"]["documentId"], vocab_doc_id)
            self.assertEqual(card["citation"]["documentName"], "mimikara_n3_vocab.txt")


if __name__ == "__main__":
    unittest.main()
