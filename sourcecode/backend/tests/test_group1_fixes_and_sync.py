"""Tests for Group 1 upgrades: DOCX table extraction, Global Search versioning & Eco sync, Study profile scaling, and /chat/query alignment."""
import asyncio
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import docx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.database as db_mod  # noqa: E402
import app.services.document_service as doc_mod  # noqa: E402
from app.main import app  # noqa: E402
from app.services.hardware_profile_service import set_selected_profile_mode  # noqa: E402
from app.services.retrieval_service import invalidate_workspace_vector_cache, search_relevant_chunks  # noqa: E402
from app.services.study_service import _prepare_summary_prompts, generate_ai_summary, stream_ai_summary  # noqa: E402


def _topic_embed(texts):
    vectors = []
    for raw in texts:
        text = (raw or "").lower()
        if "phạt" in text or "hợp đồng" in text or "tiến độ" in text or "công thức" in text:
            vectors.append([1.0, 0.0, 0.0])
        elif "vắc xin" in text or "y tế" in text:
            vectors.append([0.0, 1.0, 0.0])
        else:
            vectors.append([0.0, 0.0, 1.0])
    return vectors


class _FakeStreamResponse:
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

    async def aread(self):
        return b""


class _FakePostResponse:
    def __init__(self, content: str):
        self.status_code = 200
        self.reason_phrase = "OK"
        self._content = content

    def json(self):
        return {"message": {"content": self._content}}


class _CapturingAsyncClient:
    captured_payloads = []
    post_reply = "# 📌 Tổng Quan Cốt Lõi\nNội dung tóm tắt mẫu."
    stream_lines = [
        json.dumps({"message": {"content": "# 📌 Tổng Quan\nOK"}, "done": True}, ensure_ascii=False)
    ]

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json=None, **kwargs):
        if url.endswith("/api/chat"):
            _CapturingAsyncClient.captured_payloads.append(json)
        return _FakePostResponse(_CapturingAsyncClient.post_reply)

    def stream(self, method, url, json=None, **kwargs):
        if url.endswith("/api/chat"):
            _CapturingAsyncClient.captured_payloads.append(json)
        return _FakeStreamResponse(_CapturingAsyncClient.stream_lines)


class Group1FixesAndSyncTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp_dir.name)
        self.orig_db_path = db_mod.DATABASE_PATH
        self.orig_data_dir = db_mod.DATA_DIR
        self.orig_db_upload = db_mod.UPLOAD_DIR
        self.orig_doc_upload = doc_mod.UPLOAD_DIR

        db_mod.DATA_DIR = tmp_path / "data"
        db_mod.UPLOAD_DIR = db_mod.DATA_DIR / "uploads"
        db_mod.DATABASE_PATH = db_mod.DATA_DIR / "test_group1.db"
        doc_mod.UPLOAD_DIR = db_mod.UPLOAD_DIR

        db_mod.init_db()
        set_selected_profile_mode("balanced")
        invalidate_workspace_vector_cache()
        _CapturingAsyncClient.captured_payloads = []

    def tearDown(self):
        invalidate_workspace_vector_cache()
        db_mod.DATABASE_PATH = self.orig_db_path
        db_mod.DATA_DIR = self.orig_data_dir
        db_mod.UPLOAD_DIR = self.orig_db_upload
        doc_mod.UPLOAD_DIR = self.orig_doc_upload
        self.tmp_dir.cleanup()

    def test_docx_table_extraction_preserves_order_merged_cells_and_rag(self):
        word_doc = docx.Document()
        word_doc.add_paragraph("Phần mở đầu: Quy định nghiệm thu hợp đồng.")
        tbl = word_doc.add_table(rows=3, cols=3)
        # Hàng 0 có ô gộp ngang ở cột 0..1 để kiểm tra chống lặp nội dung
        tbl.cell(0, 0).text = "Nhóm quy định"
        tbl.cell(0, 0).merge(tbl.cell(0, 1))
        tbl.cell(0, 2).text = "Chế tài"

        tbl.cell(1, 0).text = "Điều 1"
        tbl.cell(1, 1).text = "Chậm tiến độ thi công"
        tbl.cell(1, 2).text = "Phạt 5% giá trị hợp đồng"

        tbl.cell(2, 0).text = "Điều 2"
        tbl.cell(2, 1).text = "Thiếu hồ sơ hoàn công"
        tbl.cell(2, 2).text = "Tạm giữ 2% thanh toán"
        word_doc.add_paragraph("Phần kết luận: Có hiệu lực ngay khi ký.")

        buf = io.BytesIO()
        word_doc.save(buf)
        docx_bytes = buf.getvalue()

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tf:
            tf.write(docx_bytes)
            docx_path = Path(tf.name)
        try:
            pages = doc_mod.extract_text_from_file(docx_path, "docx")
        finally:
            docx_path.unlink(missing_ok=True)

        self.assertEqual(len(pages), 1)
        extracted = pages[0]["text"]
        self.assertIn("| Nhóm quy định | Chế tài |", extracted)
        self.assertEqual(extracted.count("Nhóm quy định"), 1)
        self.assertIn("| Điều 1 | Chậm tiến độ thi công | Phạt 5% giá trị hợp đồng |", extracted)
        # Đảm bảo giữ đúng thứ tự đọc tự nhiên giữa đoạn văn và bảng
        self.assertLess(extracted.find("Phần mở đầu"), extracted.find("Điều 1"))
        self.assertLess(extracted.find("Điều 2"), extracted.find("Phần kết luận"))

        # Kiểm tra chunking & tìm kiếm RAG lấy được thông tin nằm trong bảng DOCX
        with patch("app.services.document_service.embed_texts", side_effect=_topic_embed):
            with patch("app.services.retrieval_service.embed_texts", side_effect=_topic_embed):
                doc_mod.process_and_index_document("default", "hop_dong.docx", docx_bytes)
                hits = search_relevant_chunks("default", "Chậm tiến độ phạt bao nhiêu?", top_k=3)
                self.assertTrue(hits)
                self.assertIn("Phạt 5% giá trị hợp đồng", hits[0]["content"])

    @patch("app.services.workspace_ai_service.embed_texts", side_effect=_topic_embed)
    @patch("app.services.document_service.embed_texts", side_effect=_topic_embed)
    @patch("app.services.workspace_ai_service.call_ollama_json", new_callable=AsyncMock)
    def test_global_and_workspace_search_filters_out_superseded_v1_and_supports_eco_shortcut(
        self, mock_ollama, _mock_doc_emb, mock_ws_emb
    ):
        mock_ollama.return_value = {"ok": False, "error": "offline", "data": None}
        with patch.dict(os.environ, {"DISABLE_MODEL_WARMUP": "1"}):
            client = TestClient(app)
            reg = client.post(
                "/api/v1/auth/register",
                json={"email": "searchv2@example.com", "password": "Password123!", "name": "Search User"},
            )
            self.assertEqual(reg.status_code, 201, reg.text)
            headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
            ws_id = client.post(
                "/api/v1/workspaces",
                json={"name": "Kho Văn Bản Pháp Luật"},
                headers=headers,
            ).json()["workspace"]["id"]

            u1 = client.post(
                f"/api/v1/workspaces/{ws_id}/documents/upload",
                files={"file": ("nghi_dinh_cu.txt", "Quy định mức phạt chậm nộp là 1200000 đồng.".encode("utf-8"), "text/plain")},
                data={"defer_metadata": "true", "effective_date": "2026-01-01"},
                headers=headers,
            )
            self.assertEqual(u1.status_code, 200, u1.text)
            v1_id = u1.json()["document"]["document_id"]

            u2 = client.post(
                f"/api/v1/workspaces/{ws_id}/documents/upload",
                files={"file": ("nghi_dinh_moi.txt", "Quy định mới mức phạt vi phạm hành chính là 8500000 đồng.".encode("utf-8"), "text/plain")},
                data={"defer_metadata": "true", "replace_document_id": v1_id, "effective_date": "2026-11-20"},
                headers=headers,
            )
            self.assertEqual(u2.status_code, 200, u2.text)
            v2_id = u2.json()["document"]["document_id"]

            # 1. Global Search tìm cụm từ của v1 ("1200000") phải không trả về bản v1 đã lỗi thời
            old_res = client.get("/api/v1/search", params={"q": "1200000", "kind": "document"}, headers=headers)
            self.assertEqual(old_res.status_code, 200)
            self.assertEqual([h["id"] for h in old_res.json()["hits"]], [])

            # 2. Global Search tìm cụm từ của v2 ("8500000") trả đúng document v2 mới nhất
            new_res = client.get("/api/v1/search", params={"q": "8500000", "kind": "document"}, headers=headers)
            self.assertEqual(new_res.status_code, 200)
            doc_hits = new_res.json()["hits"]
            self.assertEqual([h["id"] for h in doc_hits], [v2_id])

            # 3. Chuyển sang Eco profile -> tìm kiếm Ctrl+K với khớp FTS5 rõ ràng dùng fts_shortcut và không gọi BGE-M3
            set_selected_profile_mode("eco")
            mock_ws_emb.reset_mock()
            eco_res = client.get("/api/v1/search", params={"q": "8500000", "kind": "document"}, headers=headers)
            self.assertEqual(eco_res.status_code, 200)
            self.assertEqual(eco_res.json()["search_mode"], "fts_shortcut")
            self.assertEqual([h["id"] for h in eco_res.json()["hits"]], [v2_id])
            mock_ws_emb.assert_not_called()

    def test_study_service_honors_eco_and_balanced_hardware_profiles(self):
        long_paragraphs = [
            f"Đoạn kiến thức số {idx}: Nguyên lý truyền thông đồng bộ và quản lý bộ nhớ trong hệ thống phân tán hiệu năng cao."
            for idx in range(1, 35)
        ]
        long_bytes = "\n\n".join(long_paragraphs).encode("utf-8")
        with patch("app.services.document_service.embed_texts", side_effect=_topic_embed):
            doc_info = doc_mod.process_and_index_document("default", "distributed_systems.txt", long_bytes)
        doc_id = doc_info["document_id"]

        async def run_study_checks():
            # Eco profile: giữ context tóm tắt gọn <= 1500 ký tự, num_ctx=2048, num_predict=450
            set_selected_profile_mode("eco")
            _sys_eco, user_eco, _ = _prepare_summary_prompts("default", document_id=doc_id)
            self.assertLessEqual(len(user_eco), 1650)

            with patch("app.services.study_service._ensure_ollama_chat_model", new_callable=AsyncMock) as mock_res:
                mock_res.return_value = ("qwen2.5:1.5b", None)
                with patch("app.services.study_service.httpx.AsyncClient", _CapturingAsyncClient):
                    res_eco = await generate_ai_summary("default", document_id=doc_id)
                    self.assertFalse(res_eco.get("is_mock"))
                    eco_opts = _CapturingAsyncClient.captured_payloads[-1]["options"]
                    self.assertEqual(eco_opts["num_ctx"], 2048)
                    self.assertEqual(eco_opts["num_predict"], 450)

                    # Balanced profile: mở rộng ngữ cảnh > 1800 ký tự, num_ctx=4096, num_predict=700
                    set_selected_profile_mode("balanced")
                    _sys_bal, user_bal, _ = _prepare_summary_prompts("default", document_id=doc_id)
                    self.assertGreater(len(user_bal), 2000)

                    events = []
                    async for ev in stream_ai_summary("default", document_id=doc_id):
                        events.append(ev)
                    self.assertTrue(any('"type": "done"' in e for e in events))
                    bal_opts = _CapturingAsyncClient.captured_payloads[-1]["options"]
                    self.assertEqual(bal_opts["num_ctx"], 4096)
                    self.assertEqual(bal_opts["num_predict"], 700)

                    # Performance profile: mở rộng ngữ cảnh và ngân sách token cao nhất
                    set_selected_profile_mode("performance")
                    _sys_perf, user_perf, _ = _prepare_summary_prompts("default", document_id=doc_id)
                    self.assertGreater(len(user_perf), 3200)
                    res_perf = await generate_ai_summary("default", document_id=doc_id)
                    self.assertFalse(res_perf.get("is_mock"))
                    perf_opts = _CapturingAsyncClient.captured_payloads[-1]["options"]
                    self.assertEqual(perf_opts["num_ctx"], 6144)
                    self.assertEqual(perf_opts["num_predict"], 900)

        asyncio.run(run_study_checks())

    @patch("app.services.document_service.embed_texts", side_effect=_topic_embed)
    @patch("app.services.retrieval_service.embed_texts", side_effect=_topic_embed)
    @patch("app.services.workspace_ai_service.embed_texts", side_effect=_topic_embed)
    @patch("app.services.workspace_ai_service.call_ollama_json", new_callable=AsyncMock)
    def test_sync_chat_query_executes_intent_actions_deep_reasoning_and_persists_action_json(
        self, mock_ws_llm, _m_ws, _m_ret, _m_doc
    ):
        mock_ws_llm.return_value = {"ok": False, "error": "offline", "data": None}
        with patch.dict(os.environ, {"DISABLE_MODEL_WARMUP": "1"}):
            client = TestClient(app)
            reg = client.post(
                "/api/v1/auth/register",
                json={"email": "syncchat@example.com", "password": "Password123!", "name": "Sync User"},
            )
            self.assertEqual(reg.status_code, 201, reg.text)
            headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
            ws_id = client.post("/api/v1/workspaces", json={"name": "Tài Chính Thực Hành"}, headers=headers).json()["workspace"]["id"]

            up = client.post(
                f"/api/v1/workspaces/{ws_id}/documents/upload",
                files={"file": ("cong_thuc.txt", "Công thức tính lãi suất đơn: L = P * r * t. Với P là tiền gốc, r là lãi suất năm, t là số năm.".encode("utf-8"), "text/plain")},
                data={"defer_metadata": "true"},
                headers=headers,
            )
            self.assertEqual(up.status_code, 200, up.text)

            conv = client.post(
                f"/api/v1/workspaces/{ws_id}/conversations",
                json={"title": "Test Sync Chat"},
                headers=headers,
            )
            self.assertEqual(conv.status_code, 201, conv.text)
            conv_id = conv.json()["conversation"]["id"]

            # 1. Tạo quiz qua endpoint đồng bộ /chat/query và kiểm tra action_json lưu vào DB
            fake_quiz = {
                "title": "Quiz Công thức lãi đơn",
                "questions": [
                    {
                        "id": "q1",
                        "prompt": "Công thức lãi suất đơn là gì?",
                        "options": ["L = P * r * t", "L = P + r", "L = P / t", "L = r * t"],
                        "answerIndex": 0,
                        "explanation": "Theo tài liệu.",
                    }
                ],
                "sources": [],
                "is_mock": False,
            }
            with patch("app.services.chat_action_service.generate_ai_quiz", new_callable=AsyncMock) as mock_quiz:
                mock_quiz.return_value = fake_quiz
                quiz_res = client.post(
                    "/api/v1/chat/query",
                    json={
                        "workspace_id": ws_id,
                        "conversation_id": conv_id,
                        "query": "Tạo 1 câu trắc nghiệm từ tài liệu công thức",
                    },
                    headers=headers,
                )
            self.assertEqual(quiz_res.status_code, 200, quiz_res.text)
            q_body = quiz_res.json()
            self.assertEqual(q_body["intent"], "create_quiz")
            self.assertIsNotNone(q_body.get("action_result"))
            self.assertEqual(q_body["action_result"]["action_type"], "create_quiz")
            self.assertTrue(q_body["action_result"].get("artifact_id"))

            msgs = client.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers).json()["messages"]
            asst_msgs = [m for m in msgs if m["role"] == "assistant"]
            self.assertTrue(asst_msgs)
            self.assertEqual(asst_msgs[-1]["actionArtifact"]["action_type"], "create_quiz")

            # 2. reasoning_mode="deep" kích hoạt Autonomous Reasoning qua /chat/query
            with patch("app.services.reasoning_service.call_ollama_json", new_callable=AsyncMock) as mock_plan, \
                 patch("app.services.reasoning_service.check_ollama_status", new_callable=AsyncMock) as mock_st:
                mock_st.return_value = {"running": False, "available_models": []}
                mock_plan.return_value = {"ok": False, "data": None}
                deep_res = client.post(
                    "/api/v1/chat/query",
                    json={
                        "workspace_id": ws_id,
                        "query": "Áp dụng công thức lãi suất đơn với P = 1000000, r = 0.08, t = 2",
                        "reasoning_mode": "deep",
                    },
                    headers=headers,
                )
            self.assertEqual(deep_res.status_code, 200, deep_res.text)
            d_body = deep_res.json()
            self.assertEqual(d_body["intent"], "deep_reasoning")
            self.assertTrue(d_body.get("reasoning_steps"))

            # 3. reasoning_mode="fast" giữ nhánh hỏi đáp trực tiếp thay vì ép deep reasoning
            with patch("app.services.llm_service.check_ollama_status", new_callable=AsyncMock) as mock_ol:
                mock_ol.return_value = {"running": False, "available_models": []}
                fast_res = client.post(
                    "/api/v1/chat/query",
                    json={
                        "workspace_id": ws_id,
                        "query": "Công thức lãi đơn ký hiệu những biến nào?",
                        "reasoning_mode": "fast",
                    },
                    headers=headers,
                )
            self.assertEqual(fast_res.status_code, 200, fast_res.text)
            f_body = fast_res.json()
            self.assertEqual(f_body["intent"], "rag_qa")
            self.assertEqual(f_body["retrieval"], "local")


if __name__ == "__main__":
    unittest.main()
