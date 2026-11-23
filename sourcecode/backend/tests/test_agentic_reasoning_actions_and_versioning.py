"""Tests for Stages 2, 3, and 4: intent routing, Python AST sandbox, autonomous reasoning loop, chat actions, and document versioning/diff."""
import asyncio
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

from fastapi.testclient import TestClient  # noqa: E402

import app.database as db_mod  # noqa: E402
import app.services.document_service as doc_mod  # noqa: E402
from app.main import app  # noqa: E402
from app.services.ai_router import stream_query  # noqa: E402
from app.services.document_diff_service import compute_document_diff, format_diff_markdown  # noqa: E402
from app.services.export_service import build_export_payload  # noqa: E402
from app.services.intent_service import classify_chat_intent  # noqa: E402
from app.services.python_sandbox_service import evaluate_python_sandbox  # noqa: E402
from app.services.retrieval_service import (  # noqa: E402
    invalidate_workspace_vector_cache,
    search_relevant_chunks,
)


def _dummy_embed(texts):
    res = []
    for raw in texts:
        t = (raw or "").lower()
        if "điều 5" in t or "mức phạt" in t:
            res.append([1.0, 0.0, 0.0])
        elif "công thức" in t or "lãi suất" in t:
            res.append([0.0, 1.0, 0.0])
        else:
            res.append([0.0, 0.0, 1.0])
    return res


class AgenticReasoningActionsVersioningTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp_dir.name)
        self.orig_db_path = db_mod.DATABASE_PATH
        self.orig_data_dir = db_mod.DATA_DIR
        self.orig_db_upload = db_mod.UPLOAD_DIR
        self.orig_doc_upload = doc_mod.UPLOAD_DIR

        db_mod.DATA_DIR = tmp_path / "data"
        db_mod.UPLOAD_DIR = db_mod.DATA_DIR / "uploads"
        db_mod.DATABASE_PATH = db_mod.DATA_DIR / "test_agentic.db"
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

    def test_intent_classification_accuracy_and_info_question_guard(self):
        q1 = classify_chat_intent("tạo cho tôi 10 câu trắc nghiệm từ 10 từ vựng đầu tiên")
        self.assertEqual(q1.kind, "create_quiz")
        self.assertEqual(q1.params["question_count"], 10)

        f1 = classify_chat_intent("lập 15 flashcard từ vựng tiếng nhật")
        self.assertEqual(f1.kind, "create_flashcards")
        self.assertEqual(f1.params["count"], 15)
        self.assertEqual(f1.params["card_style"], "vocabulary")

        d1 = classify_chat_intent("hãy soạn thảo một văn bản báo cáo tổng hợp thành word")
        self.assertEqual(d1.kind, "compose_document")
        self.assertEqual(d1.params["default_export_format"], "docx")

        v1 = classify_chat_intent("bản mới thay đổi gì so với bản cũ ngày 1?")
        self.assertEqual(v1.kind, "version_diff")

        r1 = classify_chat_intent("áp dụng công thức trong tài liệu tính tổng tiền sau 2 năm")
        self.assertEqual(r1.kind, "deep_reasoning")

        r2 = classify_chat_intent("nếu nhân viên nghỉ quá 15 ngày thì xử lý thế nào theo quy định?")
        self.assertEqual(r2.kind, "deep_reasoning")

        # Câu hỏi định nghĩa thuần túy không bị hiểu nhầm thành lệnh tạo quiz
        info = classify_chat_intent("cách tạo quiz hiệu quả là gì?")
        self.assertEqual(info.kind, "rag_qa")

        # Chế độ 'fast' giữ nguyên rag_qa kể cả với câu phức tạp
        fast = classify_chat_intent("áp dụng công thức tính lãi suất", reasoning_mode="fast")
        self.assertEqual(fast.kind, "rag_qa")

    def test_python_sandbox_math_logic_and_security_blocks(self):
        ok_res = evaluate_python_sandbox(
            {"P": 1000000, "r": 0.06, "n": 2, "days": 15},
            [
                "amount = P * (1 + r) ** n",
                "avg = sum([10, 20, 30]) / len([10, 20, 30])",
                "status = 'Vượt mức' if days > 12 else 'Hợp lệ'",
            ],
        )
        self.assertTrue(ok_res["ok"], ok_res)
        self.assertEqual(ok_res["env"]["amount"], 1123600)
        self.assertEqual(ok_res["env"]["avg"], 20)
        self.assertEqual(ok_res["env"]["status"], "Vượt mức")

        # Chặn các lệnh nguy hiểm
        for bad_expr in [
            "__import__('os').system('echo hack')",
            "open('secret.txt').read()",
            "eval('1+1')",
            "10 ** 5000",
        ]:
            bad_res = evaluate_python_sandbox({}, [bad_expr])
            self.assertFalse(bad_res["ok"], f"Expected sandbox rejection for {bad_expr}")

    @patch("app.services.document_service.embed_texts", side_effect=_dummy_embed)
    @patch("app.services.retrieval_service.embed_texts", side_effect=_dummy_embed)
    def test_autonomous_reasoning_loop_multihop_and_sandbox_repair(self, _m_ret, _m_doc):
        doc_mod.process_and_index_document(
            "default",
            "cong_thuc_tai_chinh.txt",
            "Công thức lãi kép: A = P * (1 + r) ** n.\nĐiều kiện ngoại lệ: nếu n >= 2 thì thưởng thêm 5000.\n".encode("utf-8"),
        )

        # Mô phỏng planner bước đầu sinh biến bị thiếu -> tự sửa 1 lần bằng self-repair -> chạy thành công
        planner_calls = [
            {
                "ok": True,
                "data": {
                    "goal": "Tính lãi kép 2 năm và cộng thưởng ngoại lệ",
                    "sub_queries": ["Điều kiện ngoại lệ thưởng"],
                    "cross_check_focus": "thưởng thêm",
                    "needs_calculation": True,
                    "variables": {"P": 1000000, "r": 0.06},
                    "expressions": ["A = P * (1 + r) ** n + 5000"],  # cố tình thiếu biến n để test self-repair
                },
            },
            {
                "ok": True,
                "data": {
                    "variables": {"P": 1000000, "r": 0.06, "n": 2},
                    "expressions": ["A = P * (1 + r) ** n + 5000"],
                },
            },
        ]

        async def fake_stream_ollama(**kwargs):
            payload = kwargs["payload"]
            user_text = payload["messages"][-1]["content"]
            # Xác nhận kết quả đã kiểm chứng từ Sandbox (1128600) đã được chèn vào prompt tổng hợp
            self.assertIn("1128600", user_text)
            ans = "## Kết luận suy luận\nÁp dụng công thức [1], đáp số chính xác là **1.128.600**.\n\n---GỢI Ý TIẾP THEO---\n- Tính lại nếu rút trước hạn\n- So sánh lãi đơn\n- Tạo bài tập tương tự"
            yield f"data: {json.dumps({'delta': ans}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'answer': ans, 'done': True}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        async def run_flow():
            events = []
            collector = {}
            with patch("app.services.reasoning_service.check_ollama_status", new_callable=AsyncMock) as mock_ol:
                mock_ol.return_value = {"running": True, "available_models": ["qwen2.5:3b"]}
                with patch("app.services.reasoning_service.call_ollama_json", new_callable=AsyncMock, side_effect=planner_calls):
                    with patch("app.services.reasoning_service._stream_ollama_chat", side_effect=fake_stream_ollama):
                        async for raw in stream_query(
                            "default",
                            "áp dụng công thức tính tổng tiền với P=1000000, r=6%, n=2 năm",
                            reasoning_mode="deep",
                            collector=collector,
                        ):
                            if raw.startswith("data: ") and "[DONE]" not in raw:
                                events.append(json.loads(raw[6:].strip()))
            return events, collector

        events, collector = asyncio.run(run_flow())
        steps = [e["reasoning_step"] for e in events if "reasoning_step" in e]
        self.assertGreaterEqual(len(steps), 3)
        action_res = collector.get("action_result")
        self.assertIsNotNone(action_res)
        self.assertEqual(action_res["action_type"], "reasoning_result")
        self.assertTrue(action_res["sandbox"]["ok"])
        self.assertEqual(action_res["sandbox"]["final_result"], 1128600)

    @patch("app.services.document_service.embed_texts", side_effect=_dummy_embed)
    @patch("app.services.retrieval_service.embed_texts", side_effect=_dummy_embed)
    def test_chat_actions_persist_quiz_and_exportable_document(self, _m_ret, _m_doc):
        doc_mod.process_and_index_document(
            "default",
            "bai_hoc.txt",
            b"Hybrid RAG ket hop BM25 va Vector Search. Cross-Encoder giup loc nhieu hieu qua.",
        )

        fake_quiz = {
            "title": "Quiz Hybrid RAG",
            "questions": [
                {
                    "id": "q1",
                    "prompt": "Hybrid RAG kết hợp hai kênh nào?",
                    "options": ["BM25 và Vector", "SQL và NoSQL", "HTTP và FTP", "CPU và RAM"],
                    "answerIndex": 0,
                    "explanation": "Theo tài liệu bài học.",
                }
            ],
            "is_mock": False,
        }

        async def run_actions():
            # 1. Hành động tạo Quiz trong Chat phải lưu vào bảng study_artifacts
            c1 = {}
            with patch("app.services.chat_action_service.generate_ai_quiz", new_callable=AsyncMock, return_value=fake_quiz):
                async for _ in stream_query("default", "hãy tạo 1 câu trắc nghiệm từ tài liệu", collector=c1):
                    pass

            self.assertEqual(c1["action_result"]["action_type"], "create_quiz")
            artifact_id = c1["action_result"]["artifact_id"]
            self.assertTrue(artifact_id)
            conn = db_mod.get_db_connection()
            try:
                saved = conn.execute("SELECT artifact_type, title FROM study_artifacts WHERE id = ?", (artifact_id,)).fetchone()
                self.assertIsNotNone(saved)
                self.assertEqual(saved["artifact_type"], "quiz")
            finally:
                conn.close()

            # 2. Hành động soạn thảo văn bản -> sinh Markdown xuất được .docx
            async def fake_compose_stream(**kwargs):
                md = "# Báo cáo Kỹ thuật Hybrid RAG\n\n## 1. Tổng quan\nHệ thống kết hợp BM25 và Vector [1]."
                yield f"data: {json.dumps({'delta': md}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'answer': md, 'done': True}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"

            c2 = {}
            with patch("app.services.chat_action_service.check_ollama_status", new_callable=AsyncMock) as mock_ol:
                mock_ol.return_value = {"running": True, "available_models": ["qwen2.5:3b"]}
                with patch("app.services.chat_action_service._stream_ollama_chat", side_effect=fake_compose_stream):
                    async for _ in stream_query("default", "soạn thảo một văn bản báo cáo từ tài liệu", collector=c2):
                        pass

            self.assertEqual(c2["action_result"]["action_type"], "compose_document")
            payload_bytes, media_type, _ascii, _utf8 = build_export_payload(
                c2["action_result"]["title"],
                c2["action_result"]["markdown"],
                "docx",
            )
            self.assertGreater(len(payload_bytes), 500)
            self.assertIn("wordprocessingml", media_type)

        asyncio.run(run_actions())

    @patch("app.services.document_service.embed_texts", side_effect=_dummy_embed)
    @patch("app.services.retrieval_service.embed_texts", side_effect=_dummy_embed)
    def test_document_versioning_temporal_rag_diff_and_delete_restore(self, _m_ret, _m_doc):
        with patch.dict(os.environ, {"DISABLE_MODEL_WARMUP": "1"}):
            with patch("app.api.workspaces.upsert_workspace_embedding"), patch(
                "app.api.workspaces.schedule_workspace_embedding"
            ):
                client = TestClient(app)
                reg = client.post(
                    "/api/v1/auth/register",
                    json={"email": "ver@example.com", "password": "Password123!", "name": "Version User"},
                )
                self.assertEqual(reg.status_code, 201, reg.text)
                headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
                ws_id = client.post("/api/v1/workspaces", json={"name": "Luat Workspace"}, headers=headers).json()["workspace"]["id"]

                # Ngày 1: Upload v1
                u1 = client.post(
                    f"/api/v1/workspaces/{ws_id}/documents/upload",
                    files={"file": ("luat_lao_dong.txt", "Điều 5: Mức phạt tối đa là 10 triệu đồng.".encode("utf-8"), "text/plain")},
                    data={"defer_metadata": "true", "effective_date": "2026-11-01"},
                    headers=headers,
                )
                self.assertEqual(u1.status_code, 200, u1.text)
                v1_doc = u1.json()["document"]
                v1_id = v1_doc["document_id"]
                self.assertEqual(v1_doc["version_number"], 1)

                # Ngày 2: Upload v2 thay thế Điều 5 và thêm Điều 6
                u2 = client.post(
                    f"/api/v1/workspaces/{ws_id}/documents/upload",
                    files={
                        "file": (
                            "luat_lao_dong.txt",
                            "Điều 5: Mức phạt tối đa là 25 triệu đồng.\nĐiều 6: Bổ sung quy định làm thêm giờ.".encode("utf-8"),
                            "text/plain",
                        )
                    },
                    data={
                        "defer_metadata": "true",
                        "replace_document_id": v1_id,
                        "effective_date": "2026-11-23",
                    },
                    headers=headers,
                )
                self.assertEqual(u2.status_code, 200, u2.text)
                v2_doc = u2.json()["document"]
                v2_id = v2_doc["document_id"]
                self.assertEqual(v2_doc["version_number"], 2)
                self.assertEqual(v2_doc["version_group_id"], v1_id)

                # Kiểm tra RAG mặc định CHỈ lấy bản hiệu lực mới nhất (25 triệu), không lẫn 10 triệu từ v1
                hits = search_relevant_chunks(ws_id, "Điều 5 mức phạt tối đa là bao nhiêu?", top_k=5)
                self.assertTrue(hits)
                combined_text = "\n".join(h["content"] for h in hits)
                self.assertIn("25 triệu", combined_text)
                self.assertNotIn("10 triệu", combined_text)
                self.assertEqual(hits[0]["version_number"], 2)
                self.assertEqual(hits[0]["effective_date"], "2026-11-23")

                # Kiểm tra API đối chiếu diff v1 -> v2
                diff_resp = client.post(
                    f"/api/v1/workspaces/{ws_id}/documents/diff",
                    json={"include_ai_summary": False},
                    headers=headers,
                )
                self.assertEqual(diff_resp.status_code, 200, diff_resp.text)
                diff_body = diff_resp.json()
                self.assertTrue(diff_body["ok"])
                self.assertGreaterEqual(diff_body["total_changes"], 1)
                self.assertIn("25 triệu", diff_body["markdown"])

                # Xóa v2 -> tự động khôi phục v1 lên lại is_latest = 1
                del_resp = client.delete(f"/api/v1/documents/{v2_id}", headers=headers)
                self.assertEqual(del_resp.status_code, 200, del_resp.text)

                hits_after_del = search_relevant_chunks(ws_id, "Điều 5 mức phạt", top_k=5)
                self.assertTrue(hits_after_del)
                self.assertIn("10 triệu", hits_after_del[0]["content"])


if __name__ == "__main__":
    unittest.main()
