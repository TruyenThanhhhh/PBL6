"""Tests for RAM & Low-Memory optimization: dynamic keep_alive, startup RAM gates, idle eviction, low-RAM reranker bypass, bounded vector cache, and /system/free-memory."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

import app.database as db_mod  # noqa: E402
import app.services.document_service as doc_mod  # noqa: E402
import app.services.embedding_service as emb_mod  # noqa: E402
import app.services.reranker_service as rerank_mod  # noqa: E402
import app.services.retrieval_service as ret_mod  # noqa: E402
from app.main import app  # noqa: E402
from app.services.hardware_profile_service import (  # noqa: E402
    get_recommended_keep_alive,
    should_warmup_on_startup,
)


class MemoryOptimizationTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp_dir.name)
        self.orig_db_path = db_mod.DATABASE_PATH
        self.orig_data_dir = db_mod.DATA_DIR
        self.orig_db_upload = db_mod.UPLOAD_DIR
        self.orig_doc_upload = doc_mod.UPLOAD_DIR

        db_mod.DATA_DIR = tmp_path / "data"
        db_mod.UPLOAD_DIR = db_mod.DATA_DIR / "uploads"
        db_mod.DATABASE_PATH = db_mod.DATA_DIR / "test_mem.db"
        doc_mod.UPLOAD_DIR = db_mod.UPLOAD_DIR

        db_mod.init_db()
        ret_mod.invalidate_workspace_vector_cache()

    def tearDown(self):
        emb_mod.unload_embedding_model(trim_os=False)
        rerank_mod.unload_reranker_model(trim_os=False)
        ret_mod.invalidate_workspace_vector_cache()
        db_mod.DATABASE_PATH = self.orig_db_path
        db_mod.DATA_DIR = self.orig_data_dir
        db_mod.UPLOAD_DIR = self.orig_db_upload
        doc_mod.UPLOAD_DIR = self.orig_doc_upload
        self.tmp_dir.cleanup()

    def test_dynamic_keep_alive_and_startup_warmup_ram_gates(self):
        self.assertEqual(
            get_recommended_keep_alive({"id": "eco", "specs": {"available_ram_gb": 5.0}}),
            "2m",
        )
        self.assertEqual(
            get_recommended_keep_alive({"id": "balanced", "specs": {"available_ram_gb": 3.0}}),
            "2m",
        )
        self.assertEqual(
            get_recommended_keep_alive({"id": "balanced", "specs": {"available_ram_gb": 5.8}}),
            "5m",
        )
        self.assertEqual(
            get_recommended_keep_alive({"id": "performance", "specs": {"available_ram_gb": 10.0}}),
            "15m",
        )

        # Máy Balanced nhưng RAM trống chỉ còn 5.0 GB -> tắt warmup lúc khởi động để tránh đầy RAM
        self.assertEqual(
            should_warmup_on_startup(
                {
                    "warmup_embeddings": True,
                    "warmup_reranker": False,
                    "warmup_ollama": True,
                    "specs": {"available_ram_gb": 5.0},
                }
            ),
            (False, False, False),
        )
        self.assertEqual(
            should_warmup_on_startup(
                {
                    "warmup_embeddings": True,
                    "warmup_reranker": True,
                    "warmup_ollama": True,
                    "specs": {"available_ram_gb": 9.5},
                }
            ),
            (True, True, True),
        )

    def test_reranker_low_ram_guard_and_idle_eviction(self):
        rerank_mod.unload_reranker_model(trim_os=False)
        docs = [{"content": "doc 1"}, {"content": "doc 2"}]
        with patch(
            "app.services.hardware_profile_service.get_active_profile_config",
            return_value={
                "id": "balanced",
                "rerank_enabled": True,
                "rerank_max_candidates": 6,
                "specs": {"available_ram_gb": 3.1},
            },
        ), patch("app.services.reranker_service.get_memory_gb", return_value=(16.0, 3.1)):
            with patch.object(rerank_mod, "_get_model", wraps=rerank_mod._get_model) as spy_load:
                # Chưa nạp Reranker & RAM trống < 4.2GB -> bỏ qua nạp model ONNX nặng
                out = rerank_mod.rerank_documents("test", docs, top_k=2)
                self.assertEqual(out, docs)
                spy_load.assert_not_called()

        # Khi model đang nạp trong RAM và quá thời gian nhàn rỗi -> tự dỡ bỏ
        rerank_mod._RERANK_MODEL = MagicMock()
        rerank_mod._RERANK_LAST_USED_AT = time.monotonic() - 120.0
        self.assertTrue(rerank_mod.is_reranker_loaded())
        with patch("app.services.reranker_service.trim_process_memory") as mock_trim:
            self.assertTrue(rerank_mod.maybe_evict_idle_reranker_model(max_idle_sec=45.0))
            self.assertFalse(rerank_mod.is_reranker_loaded())
            mock_trim.assert_called_once()

    def test_embedding_idle_eviction_and_free_memory_endpoint(self):
        emb_mod._ST_MODEL = MagicMock()
        emb_mod._EMBED_LAST_USED_AT = time.monotonic() - 200.0
        self.assertTrue(emb_mod.is_embedding_model_loaded())
        with patch("app.services.embedding_service.trim_process_memory") as mock_trim:
            self.assertTrue(emb_mod.maybe_evict_idle_embedding_model(max_idle_sec=60.0))
            self.assertFalse(emb_mod.is_embedding_model_loaded())
            mock_trim.assert_called_once()

        with patch.dict(os.environ, {"DISABLE_MODEL_WARMUP": "1"}):
            client = TestClient(app)
            reg = client.post(
                "/api/v1/auth/register",
                json={"email": "memuser@example.com", "password": "Password123!", "name": "Mem User"},
            )
            self.assertEqual(reg.status_code, 201)
            headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

            emb_mod._ST_MODEL = MagicMock()
            rerank_mod._RERANK_MODEL = MagicMock()
            with patch("app.api.chat.unload_ollama_models", new_callable=AsyncMock) as mock_ol, \
                 patch("app.api.chat.get_memory_gb", side_effect=[(16.0, 2.5), (16.0, 6.1)]):
                mock_ol.return_value = ["qwen2.5:3b"]
                res = client.post("/api/v1/system/free-memory", headers=headers)
            self.assertEqual(res.status_code, 200, res.text)
            body = res.json()
            self.assertTrue(body["freed_embedding"])
            self.assertTrue(body["freed_reranker"])
            self.assertEqual(body["unloaded_ollama_models"], ["qwen2.5:3b"])
            self.assertEqual(body["available_ram_gb_before"], 2.5)
            self.assertEqual(body["available_ram_gb_after"], 6.1)
            self.assertFalse(emb_mod.is_embedding_model_loaded())
            self.assertFalse(rerank_mod.is_reranker_loaded())

    def test_vector_cache_lru_bound_max_3_workspaces(self):
        conn = db_mod.get_db_connection()
        try:
            cursor = conn.cursor()
            for idx in range(1, 5):
                ws_id = f"ws_lru_{idx}"
                ret_mod._get_workspace_vector_index(cursor, ws_id)
            self.assertLessEqual(len(ret_mod._VECTOR_CACHE), 3)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
