"""Unit & integration tests for workspace auto-metadata generation and semantic search."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

import app.database as db_mod  # noqa: E402
import app.services.document_service as doc_mod  # noqa: E402
from app.main import app  # noqa: E402


def _fake_topic_embed(texts):
    """Tạo vector 5 chiều trực giao theo chủ đề để kiểm thử tìm kiếm ngữ nghĩa nhanh & xác định."""
    vectors = []
    for raw in texts:
        t = (raw or "").lower()
        v = [0.02, 0.02, 0.02, 0.02, 0.02]
        matched = False
        if any(k in t for k in ("mạng", "tcp", "router", "giao thức", "định tuyến", "ip", "bắt tay", "thiết bị")):
            v[0] += 1.0
            matched = True
        if any(k in t for k in ("nhật", "jlpt", "n3", "kanji", "từ vựng", "ngữ pháp", "đề thi")):
            v[1] += 1.0
            matched = True
        if any(k in t for k in ("nấu ăn", "ẩm thực", "bánh", "món ăn", "gia vị")):
            v[2] += 1.0
            matched = True
        if any(k in t for k in ("rag", "vector", "embedding", "llm", "trí tuệ")):
            v[3] += 1.0
            matched = True
        if not matched:
            v[4] += 1.0
        norm = sum(x * x for x in v) ** 0.5
        vectors.append([x / norm for x in v])
    return vectors


class WorkspaceAITestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp_dir.name)
        self.orig_db_path = db_mod.DATABASE_PATH
        self.orig_data_dir = db_mod.DATA_DIR
        self.orig_db_upload = db_mod.UPLOAD_DIR
        self.orig_doc_upload = doc_mod.UPLOAD_DIR

        db_mod.DATA_DIR = tmp_path / "data"
        db_mod.UPLOAD_DIR = db_mod.DATA_DIR / "uploads"
        db_mod.DATABASE_PATH = db_mod.DATA_DIR / "test_knowledge.db"
        doc_mod.UPLOAD_DIR = db_mod.UPLOAD_DIR

        db_mod.init_db()
        self.client = TestClient(app)

        self.user_a_headers = self._register_and_headers("usera@example.com", "Password123!", "User A")
        self.user_b_headers = self._register_and_headers("userb@example.com", "Password123!", "User B")

    def tearDown(self):
        db_mod.DATABASE_PATH = self.orig_db_path
        db_mod.DATA_DIR = self.orig_data_dir
        db_mod.UPLOAD_DIR = self.orig_db_upload
        doc_mod.UPLOAD_DIR = self.orig_doc_upload
        self.tmp_dir.cleanup()

    def _register_and_headers(self, email: str, password: str, name: str):
        resp = self.client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "name": name},
        )
        self.assertEqual(resp.status_code, 201, resp.text)
        token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    @patch("app.services.workspace_ai_service.embed_texts", side_effect=_fake_topic_embed)
    @patch("app.services.document_service.embed_texts", side_effect=_fake_topic_embed)
    def test_quick_create_unique_default_names(self, _mock_doc_emb, _mock_ws_emb):
        r1 = self.client.post("/api/v1/workspaces", json={"name": ""}, headers=self.user_a_headers)
        r2 = self.client.post("/api/v1/workspaces", json={}, headers=self.user_a_headers)
        self.assertEqual(r1.status_code, 201, r1.text)
        self.assertEqual(r2.status_code, 201, r2.text)
        self.assertEqual(r1.json()["workspace"]["name"], "Workspace mới")
        self.assertEqual(r2.json()["workspace"]["name"], "Workspace mới 2")

    @patch("app.services.workspace_ai_service.embed_texts", side_effect=_fake_topic_embed)
    @patch("app.services.document_service.embed_texts", side_effect=_fake_topic_embed)
    @patch("app.services.workspace_ai_service.call_ollama_json", new_callable=AsyncMock)
    def test_auto_generate_metadata_on_upload_and_batch_defer(
        self, mock_ollama, _mock_doc_emb, _mock_ws_emb
    ):
        ws_resp = self.client.post("/api/v1/workspaces", json={}, headers=self.user_a_headers)
        ws_id = ws_resp.json()["workspace"]["id"]

        mock_ollama.return_value = {
            "ok": True,
            "model_used": "qwen2.5:7b",
            "data": {
                "title": "Mạng Máy Tính Cơ Bản",
                "description": "Tài liệu về giao thức TCP/IP và định tuyến mạng.",
                "category": "Kỹ thuật",
            },
        }
        up1 = self.client.post(
            f"/api/v1/workspaces/{ws_id}/documents/upload",
            files={"file": ("network_lab1.txt", b"Giao thuc TCP/IP va dinh tuyen router.", "text/plain")},
            headers=self.user_a_headers,
        )
        self.assertEqual(up1.status_code, 200, up1.text)
        body1 = up1.json()
        self.assertEqual(body1["metadata_source"], "ai")
        self.assertEqual(body1["workspace"]["name"], "Mạng Máy Tính Cơ Bản")
        self.assertEqual(body1["workspace"]["category"], "Kỹ thuật")

        # Upload theo batch với defer_metadata=true: chưa gọi LLM
        call_count_before = mock_ollama.await_count
        up2 = self.client.post(
            f"/api/v1/workspaces/{ws_id}/documents/upload",
            files={"file": ("security_lab2.txt", b"Bao mat tang mang va tuong lua firewall.", "text/plain")},
            data={"defer_metadata": "true"},
            headers=self.user_a_headers,
        )
        self.assertEqual(up2.status_code, 200, up2.text)
        self.assertEqual(up2.json()["metadata_source"], "deferred")
        self.assertEqual(mock_ollama.await_count, call_count_before)

        # Kết thúc batch mới gọi generate-metadata 1 lần:
        # Tiêu đề giữ nguyên theo file đầu tiên ('Mạng Máy Tính Cơ Bản'), mô tả cập nhật bao quát các file đang có
        mock_ollama.return_value = {
            "ok": True,
            "model_used": "qwen2.5:7b",
            "data": {
                "title": "Tên Khác Không Được Ghi Đè",
                "description": "Workspace hiện có tài liệu hướng dẫn TCP/IP cùng tài liệu cấu hình tường lửa bảo mật mạng.",
                "category": "Kỹ thuật",
            },
        }
        gen = self.client.post(
            f"/api/v1/workspaces/{ws_id}/generate-metadata",
            headers=self.user_a_headers,
        )
        self.assertEqual(gen.status_code, 200, gen.text)
        self.assertEqual(gen.json()["workspace"]["name"], "Mạng Máy Tính Cơ Bản")
        self.assertIn("tường lửa", gen.json()["workspace"]["description"])
        self.assertEqual(gen.json()["workspace"]["doc_count"], 2)

    @patch("app.services.workspace_ai_service.embed_texts", side_effect=_fake_topic_embed)
    @patch("app.services.document_service.embed_texts", side_effect=_fake_topic_embed)
    @patch("app.services.workspace_ai_service.call_ollama_json", new_callable=AsyncMock)
    def test_fallback_when_ollama_offline(self, mock_ollama, _mock_doc_emb, _mock_ws_emb):
        ws_id = self.client.post("/api/v1/workspaces", json={}, headers=self.user_a_headers).json()["workspace"]["id"]
        mock_ollama.return_value = {"ok": False, "error": "ollama_offline", "data": None}

        up = self.client.post(
            f"/api/v1/workspaces/{ws_id}/documents/upload",
            files={"file": ("DeThi_JLPT_N3.txt", b"Ngu phap va tu vung N3.", "text/plain")},
            headers=self.user_a_headers,
        )
        self.assertEqual(up.status_code, 200, up.text)
        body = up.json()
        self.assertEqual(body["metadata_source"], "fallback")
        self.assertIn("DeThi JLPT N3", body["workspace"]["name"])

    @patch("app.services.workspace_ai_service.embed_texts", side_effect=_fake_topic_embed)
    @patch("app.services.document_service.embed_texts", side_effect=_fake_topic_embed)
    @patch("app.services.workspace_ai_service.call_ollama_json", new_callable=AsyncMock)
    def test_semantic_search_home_and_global_with_isolation(
        self, mock_ollama, _mock_doc_emb, _mock_ws_emb
    ):
        # User A có 2 workspace với tên trung tính nhưng nội dung khác hẳn nhau
        mock_ollama.return_value = {"ok": False, "error": "offline", "data": None}
        ws1 = self.client.post(
            "/api/v1/workspaces",
            json={"name": "Học kỳ 6", "description": "Lưu trữ bài tập môn chuyên ngành"},
            headers=self.user_a_headers,
        ).json()["workspace"]["id"]
        ws2 = self.client.post(
            "/api/v1/workspaces",
            json={"name": "Sở thích cuối tuần", "description": "Ghi chép cá nhân"},
            headers=self.user_a_headers,
        ).json()["workspace"]["id"]

        self.client.post(
            f"/api/v1/workspaces/{ws1}/documents/upload",
            files={"file": ("bai_giang.txt", b"Co che bat tay 3 buoc TCP va dinh tuyen goi tin IP.", "text/plain")},
            data={"defer_metadata": "true"},
            headers=self.user_a_headers,
        )
        self.client.post(
            f"/api/v1/workspaces/{ws2}/documents/upload",
            files={"file": ("so_tay.txt", b"Cong thuc lam banh mi va nau an cuoi tuan.", "text/plain")},
            data={"defer_metadata": "true"},
            headers=self.user_a_headers,
        )

        # User B tạo workspace riêng chứa nội dung JLPT
        ws_b = self.client.post(
            "/api/v1/workspaces",
            json={"name": "JLPT của B", "description": "Ôn thi tiếng Nhật"},
            headers=self.user_b_headers,
        ).json()["workspace"]["id"]
        self.client.post(
            f"/api/v1/workspaces/{ws_b}/documents/upload",
            files={"file": ("n3.txt", b"Tu vung kanji N3 va ngu phap.", "text/plain")},
            data={"defer_metadata": "true"},
            headers=self.user_b_headers,
        )

        # Tìm kiếm ngữ nghĩa ở trang Home của User A (không chứa từ "mạng" hay "TCP" trong tên "Học kỳ 6")
        home_res = self.client.get(
            "/api/v1/workspaces/search",
            params={"q": "cơ chế bắt tay giao thức mạng và địa chỉ IP"},
            headers=self.user_a_headers,
        )
        self.assertEqual(home_res.status_code, 200, home_res.text)
        ws_hits = home_res.json()["workspaces"]
        self.assertTrue(len(ws_hits) >= 1)
        self.assertEqual(ws_hits[0]["id"], ws1)
        self.assertTrue(all(w["id"] != ws_b for w in ws_hits))

        # Global search Ctrl+K của User A trả về cả workspace và document có snippet thật
        global_res = self.client.get(
            "/api/v1/search",
            params={"q": "giao thức TCP định tuyến"},
            headers=self.user_a_headers,
        )
        self.assertEqual(global_res.status_code, 200, global_res.text)
        hits = global_res.json()["hits"]
        kinds = {h["kind"] for h in hits}
        self.assertIn("workspace", kinds)
        self.assertIn("document", kinds)
        doc_hit = next(h for h in hits if h["kind"] == "document")
        self.assertEqual(doc_hit["workspaceId"], ws1)
        self.assertIn("TCP", doc_hit["snippet"])
        self.assertTrue(all(h["workspaceId"] != ws_b for h in hits))

    @patch("app.services.workspace_ai_service.embed_texts", side_effect=_fake_topic_embed)
    @patch("app.services.document_service.embed_texts", side_effect=_fake_topic_embed)
    def test_global_search_notebooks_notes_conversations_and_doc_delete(
        self, _mock_doc_emb, _mock_ws_emb
    ):
        ws_id = self.client.post(
            "/api/v1/workspaces",
            json={"name": "Phòng thí nghiệm AI"},
            headers=self.user_a_headers,
        ).json()["workspace"]["id"]

        # Tạo notebook, note và conversation
        nb = self.client.post(
            f"/api/v1/workspaces/{ws_id}/notebooks",
            json={"name": "Chuyên đề RAG", "description": "Nghiên cứu vector search"},
            headers=self.user_a_headers,
        )
        self.assertEqual(nb.status_code, 201, nb.text)

        note = self.client.post(
            f"/api/v1/workspaces/{ws_id}/notes",
            json={"title": "Ghi chú BGE-M3", "content": "Embedding model đa ngôn ngữ cho RAG."},
            headers=self.user_a_headers,
        )
        self.assertEqual(note.status_code, 201, note.text)

        conv = self.client.post(
            f"/api/v1/workspaces/{ws_id}/conversations",
            json={"title": "Hỏi đáp về vector embedding"},
            headers=self.user_a_headers,
        )
        self.assertEqual(conv.status_code, 201, conv.text)

        # Upload rồi xóa tài liệu
        up = self.client.post(
            f"/api/v1/workspaces/{ws_id}/documents/upload",
            files={"file": ("rag_guide.txt", b"Kien truc Hybrid RAG ket hop BM25 va vector.", "text/plain")},
            data={"defer_metadata": "true"},
            headers=self.user_a_headers,
        )
        self.assertEqual(up.status_code, 200, up.text)
        doc_id = up.json()["document"]["document_id"]

        res_all = self.client.get(
            "/api/v1/search",
            params={"q": "vector embedding RAG"},
            headers=self.user_a_headers,
        )
        self.assertEqual(res_all.status_code, 200)
        kinds = {h["kind"] for h in res_all.json()["hits"]}
        self.assertTrue({"workspace", "notebook", "document", "note", "conversation"}.issubset(kinds))

        del_res = self.client.delete(f"/api/v1/documents/{doc_id}", headers=self.user_a_headers)
        self.assertEqual(del_res.status_code, 200, del_res.text)

        res_docs = self.client.get(
            "/api/v1/search",
            params={"q": "Hybrid RAG BM25", "kind": "document"},
            headers=self.user_a_headers,
        )
        self.assertEqual(res_docs.status_code, 200)
        self.assertEqual(res_docs.json()["hits"], [])

    @patch("app.services.workspace_ai_service.embed_texts", side_effect=_fake_topic_embed)
    @patch("app.services.document_service.embed_texts", side_effect=_fake_topic_embed)
    @patch("app.services.workspace_ai_service.call_ollama_json", new_callable=AsyncMock)
    def test_accented_phrase_de_thi_no_false_substring_or_diacritic_leak(
        self, mock_ollama, _mock_doc_emb, _mock_ws_emb
    ):
        mock_ollama.return_value = {"ok": False, "error": "offline", "data": None}
        # Workspace chứa 'ThietBi' (chuỗi con 'thi') và từ 'để', 'thì' (khác dấu với 'đề thi')
        ws_noise = self.client.post(
            "/api/v1/workspaces",
            json={"name": "PBL6", "description": "hiii"},
            headers=self.user_a_headers,
        ).json()["workspace"]["id"]
        self.client.post(
            f"/api/v1/workspaces/{ws_noise}/documents/upload",
            files={
                "file": (
                    "DanhSach_ThietBi_Mang.txt",
                    "Tổng quan hệ thống. Tài liệu này để tìm hiểu thiết bị, thì giờ và định tuyến mạng.".encode("utf-8"),
                    "text/plain",
                )
            },
            data={"defer_metadata": "true"},
            headers=self.user_a_headers,
        )
        ws_empty = self.client.post(
            "/api/v1/workspaces",
            json={"name": "Workspace Trống", "description": ""},
            headers=self.user_a_headers,
        ).json()["workspace"]["id"]

        ws_exam = self.client.post(
            "/api/v1/workspaces",
            json={"name": "JLPT N3", "description": "Luyện đề thi tiếng Nhật N3"},
            headers=self.user_a_headers,
        ).json()["workspace"]["id"]

        res = self.client.get(
            "/api/v1/workspaces/search",
            params={"q": "đề thi"},
            headers=self.user_a_headers,
        )
        self.assertEqual(res.status_code, 200, res.text)
        returned_ids = [w["id"] for w in res.json()["workspaces"]]
        self.assertIn(ws_exam, returned_ids)
        self.assertNotIn(ws_noise, returned_ids)
        self.assertNotIn(ws_empty, returned_ids)

    @patch("app.services.workspace_ai_service.embed_texts", side_effect=_fake_topic_embed)
    @patch("app.services.document_service.embed_texts", side_effect=_fake_topic_embed)
    @patch("app.services.workspace_ai_service.call_ollama_json", new_callable=AsyncMock)
    def test_fallback_preserves_existing_good_description_on_multi_upload(
        self, mock_ollama, _mock_doc_emb, _mock_ws_emb
    ):
        ws_id = self.client.post("/api/v1/workspaces", json={}, headers=self.user_a_headers).json()["workspace"]["id"]

        mock_ollama.return_value = {
            "ok": True,
            "model_used": "qwen2.5:3b",
            "data": {
                "title": "Từ Vựng Mĩmikara N3",
                "description": "Tài liệu học từ vựng và mẫu câu tiếng Nhật trình độ JLPT N3.",
                "category": "Ngoại ngữ",
            },
        }
        self.client.post(
            f"/api/v1/workspaces/{ws_id}/documents/upload",
            files={"file": ("mimikara_n3.txt", b"Tu vung Mimikara N3 bai 1.", "text/plain")},
            headers=self.user_a_headers,
        )

        # Giả lập lần up file tiếp theo Ollama tạm lỗi -> không được ghi đè bằng 'Tổng hợp 2 tài liệu: ...'
        mock_ollama.return_value = {"ok": False, "error": "timeout", "data": None}
        up2 = self.client.post(
            f"/api/v1/workspaces/{ws_id}/documents/upload",
            files={"file": ("n3_2017.txt", b"De thi JLPT N3 nam 2017.", "text/plain")},
            headers=self.user_a_headers,
        )
        self.assertEqual(up2.status_code, 200, up2.text)
        desc = up2.json()["workspace"]["description"]
        self.assertNotIn("Tổng hợp 2 tài liệu:", desc)
        self.assertEqual(desc, "Tài liệu học từ vựng và mẫu câu tiếng Nhật trình độ JLPT N3.")


if __name__ == "__main__":
    unittest.main()
