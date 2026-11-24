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

    @patch("app.services.study_service.check_ollama_status", new_callable=AsyncMock)
    @patch("app.services.study_service.httpx.AsyncClient")
    def test_quiz_english_glossary_strips_boilerplate_and_honors_user_focus_and_style(
        self, mock_async_client, mock_ollama_status
    ):
        mock_ollama_status.return_value = {
            "running": True,
            "available_models": ["qwen2.5:3b"],
        }

        glossary_text = (
            "VnDoc - Tải tài liệu, văn bản pháp luật, biểu mẫu miễn phí\n"
            "Để giúp các bạn học từ vựng một cách bài bản và hiệu quả, trong bài viết sau đây VnDoc xin giới thiệu thuật ngữ âm nhạc.\n"
            "beat: nhịp trống\n"
            "harmony: hòa âm\n"
            "melody (tune): giai điệu\n"
            "amp (viết tắt của amplifier): bộ khuếch đại âm thanh\n"
            "MP3 player; máy phát nhạc MP3\n"
            "pianist: người chơi piano/nghệ sĩ dương cầm\n"
            "flautist: người thổi sáo\n"
            "cellist: người chơi vi-ô-lông xen\n"
            "violinist: nghệ sĩ vĩ cầm\n"
            "drummer: tay trống\n"
            "hymn: thánh ca\n"
            "stereo (stereo system): dàn âm thanh nổi\n"
            "Hy vọng bài viết này sẽ mang lại những kiến thức bổ ích cho bạn đọc!\n"
            "VnDoc chúc bạn học tiếng Anh hiệu quả!\n"
        )
        with patch("app.services.workspace_ai_service.embed_texts", return_value=[[0.3, 0.4, 0.5]]):
            with patch("app.services.document_service.embed_texts", return_value=[[0.3, 0.4, 0.5]]):
                up = self.client.post(
                    f"/api/v1/workspaces/{self.workspace_id}/documents/upload",
                    files={"file": ("thuat-ngu-am-nhac.txt", glossary_text.encode("utf-8"), "text/plain")},
                    data={"defer_metadata": "true"},
                    headers=self.headers,
                )
        self.assertEqual(up.status_code, 200, up.text)
        glossary_doc_id = up.json()["document"]["document_id"]

        # LLM returns 1 good question + 2 polluted/bad questions that sanitizer must reject
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "message": {
                "content": (
                    '{"questions":['
                    '{"prompt":"Thuật ngữ \\"hymn\\" trong âm nhạc có nghĩa là gì?","options":["thánh ca","nhịp trống","hòa âm","giai điệu"],"answerIndex":0,"explanation":"hymn có nghĩa là thánh ca.","sourceIndex":1},'
                    '{"prompt":"Chi tiết nào phản ánh đúng nội dung bài học?","options":["VnDoc chúc bạn học tiếng Anh hiệu quả!","nhịp trống","hòa âm","thánh ca"],"answerIndex":0,"sourceIndex":1},'
                    '{"prompt":"Câu lỗi mẫu","options":["Không đề cập trong đoạn này: pianist","thánh ca","nhịp trống","giai điệu"],"answerIndex":1,"sourceIndex":1}'
                    ']}'
                )
            }
        }
        fake_client = AsyncMock()
        fake_client.post.return_value = fake_resp
        mock_async_client.return_value.__aenter__.return_value = fake_client

        user_focus = "Tập trung hỏi các từ chỉ người chơi nhạc cụ (pianist, flautist, cellist, drummer), hỏi từ tiếng Anh sang nghĩa tiếng Việt"
        quiz_resp = self.client.post(
            "/api/v1/study/quiz",
            json={
                "workspace_id": self.workspace_id,
                "document_id": glossary_doc_id,
                "difficulty": "medium",
                "question_count": 10,
                "quiz_style": "vocabulary",
                "focus_prompt": user_focus,
            },
            headers=self.headers,
        )
        self.assertEqual(quiz_resp.status_code, 200, quiz_resp.text)
        quiz_body = quiz_resp.json()
        self.assertFalse(quiz_body["is_mock"])
        self.assertEqual(quiz_body["quiz_style"], "vocabulary")
        self.assertEqual(len(quiz_body["questions"]), 10)

        sent_payload = fake_client.post.call_args.kwargs["json"]
        user_msg_content = sent_payload["messages"][1]["content"]
        self.assertIn("YÊU CẦU RIÊNG CỦA NGƯỜI HỌC", user_msg_content)
        self.assertIn("pianist", user_msg_content)
        self.assertNotIn("VnDoc chúc bạn học tiếng Anh hiệu quả", user_msg_content)

        for q in quiz_body["questions"]:
            self.assertEqual(len(q["options"]), 4)
            self.assertNotIn("VnDoc", q["prompt"])
            self.assertNotIn("Hiragana", q["prompt"])
            self.assertNotIn("câu #", q["prompt"])
            for opt in q["options"]:
                self.assertNotIn("VnDoc", opt)
                self.assertNotIn("chúc bạn học", opt)
                self.assertNotIn("Không đề cập trong đoạn này", opt)

    @patch("app.services.study_service.check_ollama_status", new_callable=AsyncMock)
    @patch("app.services.study_service.httpx.AsyncClient")
    def test_quiz_prose_fallback_generates_clean_concept_or_cloze_questions(
        self, mock_async_client, mock_ollama_status
    ):
        mock_ollama_status.return_value = {
            "running": True,
            "available_models": ["qwen2.5:3b"],
        }

        prose_text = (
            "TCP (Transmission Control Protocol) là giao thức truyền tải hướng kết nối đảm bảo dữ liệu đến đúng thứ tự và không bị mất gói tin.\n\n"
            "UDP (User Datagram Protocol) là giao thức truyền tải không kết nối có độ trễ thấp, thường dùng cho truyền phát video trực tiếp và trò chơi trực tuyến.\n\n"
            "DNS (Domain Name System) là hệ thống phân giải tên miền giúp chuyển đổi tên miền dễ nhớ thành địa chỉ IP tương ứng trên mạng Internet.\n\n"
            "HTTP (HyperText Transfer Protocol) là giao thức truyền tải siêu văn bản hoạt động ở tầng ứng dụng giữa trình duyệt web và máy chủ.\n\n"
            "Firewall (Tường lửa) là hệ thống bảo mật mạng giám sát và kiểm soát lưu lượng ra vào dựa trên các quy tắc an ninh được thiết lập sẵn.\n"
        )
        with patch("app.services.workspace_ai_service.embed_texts", return_value=[[0.4, 0.5, 0.6]]):
            with patch("app.services.document_service.embed_texts", return_value=[[0.4, 0.5, 0.6]]):
                up = self.client.post(
                    f"/api/v1/workspaces/{self.workspace_id}/documents/upload",
                    files={"file": ("mang_may_tinh.txt", prose_text.encode("utf-8"), "text/plain")},
                    data={"defer_metadata": "true"},
                    headers=self.headers,
                )
        self.assertEqual(up.status_code, 200, up.text)
        prose_doc_id = up.json()["document"]["document_id"]

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "message": {
                "content": (
                    '{"questions":['
                    '{"prompt":"Giao thức nào đảm bảo truyền dữ liệu hướng kết nối và đúng thứ tự?","options":["TCP","UDP","DNS","HTTP"],"answerIndex":0,"explanation":"TCP đảm bảo hướng kết nối.","sourceIndex":1}'
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
                "document_id": prose_doc_id,
                "difficulty": "medium",
                "question_count": 5,
                "quiz_style": "concept",
                "focus_prompt": "So sánh các giao thức mạng TCP, UDP, DNS, HTTP",
            },
            headers=self.headers,
        )
        self.assertEqual(quiz_resp.status_code, 200, quiz_resp.text)
        quiz_body = quiz_resp.json()
        self.assertEqual(len(quiz_body["questions"]), 5)
        for q in quiz_body["questions"]:
            self.assertNotIn("câu #", q["prompt"])
            for opt in q["options"]:
                self.assertNotIn("Không đề cập trong đoạn này", opt)

    @patch("app.services.study_service.check_ollama_status", new_callable=AsyncMock)
    @patch("app.services.study_service.httpx.AsyncClient")
    def test_quiz_vietnamese_history_outline_produces_diverse_forms_and_never_chops_words(
        self, mock_async_client, mock_ollama_status
    ):
        mock_ollama_status.return_value = {
            "running": True,
            "available_models": ["qwen2.5:3b"],
        }

        history_text = (
            "[CÂY MỤC LỤC & TỔNG QUAN CẤU TRÚC TÀI LIỆU: TOM_TAT_LY_THUYET_LICH_SU_12.pdf]\n"
            "- Tổng số trang/phần: 72\n"
            "- Danh mục 22 Chương / Điều / Mục chính trong toàn bộ tài liệu:\n"
            "  - [Trang 24] Bài 13: PHONG TRÀO DÂN TỘC DÂN CHỦ Ở VIỆT NAM TỪ NĂM 1925 ĐẾN NĂM 1930\n"
            "  - [Trang 68] Bài 25: VIỆT NAM XÂY DỰNG CHỦ NGHĨA XÃ HỘI VÀ ĐẤU TRANH BẢO VỆ TỔ\n"
            "http://megabook.vn\n"
            "I. HỘI NGHỊ IAN-TA (2-1945) VÀ TRẬT TỰ HAI CỰC\n"
            "Nội dung hội nghị: Tiêu diệt tận gốc chủ nghĩa phát xít Đức và chủ nghĩa quân phiệt Nhật\n"
            "để nhanh chóng kết thúc chiến tranh.\n"
            "Ngày 24/10/1945, Liên hợp quốc chính thức được thành lập nhằm duy trì hòa bình và an ninh thế giới.\n"
            "II. CƯƠNG LĨNH CHÍNH TRỊ ĐẦU TIÊN (2-1930) VÀ LUẬN CƯƠNG CHÍNH TRỊ (10-1930)\n"
            "+ Nội dung cương lĩnh phù hợp với quan điểm chủ nghĩa Mác – Lênin và thực tế cách mạng Việt Nam.\n"
            "Chiến lược cách mạng: tiến hành tư sản dân quyền cách mạng và thổ địa cách mạng để đi tới xã hội cộng sản.\n"
            "Lực lượng cách mạng: công nông, tiểu tư sản, trí thức, lợi dụng hoặc trung lập phú nông, địa chủ và tư sản.\n"
            "Động lực cách mạng là giai cấp công nhân và nông dân trong cuộc đấu tranh giải phóng dân tộc.\n"
            "Lãnh đạo cách mạng là giai cấp công nhân với đội tiên phong là Đảng Cộng sản Đông Dương.\n"
            "Hạn chế: Không đưa ngọn cờ dân tộc lên hàng đầu mà nặng về đấu tranh giai cấp và cách mạng ruộng đất.\n"
            "III. PHONG TRÀO GIẢI PHÓNG DÂN TỘC VÀ TỔNG KHỞI NGHĨA THÁNG TÁM (1939-1945)\n"
            "Ngày 19/05/1941, Mặt trận Việt Minh được thành lập theo quyết định của Hội nghị Trung ương Đảng lần thứ 8.\n"
            "Ngày 22/12/1944, Đội Việt Nam tuyên truyền giải phóng quân được thành lập theo chỉ thị của Hồ Chí Minh.\n"
            "Ngày 02/09/1945, Chủ tịch Hồ Chí Minh đọc bản Tuyên ngôn Độc lập khai sinh nước Việt Nam Dân chủ Cộng hòa.\n"
            "IV. CUỘC KHÁNG CHIẾN CHỐNG PHÁP VÀ CHỐNG MỸ (1945-1975)\n"
            "Ngày 07/05/1954, Chiến dịch Điện Biên Phủ toàn thắng đập tan hoàn toàn kế hoạch Na-va của thực dân Pháp.\n"
            "Ngày 27/01/1973, Hiệp định Paris về chấm dứt chiến tranh và lập lại hòa bình ở Việt Nam được ký kết.\n"
            "Ý nghĩa: Mở ra kỷ nguyên độc lập, tự do, thống nhất đất nước và cả nước đi lên chủ nghĩa xã hội.\n"
            "V. ĐƯỜNG LỐI ĐỔI MỚI ĐẤT NƯỚC (1986-2000)\n"
            "Đổi mới kinh tế là xóa bỏ cơ chế quản lý tập trung bao cấp và phát triển kinh tế hàng hóa nhiều thành phần.\n"
            "Đổi mới chính trị là xây dựng Nhà nước pháp quyền xã hội chủ nghĩa của dân, do dân và vì dân.\n"
        )

        with patch("app.services.workspace_ai_service.embed_texts", return_value=[[0.5, 0.6, 0.7]]):
            with patch("app.services.document_service.embed_texts", return_value=[[0.5, 0.6, 0.7]]):
                up = self.client.post(
                    f"/api/v1/workspaces/{self.workspace_id}/documents/upload",
                    files={"file": ("TOM_TAT_LY_THUYET_LICH_SU_12.txt", history_text.encode("utf-8"), "text/plain")},
                    data={"defer_metadata": "true"},
                    headers=self.headers,
                )
        self.assertEqual(up.status_code, 200, up.text)
        hist_doc_id = up.json()["document"]["document_id"]

        # Giả lập LLM chỉ trả về 1 câu rồi dừng/lỗi ở lô tiếp theo để kiểm chứng toàn diện bộ sinh đa dạng dự phòng
        fake_resp_1 = MagicMock()
        fake_resp_1.status_code = 200
        fake_resp_1.json.return_value = {
            "message": {
                "content": (
                    '{"questions":['
                    '{"prompt":"Hội nghị Trung ương lần thứ 8 (5/1941) đã quyết định thành lập tổ chức mặt trận nào?","options":["Mặt trận Việt Minh","Mặt trận Dân chủ Đông Dương","Mặt trận Liên Việt","Mặt trận Tổ quốc Việt Nam"],"answerIndex":0,"explanation":"Ngày 19/05/1941 thành lập Mặt trận Việt Minh.","sourceIndex":1}'
                    ']}'
                )
            }
        }
        fake_client = AsyncMock()
        fake_client.post.side_effect = [fake_resp_1, RuntimeError("simulated timeout"), RuntimeError("simulated timeout")]
        mock_async_client.return_value.__aenter__.return_value = fake_client

        quiz_resp = self.client.post(
            "/api/v1/study/quiz",
            json={
                "workspace_id": self.workspace_id,
                "document_id": hist_doc_id,
                "difficulty": "medium",
                "question_count": 10,
                "quiz_style": "auto",
                "focus_prompt": "Bám sát các định nghĩa, khái niệm và luận điểm cốt lõi trong bài",
            },
            headers=self.headers,
        )
        self.assertEqual(quiz_resp.status_code, 200, quiz_resp.text)
        quiz_body = quiz_resp.json()
        questions = quiz_body["questions"]
        self.assertEqual(len(questions), 10)

        # Kiểm tra đa dạng nhiều dạng câu hỏi (không bị dồn 100% vào điền chỗ trống '[...]')
        cloze_count = sum(1 for q in questions if "[...]" in q["prompt"])
        self.assertLessEqual(cloze_count, 4, f"Quá nhiều câu điền khuyết 1 form: {cloze_count}/10")

        # Kiểm tra đáp án đúng phân bổ đều qua nhiều vị trí A/B/C/D (không dồn 1 đáp án cố định)
        answer_positions = {q["answerIndex"] for q in questions}
        self.assertGreaterEqual(len(answer_positions), 3, f"Đáp án bị dồn cục vào vị trí: {answer_positions}")

        # Kiểm tra tuyệt đối không có mảnh từ tiếng Việt bị cắt cụt hay rác watermark/bullet
        forbidden_opts = {"nam", "trung", "ban", "lan", "ngay", "thanh", "bắc", "đông", "tây"}
        for q in questions:
            self.assertEqual(len(q["options"]), 4)
            self.assertNotIn("megabook", q["prompt"].lower())
            self.assertNotIn("[trang ", q["prompt"].lower())
            self.assertNotIn("danh mục 22 chương", q["prompt"].lower())
            self.assertNotIn('"+ ', q["prompt"])
            for opt in q["options"]:
                self.assertNotIn("megabook", opt.lower())
                self.assertNotIn("[trang ", opt.lower())
                self.assertNotIn("không đề cập trong đoạn này", opt.lower())
                self.assertFalse(opt.rstrip().endswith((",", "-", "–")), f"Phương án bị cắt cụt giữa câu: {opt}")
                self.assertNotIn(
                    opt.strip().lower(),
                    forbidden_opts,
                    f"Phát hiện phương án bị cắt cụt từ tiếng Việt '{opt}' trong câu: {q['prompt']}",
                )

    @patch("app.services.study_service.check_ollama_status", new_callable=AsyncMock)
    @patch("app.services.study_service.httpx.AsyncClient")
    def test_quiz_ipa_english_dictionary_handles_colons_inside_ipa_and_strips_contact_headers(
        self, mock_async_client, mock_ollama_status
    ):
        mock_ollama_status.return_value = {
            "running": True,
            "available_models": ["qwen2.5:3b"],
        }

        ipa_dict_text = (
            "Anh ngữ Ms Hoa| Ms Hoa TOEIC & Ms Hoa Giao tiếp\n"
            "Website: mshoagiaotiep.com | anhngumshoa.com\n"
            "| Hotline: 093 448 96 66| 093 448 96 66\n"
            "Fanpage: https://www.facebook.com/aland.edu.vn/\n\n"
            "3000 TỪ TIẾNG ANH THÔNG DỤNG NHẤT\n"
            "(PHIÊN ÂM VÀ GIẢI NGHĨA)\n\n"
            "attorney n. (especially NAmE) /ə'tə:ni/ người được ủy quyền\n"
            "concert n. /kən'sə:t/ buổi hòa nhạc\n"
            "author n. /'ɔ:θə/ tác giả\n"
            "even adv., adj. /'i:vn/ ngay cả, thậm chí, bằng phẳng\n"
            "assume v. /ə'sju:m/ mang, khoác, cho rằng\n"
            "assure v. /ə'ʃuə/ đảm bảo, cam đoan\n"
            "atmosphere n. /'ætməsfiə/ khí quyển\n"
            "automatic adj. /,ɔ:tə'mætik/ tự động\n"
            "autumn n. /'ɔ:təm/ mùa thu (US: fall)\n"
            "ceremony n. /'seriməni/ nghi lễ, buổi lễ\n"
        )
        with patch("app.services.workspace_ai_service.embed_texts", return_value=[[0.2, 0.3, 0.4]]):
            with patch("app.services.document_service.embed_texts", return_value=[[0.2, 0.3, 0.4]]):
                up = self.client.post(
                    f"/api/v1/workspaces/{self.workspace_id}/documents/upload",
                    files={"file": ("3000_tu_tieng_anh.txt", ipa_dict_text.encode("utf-8"), "text/plain")},
                    data={"defer_metadata": "true"},
                    headers=self.headers,
                )
        self.assertEqual(up.status_code, 200, up.text)
        dict_doc_id = up.json()["document"]["document_id"]

        # Giả lập LLM trả về 0 câu để kiểm tra toàn bộ pipeline trích xuất từ điển IPA + fallback + bộ lọc chất lượng
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {"message": {"content": '{"questions":[]}'}}
        fake_client = AsyncMock()
        fake_client.post.return_value = fake_resp
        mock_async_client.return_value.__aenter__.return_value = fake_client

        quiz_resp = self.client.post(
            "/api/v1/study/quiz",
            json={
                "workspace_id": self.workspace_id,
                "document_id": dict_doc_id,
                "difficulty": "hard",
                "question_count": 8,
                "focus_prompt": "Bám sát các định nghĩa, khái niệm và luận điểm cốt lõi trong bài",
                "quiz_style": "auto",
            },
            headers=self.headers,
        )
        self.assertEqual(quiz_resp.status_code, 200, quiz_resp.text)
        questions = quiz_resp.json()["questions"]
        self.assertEqual(len(questions), 8)

        # Phân bổ đáp án đều qua A/B/C/D
        answer_positions = {q["answerIndex"] for q in questions}
        self.assertEqual(answer_positions, {0, 1, 2, 3})

        for q in questions:
            self.assertEqual(len(q["options"]), 4)
            prompt_l = q["prompt"].lower()
            self.assertNotIn("ni/", prompt_l)
            self.assertNotIn("hotline", prompt_l)
            self.assertNotIn("mshoagiaotiep", prompt_l)
            self.assertNotIn("facebook.com", prompt_l)
            for opt in q["options"]:
                # Không bao giờ bị cắt dở IPA như '/ə\'tə' hay '/kən\'sə' hay '/\'i'
                self.assertEqual(
                    opt.count("/") % 2,
                    0,
                    f"Phát hiện dấu phiên âm IPA bị cắt dở trong phương án: {opt}",
                )
                self.assertNotIn("hotline", opt.lower())
                self.assertNotIn("mshoa", opt.lower())
                self.assertNotIn("ni/ người", opt.lower())
                self.assertFalse(opt.lower().startswith("ni/"))


if __name__ == "__main__":
    unittest.main()
