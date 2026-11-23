"""Tests for Stage 1: hardware profiles (Eco/Balanced/Performance), Vector Matrix Cache, early chitchat bypass, and SSE progress streaming."""
import asyncio
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

from fastapi.testclient import TestClient  # noqa: E402

import app.database as db_mod  # noqa: E402
import app.services.document_service as doc_mod  # noqa: E402
from app.main import app  # noqa: E402
from app.services.ai_router import answer_query, stream_query  # noqa: E402
from app.services.hardware_profile_service import (  # noqa: E402
    recommend_profile_id,
    set_selected_profile_mode,
)
from app.services.retrieval_service import (  # noqa: E402
    invalidate_workspace_vector_cache,
    search_relevant_chunks,
)


def _topic_embed(texts):
    res = []
    for t in texts:
        low = (t or "").lower()
        if "rag" in low or "hybrid" in low:
            res.append([1.0, 0.0, 0.0])
        elif "pháp luật" in low or "nghị định" in low:
            res.append([0.0, 1.0, 0.0])
        else:
            res.append([0.1, 0.1, 1.0])
    return res


class PerformanceAndEcoProfileTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp_dir.name)
        self.orig_db_path = db_mod.DATABASE_PATH
        self.orig_data_dir = db_mod.DATA_DIR
        self.orig_db_upload = db_mod.UPLOAD_DIR
        self.orig_doc_upload = doc_mod.UPLOAD_DIR

        db_mod.DATA_DIR = tmp_path / "data"
        db_mod.UPLOAD_DIR = db_mod.DATA_DIR / "uploads"
        db_mod.DATABASE_PATH = db_mod.DATA_DIR / "test_perf.db"
        doc_mod.UPLOAD_DIR = db_mod.UPLOAD_DIR
        db_mod.init_db()
        invalidate_workspace_vector_cache()

    def tearDown(self):
        invalidate_workspace_vector_cache()
        db_mod.DATABASE_PATH = self.orig_db_path
        db_mod.DATA_DIR = self.orig_data_dir
        db_mod.UPLOAD_DIR = self.orig_db_upload
        doc_mod.UPLOAD_DIR = self.orig_doc_upload
        self.tmp_dir.cleanup()

    def test_hardware_profile_recommendations_match_machine_tier(self):
        self.assertEqual(
            recommend_profile_id({"cpu_count": 4, "total_ram_gb": 8.0, "gpu_vram_mb": 0}),
            "eco",
        )
        self.assertEqual(
            recommend_profile_id({"cpu_count": 12, "total_ram_gb": 16.0, "gpu_vram_mb": 4096}),
            "balanced",
        )
        self.assertEqual(
            recommend_profile_id({"cpu_count": 16, "total_ram_gb": 32.0, "gpu_vram_mb": 8192}),
            "performance",
        )

    @patch("app.services.reranker_service._get_model")
    @patch("app.services.retrieval_service.embed_texts", side_effect=_topic_embed)
    @patch("app.services.document_service.embed_texts", side_effect=_topic_embed)
    def test_eco_mode_skips_reranker_and_uses_fts_shortcut(self, _m_doc, mock_ret_emb, mock_rerank_model):
        set_selected_profile_mode("eco")
        doc_mod.process_and_index_document(
            "default",
            "rag_notes.txt",
            (
                "Hybrid RAG kết hợp tìm kiếm từ khóa BM25 và Dense Vector.\n"
                + ("Đoạn kiến thức về Hybrid RAG và tối ưu chỉ mục.\n" * 6)
            ).encode("utf-8"),
        )
        chunks = search_relevant_chunks("default", "Hybrid RAG kết hợp BM25", top_k=3)
        self.assertTrue(chunks)
        # Eco FTS-first shortcut không gọi BGE-M3 query embedding khi FTS5 đã đủ kết quả
        mock_ret_emb.assert_not_called()
        # Eco tắt Cross-Encoder Reranker hoàn toàn
        mock_rerank_model.assert_not_called()

    @patch("app.services.retrieval_service.rerank_documents", side_effect=lambda q, docs, k, **kw: docs[:k])
    @patch("app.services.retrieval_service.embed_texts", side_effect=_topic_embed)
    @patch("app.services.document_service.embed_texts", side_effect=_topic_embed)
    def test_vector_matrix_cache_handles_mixed_dims_and_invalidation(self, _m_doc, _m_ret, _m_rerank):
        set_selected_profile_mode("balanced")
        doc = doc_mod.process_and_index_document(
            "default",
            "rag_guide.txt",
            b"Hybrid RAG giup truy xuat tai lieu chinh xac hon.\n" * 3,
        )
        # Chèn thêm 1 chunk có chiều vector khác (5 dims) để kiểm tra không lỗi aligned shapes
        conn = db_mod.get_db_connection()
        try:
            conn.execute(
                "INSERT INTO document_chunks (id, document_id, workspace_id, chunk_index, page_number, token_count, content) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("c_odd", doc["document_id"], "default", 99, 1, 5, "Pháp luật quy định mới."),
            )
            from app.config import EMBEDDING_MODEL
            from app.services.embedding_service import pack_vector
            conn.execute(
                "INSERT INTO chunk_embeddings (chunk_id, model, dimensions, vector) VALUES (?, ?, ?, ?)",
                ("c_odd", EMBEDDING_MODEL, 5, pack_vector([0.1, 0.2, 0.3, 0.4, 0.5])),
            )
            conn.commit()
        finally:
            conn.close()

        hits1 = search_relevant_chunks("default", "Hybrid RAG", top_k=4)
        hits2 = search_relevant_chunks("default", "Hybrid RAG", top_k=4)
        self.assertTrue(hits1)
        self.assertEqual([h["chunk_id"] for h in hits1], [h["chunk_id"] for h in hits2])

    def test_chitchat_skips_retrieval_completely_and_stream_emits_progress(self):
        async def run_cases():
            with patch("app.services.ai_router._retrieve_local_sources", new_callable=AsyncMock) as mock_ret:
                with patch("app.services.llm_service.check_ollama_status", new_callable=AsyncMock) as mock_ol:
                    mock_ol.return_value = {"running": False, "available_models": []}
                    res = await answer_query("default", "xin chào")
                    self.assertEqual(res["retrieval"], "conversational")
                    mock_ret.assert_not_awaited()

            with patch("app.services.document_service.embed_texts", side_effect=_topic_embed):
                doc_mod.process_and_index_document(
                    "default",
                    "law.txt",
                    b"Quy dinh an toan thong tin noi bo trong cong ty.",
                )
            events = []
            with patch("app.services.ai_router._retrieve_local_sources", new_callable=AsyncMock) as mock_ret:
                mock_ret.return_value = [
                    {
                        "chunk_id": "c1",
                        "document_id": "d1",
                        "document_name": "law.txt",
                        "page_number": 1,
                        "chunk_index": 0,
                        "content": "Quy dinh an toan thong tin noi bo trong cong ty.",
                    }
                ]
                with patch("app.services.llm_service.check_ollama_status", new_callable=AsyncMock) as mock_ol:
                    mock_ol.return_value = {"running": False, "available_models": []}
                    async for raw in stream_query("default", "quy định an toàn là gì?"):
                        if raw.startswith("data: ") and "[DONE]" not in raw:
                            events.append(json.loads(raw[6:].strip()))

            stages = [e.get("stage") for e in events if e.get("stage")]
            self.assertIn("retrieving", stages)
            self.assertIn("found_sources", stages)
            found_evt = next(e for e in events if e.get("stage") == "found_sources")
            self.assertEqual(len(found_evt["citations"]), 1)

        asyncio.run(run_cases())

    def test_status_and_hardware_profile_persistence_endpoints(self):
        with patch.dict(os.environ, {"DISABLE_MODEL_WARMUP": "1"}):
            with patch("app.api.chat.check_ollama_status", new_callable=AsyncMock) as mock_ol:
                mock_ol.return_value = {"running": True, "available_models": ["qwen2.5:3b"], "message": "ok"}
                client = TestClient(app)
                reg = client.post(
                    "/api/v1/auth/register",
                    json={"email": "perf@example.com", "password": "Password123!", "name": "Perf User"},
                )
                self.assertEqual(reg.status_code, 201, reg.text)
                headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

                st1 = client.get("/api/v1/status")
                self.assertEqual(st1.status_code, 200)
                self.assertIn("hardware_profile", st1.json())

                upd = client.patch(
                    "/api/v1/system/hardware-profile",
                    json={"mode": "eco"},
                    headers=headers,
                )
                self.assertEqual(upd.status_code, 200, upd.text)
                self.assertEqual(upd.json()["hardware_profile"]["active_id"], "eco")
                self.assertEqual(upd.json()["hardware_profile"]["selected_mode"], "eco")

                st2 = client.get("/api/v1/status")
                self.assertEqual(st2.json()["hardware_profile"]["active_id"], "eco")


if __name__ == "__main__":
    unittest.main()
