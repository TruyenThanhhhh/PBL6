"""Tests for Group 2 upgrades: Deep Research SSE + SQLite persistence, PDF scan OCR fallback, and Chat Vision validation/routing."""
import base64
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import pymupdf  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

import app.database as db_mod  # noqa: E402
import app.services.document_service as doc_mod  # noqa: E402
from app.main import app  # noqa: E402
from app.services.hardware_profile_service import set_selected_profile_mode  # noqa: E402
from app.services.llm_service import _resolve_model_for_chat, resolve_available_vision_model  # noqa: E402
from app.services.retrieval_service import invalidate_workspace_vector_cache  # noqa: E402


def _research_embed(texts):
    res = []
    for raw in texts:
        t = (raw or "").lower()
        if "rag" in t or "dense" in t:
            res.append([1.0, 0.0, 0.0])
        elif "bm25" in t or "fts5" in t:
            res.append([0.0, 1.0, 0.0])
        else:
            res.append([0.6, 0.6, 0.0])
    return res


class _FakeResearchStreamResponse:
    def __init__(self, lines):
        self.status_code = 200
        self.reason_phrase = "OK"
        self._lines = lines

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeResearchHttpClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, method, url, json=None, **kwargs):
        lines = [
            json_mod.dumps(
                {
                    "message": {
                        "content": (
                            "## 1. Executive Summary\nTổng hợp từ 2 tài liệu [1] và [2].\n\n"
                            "## 2. Research Question\nSo sánh Dense và BM25.\n\n"
                            "## 3. Key Findings\n- Dense nắm ngữ nghĩa [1].\n- BM25 giữ từ khóa [2].\n\n"
                            "## 4. Comparison\n| Phương pháp | Ưu điểm |\n| :--- | :--- |\n| Dense | Ngữ nghĩa [1] |\n| BM25 | Từ khóa [2] |\n\n"
                            "## 5. Contradictions\nKhông có mâu thuẫn.\n\n"
                            "## 6. Research Gaps\nThiếu benchmark thực nghiệm.\n\n"
                            "## 7. Conclusion\nCần kết hợp cả hai.\n\n"
                            "## 8. References\n1. [1] doc1.txt\n2. [2] doc2.txt"
                        )
                    },
                    "done": True,
                },
                ensure_ascii=False,
            )
        ]
        return _FakeResearchStreamResponse(lines)


json_mod = json


def _make_scanned_pdf_bytes() -> bytes:
    """Tạo file PDF chỉ chứa 1 trang ảnh bitmap (không có lớp text layer)."""
    img = Image.new("RGB", (400, 140), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 40), "DIEU 12: MUC PHAT 50 TRIEU DONG", fill=(0, 0, 0))
    img_buf = io.BytesIO()
    img.save(img_buf, format="PNG")

    pdf_doc = pymupdf.open()
    page = pdf_doc.new_page(width=400, height=140)
    page.insert_image(pymupdf.Rect(0, 0, 400, 140), stream=img_buf.getvalue())
    out = pdf_doc.tobytes()
    pdf_doc.close()
    return out


class Group2ResearchVisionOcrTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp_dir.name)
        self.orig_db_path = db_mod.DATABASE_PATH
        self.orig_data_dir = db_mod.DATA_DIR
        self.orig_db_upload = db_mod.UPLOAD_DIR
        self.orig_doc_upload = doc_mod.UPLOAD_DIR

        db_mod.DATA_DIR = tmp_path / "data"
        db_mod.UPLOAD_DIR = db_mod.DATA_DIR / "uploads"
        db_mod.DATABASE_PATH = db_mod.DATA_DIR / "test_group2.db"
        doc_mod.UPLOAD_DIR = db_mod.UPLOAD_DIR

        db_mod.init_db()
        set_selected_profile_mode("balanced")
        invalidate_workspace_vector_cache()

    def tearDown(self):
        invalidate_workspace_vector_cache()
        db_mod.DATABASE_PATH = self.orig_db_path
        db_mod.DATA_DIR = self.orig_data_dir
        db_mod.UPLOAD_DIR = self.orig_db_upload
        doc_mod.UPLOAD_DIR = self.orig_doc_upload
        self.tmp_dir.cleanup()

    @patch("app.services.document_service.embed_texts", side_effect=_research_embed)
    @patch("app.services.retrieval_service.embed_texts", side_effect=_research_embed)
    @patch("app.services.workspace_ai_service.embed_texts", side_effect=_research_embed)
    @patch("app.services.workspace_ai_service.call_ollama_json", new_callable=AsyncMock)
    def test_deep_research_stream_sync_persistence_and_user_isolation(
        self, mock_ws_llm, _m_ws, _m_ret, _m_doc
    ):
        mock_ws_llm.return_value = {"ok": False, "error": "offline", "data": None}
        with patch.dict(os.environ, {"DISABLE_MODEL_WARMUP": "1"}):
            client = TestClient(app)
            reg_a = client.post(
                "/api/v1/auth/register",
                json={"email": "resa@example.com", "password": "Password123!", "name": "Research A"},
            )
            reg_b = client.post(
                "/api/v1/auth/register",
                json={"email": "resb@example.com", "password": "Password123!", "name": "Research B"},
            )
            self.assertEqual(reg_a.status_code, 201)
            self.assertEqual(reg_b.status_code, 201)
            headers_a = {"Authorization": f"Bearer {reg_a.json()['access_token']}"}
            headers_b = {"Authorization": f"Bearer {reg_b.json()['access_token']}"}

            ws_id = client.post(
                "/api/v1/workspaces",
                json={"name": "Nghiên cứu Kiến trúc RAG"},
                headers=headers_a,
            ).json()["workspace"]["id"]

            d1 = client.post(
                f"/api/v1/workspaces/{ws_id}/documents/upload",
                files={"file": ("doc1_dense.txt", "Dense Vector Search hiểu ngữ nghĩa câu hỏi và đồng nghĩa.".encode("utf-8"), "text/plain")},
                data={"defer_metadata": "true"},
                headers=headers_a,
            ).json()["document"]["document_id"]
            d2 = client.post(
                f"/api/v1/workspaces/{ws_id}/documents/upload",
                files={"file": ("doc2_bm25.txt", "BM25 FTS5 khớp chính xác mã hiệu, tên riêng và thuật ngữ kỹ thuật.".encode("utf-8"), "text/plain")},
                data={"defer_metadata": "true"},
                headers=headers_a,
            ).json()["document"]["document_id"]

            # 1. Stream Research Synthesis với Ollama mock
            with patch("app.services.research_service.check_ollama_status", new_callable=AsyncMock) as mock_st, \
                 patch("app.services.research_service.httpx.AsyncClient", _FakeResearchHttpClient):
                mock_st.return_value = {"running": True, "available_models": ["qwen2.5:7b"]}
                resp = client.post(
                    f"/api/v1/workspaces/{ws_id}/research/stream",
                    json={
                        "title": "So sánh Dense và BM25",
                        "question": "So sánh ưu nhược điểm của Dense RAG và BM25",
                        "document_ids": [d1, d2],
                        "allow_web": False,
                        "mode": "local",
                    },
                    headers=headers_a,
                )
            self.assertEqual(resp.status_code, 200, resp.text)
            sse_text = resp.text
            self.assertIn('"type": "meta"', sse_text)
            self.assertIn('"type": "step"', sse_text)
            self.assertIn('"type": "citations"', sse_text)
            self.assertIn('"type": "done"', sse_text)
            self.assertIn("## 4. Comparison", sse_text)

            # Kiểm tra lưu trữ SQLite & danh sách project
            list_res = client.get(f"/api/v1/workspaces/{ws_id}/research", headers=headers_a)
            self.assertEqual(list_res.status_code, 200)
            projects = list_res.json()["projects"]
            self.assertEqual(len(projects), 1)
            proj = projects[0]
            self.assertEqual(proj["status"], "completed")
            self.assertFalse(proj["isMock"])
            self.assertEqual(proj["step"], 5)
            cited_docs = {c.get("documentId") for c in proj["citations"] if c.get("documentId")}
            self.assertEqual(cited_docs, {d1, d2})

            # Cô lập dữ liệu giữa các user & PATCH/DELETE
            self.assertEqual(
                client.get(f"/api/v1/workspaces/{ws_id}/research", headers=headers_b).status_code,
                404,
            )
            self.assertEqual(
                client.patch(
                    f"/api/v1/research/{proj['id']}",
                    json={"title": "Bị chặn"},
                    headers=headers_b,
                ).status_code,
                404,
            )
            patch_res = client.patch(
                f"/api/v1/research/{proj['id']}",
                json={"title": "Báo cáo RAG đã duyệt"},
                headers=headers_a,
            )
            self.assertEqual(patch_res.status_code, 200)
            self.assertEqual(patch_res.json()["project"]["title"], "Báo cáo RAG đã duyệt")

            # 2. Sync endpoint fallback minh bạch khi Ollama offline
            with patch("app.services.research_service.check_ollama_status", new_callable=AsyncMock) as mock_off:
                mock_off.return_value = {"running": False, "available_models": []}
                sync_res = client.post(
                    f"/api/v1/workspaces/{ws_id}/research",
                    json={
                        "question": "Dense và BM25 khác nhau điểm nào?",
                        "document_ids": [d1, d2],
                        "mode": "local",
                    },
                    headers=headers_a,
                )
            self.assertEqual(sync_res.status_code, 200, sync_res.text)
            sync_proj = sync_res.json()["project"]
            self.assertIn("doc1_dense.txt", sync_proj["report"])
            self.assertIn("doc2_bm25.txt", sync_proj["report"])

            del_res = client.delete(f"/api/v1/research/{proj['id']}", headers=headers_a)
            self.assertEqual(del_res.status_code, 200)

    def test_pdf_scan_ocr_fallback_extracts_scanned_pdf_and_blocks_empty_without_ocr(self):
        scanned_bytes = _make_scanned_pdf_bytes()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
            tf.write(scanned_bytes)
            pdf_path = Path(tf.name)
        try:
            # 1. Không có OCR cục bộ & Ollama Vision tắt -> báo lỗi rõ ràng hướng dẫn bật OCR/Vision
            with patch("app.services.document_service._get_rapidocr_engine", return_value=None), \
                 patch("app.services.document_service._resolve_sync_ollama_vision_model", return_value=None):
                with self.assertRaises(ValueError) as ctx:
                    doc_mod.extract_text_from_file(pdf_path, "pdf")
                self.assertIn("ảnh scan", str(ctx.exception))

            # 2. Khi Ollama Vision khả dụng -> tự động render trang PNG và trích xuất văn bản sạch
            fake_tags = MagicMock(status_code=200)
            fake_tags.json.return_value = {"models": [{"name": "qwen3-vl:2b-instruct"}]}
            fake_chat = MagicMock(status_code=200)
            fake_chat.json.return_value = {
                "message": {"content": "Điều 12: Mức phạt tối đa 50 triệu đồng."}
            }

            with patch("app.services.document_service._get_rapidocr_engine", return_value=None), \
                 patch("app.services.document_service.httpx.get", return_value=fake_tags), \
                 patch("app.services.document_service.httpx.post", return_value=fake_chat):
                pages = doc_mod.extract_text_from_file(pdf_path, "pdf")

            self.assertEqual(len(pages), 1)
            self.assertEqual(pages[0]["page"], 1)
            self.assertIn("50 triệu đồng", pages[0]["text"])
        finally:
            pdf_path.unlink(missing_ok=True)

    def test_vision_model_resolution_and_chat_stream_image_validation(self):
        # Không chọn nhầm model chỉ xử lý text khi gửi ảnh
        self.assertIsNone(resolve_available_vision_model("qwen2.5:3b", ["qwen2.5:3b", "bge-m3:latest"]))
        self.assertEqual(
            resolve_available_vision_model("qwen2.5:3b", ["qwen2.5:3b", "llava:7b"]),
            "llava:7b",
        )
        chosen, ok = _resolve_model_for_chat(
            "qwen2.5:7b",
            {"running": True, "available_models": ["qwen2.5:7b", "qwen3-vl:2b-instruct"]},
            image_base64="ZmFrZQ==",
        )
        self.assertTrue(ok)
        self.assertEqual(chosen, "qwen3-vl:2b-instruct")

        # Kiểm tra /api/v1/system/status và validation ảnh trên /api/v1/chat/stream
        tiny_png = io.BytesIO()
        Image.new("RGB", (8, 8), color=(10, 120, 110)).save(tiny_png, format="PNG")
        valid_b64 = base64.b64encode(tiny_png.getvalue()).decode("ascii")

        with patch.dict(os.environ, {"DISABLE_MODEL_WARMUP": "1"}):
            client = TestClient(app)
            reg = client.post(
                "/api/v1/auth/register",
                json={"email": "vis@example.com", "password": "Password123!", "name": "Vision User"},
            )
            self.assertEqual(reg.status_code, 201)
            headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
            ws_id = client.post("/api/v1/workspaces", json={"name": "Vision WS"}, headers=headers).json()["workspace"]["id"]

            with patch("app.api.chat.check_ollama_status", new_callable=AsyncMock) as mock_st:
                mock_st.return_value = {"running": True, "available_models": ["qwen2.5:3b", "qwen3-vl:2b-instruct"]}
                st_res = client.get("/api/v1/status")
                self.assertEqual(st_res.status_code, 200)
                self.assertTrue(st_res.json()["ollama"]["vision_available"])

            # Thiếu image_mime_type trên /chat/stream -> 422
            bad_res = client.post(
                "/api/v1/chat/stream",
                json={"workspace_id": ws_id, "query": "Đọc ảnh", "image_base64": valid_b64},
                headers=headers,
            )
            self.assertEqual(bad_res.status_code, 422)

            # Ảnh hợp lệ -> gọi stream_query nhận image_base64 đúng
            async def fake_stream(**kwargs):
                self.assertEqual(kwargs.get("image_base64"), valid_b64)
                if kwargs.get("collector") is not None:
                    kwargs["collector"]["full_answer"] = "Ảnh màu xanh lục."
                yield 'data: {"delta": "Ảnh màu xanh lục."}\n\n'
                yield "data: [DONE]\n\n"

            with patch("app.api.chat.stream_query", side_effect=fake_stream):
                ok_res = client.post(
                    "/api/v1/chat/stream",
                    json={
                        "workspace_id": ws_id,
                        "query": "Mô tả ảnh này",
                        "image_base64": valid_b64,
                        "image_mime_type": "image/png",
                    },
                    headers=headers,
                )
            self.assertEqual(ok_res.status_code, 200)
            self.assertIn("Ảnh màu xanh lục.", ok_res.text)


if __name__ == "__main__":
    unittest.main()
