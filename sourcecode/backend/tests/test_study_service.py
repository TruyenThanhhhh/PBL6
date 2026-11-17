"""Unit & API integration tests for AI Study Tools model resolution and error handling."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

import app.database as db_mod  # noqa: E402
import app.services.document_service as doc_mod  # noqa: E402
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
                    f"/api/v1/workspaces/{self.workspace_id}/documents/upload?defer_metadata=true",
                    files={"file": ("sample.txt", b"Cau truc de thi JLPT N3 gom Tu vung, Ngu phap, Doc hieu va Nghe hieu.", "text/plain")},
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
                "content": '{"questions":[{"prompt":"JLPT N3 có gì?","options":["Từ vựng","Ngữ pháp","Đọc hiểu","Nghe hiểu"],"answerIndex":0,"explanation":"Theo tài liệu."}]}'
            }
        }
        quiz_resp = self.client.post(
            "/api/v1/study/quiz",
            json={"workspace_id": self.workspace_id, "question_count": 1},
            headers=self.headers,
        )
        self.assertEqual(quiz_resp.status_code, 200, quiz_resp.text)
        quiz_body = quiz_resp.json()
        self.assertFalse(quiz_body["is_mock"])
        self.assertEqual(len(quiz_body["questions"]), 1)
        self.assertEqual(fake_client.post.call_args.kwargs["json"]["model"], "qwen2.5:3b")


if __name__ == "__main__":
    unittest.main()
