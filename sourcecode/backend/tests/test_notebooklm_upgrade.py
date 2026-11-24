"""Tests for NotebookLM comprehensive upgrade: full-text citations, PUA-decoded chunk endpoints, Source Guide, rebuild, chunking boundaries, telemetry & routing."""
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
import app.services.retrieval_service as ret_mod  # noqa: E402
from app.main import app  # noqa: E402
from app.services.intent_service import classify_chat_intent  # noqa: E402
from app.services.llm_service import (  # noqa: E402
    _build_bounded_history_messages,
    _extract_tabular_match_excerpt,
    _prepare_rag_prompts_and_citations,
    _sanitize_rag_output,
    _strip_raw_latex_math,
    decode_symbol_pua_text,
    select_optimal_chat_model,
)
from app.services.reasoning_service import _fast_local_reasoning_planner  # noqa: E402
from app.services.retrieval_service import detect_section_intent  # noqa: E402


class NotebookLMUpgradeTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp_dir.name)
        self.orig_db_path = db_mod.DATABASE_PATH
        self.orig_data_dir = db_mod.DATA_DIR
        self.orig_db_upload = db_mod.UPLOAD_DIR
        self.orig_doc_upload = doc_mod.UPLOAD_DIR

        db_mod.DATA_DIR = tmp_path / "data"
        db_mod.UPLOAD_DIR = db_mod.DATA_DIR / "uploads"
        db_mod.DATABASE_PATH = db_mod.DATA_DIR / "test_nlm.db"
        doc_mod.UPLOAD_DIR = db_mod.UPLOAD_DIR

        db_mod.init_db()
        ret_mod.invalidate_workspace_vector_cache()

    def tearDown(self):
        ret_mod.invalidate_workspace_vector_cache()
        db_mod.DATABASE_PATH = self.orig_db_path
        db_mod.DATA_DIR = self.orig_data_dir
        db_mod.UPLOAD_DIR = self.orig_db_upload
        doc_mod.UPLOAD_DIR = self.orig_doc_upload
        self.tmp_dir.cleanup()

    def test_full_text_citations_latex_braces_and_section_chunking(self):
        long_passage = (
            "3. HỆ SỐ GÓC CỦA ĐƯỜNG THẲNG\n"
            + "Định nghĩa hệ số góc của đường thẳng y = ax + b (a ≠ 0): "
            + "Nếu đường thẳng đi qua hai điểm A(x₁, y₁) và B(x₂, y₂) thì k = (y₂ - y₁)/(x₂ - x₁). " * 8
            + "Hệ thức lượng tam giác vuông: 1/OH² = 1/OA² + 1/OB²."
        )
        chunks = [
            {
                "document_id": "doc_math_1",
                "document_name": "So_tay_Toan_9.pdf",
                "page_number": 21,
                "chunk_index": 5,
                "content": long_passage,
            }
        ]
        _sys, _usr, citations = _prepare_rag_prompts_and_citations("hệ số góc đường thẳng", chunks)
        self.assertEqual(len(citations), 1)
        cite = citations[0]
        self.assertLessEqual(len(cite["snippet"]), 325)
        self.assertGreater(len(cite["full_text"]), 500)
        self.assertIn("1/OH² = 1/OA² + 1/OB²", cite["full_text"])

        cleaned_brace = _strip_raw_latex_math("Góc tạo bởi đường thẳng: a = \\tan\\{\\alpha\\} và 2\\pi r")
        self.assertIn("tan(α)", cleaned_brace)
        self.assertIn("2π r", cleaned_brace)

        section_text = (
            "2. HÀM SỐ ĐỒNG BIẾN – NGHỊCH BIẾN\n"
            + ("Định nghĩa hàm số y = ax + b đồng biến trên R khi a > 0.\n" * 10)
            + "\n3. HỆ SỐ GÓC CỦA ĐƯỜNG THẲNG\n"
            + ("Góc tạo bởi đường thẳng với trục Ox.\n" * 10)
        )
        split_chunks = doc_mod.recursive_chunk_text(section_text, chunk_size=450, overlap=50)
        self.assertTrue(any("3. HỆ SỐ GÓC CỦA ĐƯỜNG THẲNG" in c for c in split_chunks))
        # Tiêu đề mục 3 không được phép gắn nhầm lên đầu đoạn nội dung của mục 2
        for c in split_chunks:
            if "đồng biến trên R" in c and "Góc tạo bởi đường thẳng" not in c:
                self.assertFalse(c.startswith("[3. HỆ SỐ GÓC"))

        # Kiểm tra gom hệ điều kiện ngoặc nhọn 3 dòng & khử lặp block ### giống nhau
        brace_raw = "{ x > 0\n- Thuộc góc phần tư thứ I: { và a1 ≠ a2\n{ y > 0"
        decoded_brace = decode_symbol_pua_text(brace_raw)
        self.assertIn("{ x > 0 ; y > 0 }", decoded_brace)

        dup_heading_raw = (
            "### Điều kiện góc phần tư I\n- x > 0 và y > 0 [1]\n\n"
            "### Điều kiện góc phần tư I\n- x > 0\n\n"
            "Câu hỏi/Yêu cầu của người dùng về chương 9 đã được giải đáp qua các tài liệu trên."
        )
        cleaned_dup = _sanitize_rag_output(dup_heading_raw, citations_count=1)
        self.assertEqual(cleaned_dup.count("### Điều kiện góc phần tư I"), 1)
        self.assertNotIn("đã được giải đáp qua các tài liệu", cleaned_dup)

        # Kiểm tra câu hỏi bài toán hình nón cụt ('bán kính 2 đáy lần lượt là 15cm và 10cm') đi đúng Python Sandbox & không rò history Chương 9
        frustum_q = (
            "Cho hình nón cụt có bán kính 2 đáy lần lượt là 15cm và 10cm, chiều cao 24cm. "
            "Tính đường sinh, diện tích xung quanh, diện tích toàn phần và thể tích của hình nón cụt đó."
        )
        it = classify_chat_intent(frustum_q, reasoning_mode="auto")
        self.assertEqual(it.kind, "deep_reasoning")
        plan = _fast_local_reasoning_planner(frustum_q, [])
        self.assertTrue(plan["needs_calculation"])
        self.assertEqual(plan["variables"].get("R_nc"), 15.0)
        self.assertEqual(plan["variables"].get("r_nc"), 10.0)
        self.assertEqual(plan["variables"].get("h_nc"), 24.0)

        ch9_history = [
            {"role": "user", "content": "Nội dung chương 9"},
            {"role": "assistant", "content": "Chương 9: Hai đường thẳng cắt nhau thỏa mãn điều kiện K"},
        ]
        self.assertEqual(_build_bounded_history_messages(ch9_history, current_query=frustum_q), [])
        self.assertEqual(_build_bounded_history_messages(ch9_history, current_query="後半 là gì"), [])
        self.assertTrue(_build_bounded_history_messages(ch9_history, current_query="Giải thích thêm bước 2 vừa rồi"))
        self.assertIsNone(
            detect_section_intent("後半 là gì", [{"role": "user", "content": "Nội dung bài 2 gồm những gì?"}])
        )

        vocab_tbl = "104 | 多く | おおく | nhiều\n105 | 前半 | ぜんはん | phần đầu\n106 | 後半 | こうはん | phần cuối"
        vocab_tbl = vocab_tbl + ("\n107 | a | b | c\n108 | d | e | f\n109 | g | h | i")
        excerpt_koh = _extract_tabular_match_excerpt("後半 là gì", vocab_tbl)
        self.assertEqual(excerpt_koh, "106 | 後半 | こうはん | phần cuối")

        zh_leak_raw = (
            '[Tài liệu trong kho tri thức của bạn không chứa thông tin về chủ đề "tóm tắt nội dung".]\n'
            "Tổng Hợp Toàn Tác Liệu\n"
            "Danh sách từ vựng về động词，包括以下示例:\n- 歩く\n\n"
            "Trích Đoạn Trọng Tâm Khớp Câu Hỏi Nhất:\n• 298 | 不自由な"
        )
        cleaned_zh = _sanitize_rag_output(zh_leak_raw, citations_count=2)
        self.assertNotIn("không chứa thông tin về chủ đề", cleaned_zh)
        self.assertNotIn("包括以下示例", cleaned_zh)
        self.assertNotIn("động词", cleaned_zh)
        self.assertNotIn("Trích Đoạn Trọng Tâm", cleaned_zh)
        self.assertIn("động từ", cleaned_zh)

        # Kiểm tra tóm tắt nhanh bảng từ vựng không bị lẫn chữ Hán giản thể hay sai bài học
        from app.services.llm_service import _try_build_exhaustive_tabular_list_answer
        wb_chunks = [
            {
                "document_id": "doc_missing_db_id",
                "document_name": "Mimikara_N3.xlsx",
                "page_number": 1,
                "chunk_index": 1,
                "content": (
                    "Bài 1 - 名詞 - 120\n"
                    "1 | 男性 | だんせい | đàn ông\n"
                    "Bài 2 - 動詞\n"
                    "121 | 鳴る | なる | kêu\n"
                    "Bài 4 - 形容詞\n"
                    "301 | 濃い | こい | đậm\n"
                ),
            }
        ]
        wb_sum = _try_build_exhaustive_tabular_list_answer("tóm tắt nội dung", wb_chunks)
        self.assertIsNotNone(wb_sum)
        self.assertIn("Bài 1 - 名詞 - 120 (Danh từ)", wb_sum)
        self.assertIn("`鳴る` (なる: kêu)", wb_sum)
        self.assertIn("`濃い` (こい: đậm)", wb_sum)

        broken_bold = "**[1] 3. Hình nón – Hình nón cụt:\ntừ Tài liệu 3: Sxq = π(R+r)l"
        cleaned_broken = _sanitize_rag_output(broken_bold, citations_count=2)
        self.assertNotIn("**[1]", cleaned_broken)
        self.assertNotIn("Tài liệu 3", cleaned_broken)

    def test_guide_decoded_chunks_rebuild_and_chat_latency_persistence(self):
        with patch.dict(os.environ, {"DISABLE_MODEL_WARMUP": "1"}), \
             patch("app.services.document_service.embed_texts", return_value=[[0.5, 0.5, 0.0]]), \
             patch("app.api.workspaces.schedule_workspace_embedding"):
            with TestClient(app) as client:
                reg = client.post(
                    "/api/v1/auth/register",
                    json={"email": "nlm@example.com", "password": "Password123!", "name": "NotebookLM User"},
                )
                self.assertEqual(reg.status_code, 201, reg.text)
                headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
                ws_id = client.get("/api/v1/workspaces", headers=headers).json()["workspaces"][0]["id"]

                sample_txt = (
                    "CHƯƠNG 1. HÀM SỐ BẬC NHẤT\n"
                    "Nếu 0 < a thì hàm số đồng biến trên R.\n\n"
                    "CHƯƠNG 2. HỆ THỨC LƯỢNG TRONG TAM GIÁC VUÔNG\n"
                    "Ta có 1/OH² = 1/OA² + 1/OB² và tan(α) = a.\n"
                ).encode("utf-8")
                up = client.post(
                    f"/api/v1/workspaces/{ws_id}/documents/upload",
                    headers=headers,
                    files={"file": ("toan9_guide.txt", sample_txt, "text/plain")},
                    data={"defer_metadata": "true"},
                )
                self.assertEqual(up.status_code, 200, up.text)
                doc_id = up.json()["document"]["document_id"]

                # Mô phỏng chunk legacy chứa ký tự PUA MS Word \uf03c / \uf0de để kiểm tra on-read decode + guide flag
                conn = db_mod.get_db_connection()
                try:
                    conn.execute(
                        "UPDATE document_chunks SET content = ? WHERE document_id = ?",
                        ("0 \uf03c a \uf0de hàm số đồng biến", doc_id),
                    )
                    conn.commit()
                finally:
                    conn.close()

                guide_res = client.get(f"/api/v1/documents/{doc_id}/guide", headers=headers)
                self.assertEqual(guide_res.status_code, 200, guide_res.text)
                guide = guide_res.json()
                self.assertEqual(guide["doc_category"], "math_science")
                self.assertTrue(guide["has_legacy_pua"])
                self.assertTrue(guide["suggested_questions"])

                chunks_res = client.get(f"/api/v1/documents/{doc_id}/chunks", headers=headers)
                self.assertEqual(chunks_res.status_code, 200, chunks_res.text)
                chunk_contents = "\n".join(c["content"] for c in chunks_res.json()["chunks"])
                self.assertIn("0 < a ⇒ hàm số đồng biến", chunk_contents)
                self.assertNotIn("\uf03c", chunk_contents)

                # Rebuild khôi phục nguyên bản sạch từ file gốc trên đĩa
                reb_res = client.post(f"/api/v1/documents/{doc_id}/rebuild", headers=headers)
                self.assertEqual(reb_res.status_code, 200, reb_res.text)
                self.assertTrue(reb_res.json()["rebuilt"])

                # Kiểm tra lưu latency_seconds & modelId & fullText citations qua /chat/query
                conv = client.post(
                    f"/api/v1/workspaces/{ws_id}/conversations",
                    headers=headers,
                    json={"title": "Test NotebookLM"},
                ).json()["conversation"]
                with patch("app.api.chat.answer_query", new_callable=AsyncMock) as mock_ans:
                    mock_ans.return_value = {
                        "answer": "Hàm số đồng biến khi a > 0 [1].",
                        "citations": [
                            {
                                "ref_id": 1,
                                "source_type": "document",
                                "document_id": doc_id,
                                "document_name": "toan9_guide.txt",
                                "page_number": 1,
                                "page_label": "Trang 1",
                                "chunk_index": 0,
                                "snippet": "Nếu 0 < a...",
                                "full_text": "CHƯƠNG 1. HÀM SỐ BẬC NHẤT\nNếu 0 < a thì hàm số đồng biến trên R.",
                            }
                        ],
                        "model_used": "qwen2.5:3b",
                        "engine": "ollama_local",
                    }
                    q_res = client.post(
                        "/api/v1/chat/query",
                        headers=headers,
                        json={
                            "workspace_id": ws_id,
                            "conversation_id": conv["id"],
                            "query": "Khi nào hàm số đồng biến?",
                            "model": "auto",
                        },
                    )
                self.assertEqual(q_res.status_code, 200, q_res.text)
                self.assertIn("latency_seconds", q_res.json())

                hist = client.get(f"/api/v1/conversations/{conv['id']}/messages", headers=headers)
                self.assertEqual(hist.status_code, 200, hist.text)
                asst_msg = [m for m in hist.json()["messages"] if m["role"] == "assistant"][-1]
                self.assertIsNotNone(asst_msg.get("latencySeconds"))
                self.assertEqual(asst_msg.get("modelId"), "qwen2.5:3b")
                self.assertIn("CHƯƠNG 1. HÀM SỐ BẬC NHẤT", asst_msg["citations"][0]["fullText"])

    def test_smart_auto_model_routing_fast_vs_deep(self):
        with patch(
            "app.services.hardware_profile_service.get_active_profile_config",
            return_value={
                "id": "balanced",
                "specs": {"available_ram_gb": 10.0, "gpu_vram_mb": 4096},
            },
        ):
            self.assertEqual(
                select_optimal_chat_model("auto", ["qwen2.5:3b", "qwen2.5:7b"], task_tier="fast"),
                "qwen2.5:3b",
            )
            self.assertEqual(
                select_optimal_chat_model("auto", ["qwen2.5:3b", "qwen2.5:7b"], task_tier="deep"),
                "qwen2.5:7b",
            )

        with patch(
            "app.services.hardware_profile_service.get_active_profile_config",
            return_value={
                "id": "eco",
                "specs": {"available_ram_gb": 3.5, "gpu_vram_mb": 0},
            },
        ):
            self.assertEqual(
                select_optimal_chat_model("auto", ["qwen2.5:3b", "qwen2.5:7b"], task_tier="deep"),
                "qwen2.5:3b",
            )

    def test_explicit_7b_respected_and_overview_sanitizer_preserves_content(self) -> None:
        from app.services.llm_service import _build_instant_followup_suggestions, _sanitize_rag_output
        from app.services.retrieval_service import is_global_summary_query

        # 1. Người dùng chọn đích danh Qwen 7B ở FE -> phải giữ qwen2.5:7b, không âm thầm hạ về 3B
        balanced_4gb = {
            "id": "balanced",
            "specs": {"available_ram_gb": 5.5, "gpu_vram_mb": 4096},
        }
        with patch("app.services.hardware_profile_service.get_active_profile_config", return_value=balanced_4gb):
            self.assertEqual(
                select_optimal_chat_model("qwen2.5:7b", ["qwen2.5:7b", "qwen2.5:3b"], task_tier="standard"),
                "qwen2.5:7b",
            )
            self.assertEqual(
                select_optimal_chat_model("auto", ["qwen2.5:7b", "qwen2.5:3b"], task_tier="standard"),
                "qwen2.5:3b",
            )

        # 2. Nhận diện đúng câu hỏi tổng quan toàn file nhưng không bắt nhầm câu hỏi tra cứu chi tiết
        self.assertTrue(is_global_summary_query("File này chứa nội dung gì, hãy nói chi tiết"))
        self.assertFalse(is_global_summary_query("File này có công thức hình nón cụt không?"))
        self.assertFalse(is_global_summary_query("Nội dung chương 9 là gì?"))

        # 3. _sanitize_rag_output KHÔNG được nuốt 180 ký tự văn bản thật sau `[Tài liệu n]: ...`
        long_rag = (
            "[Tài liệu 1]: Chuyên đề Những hằng đẳng thức đáng nhớ gồm 7 hằng đẳng thức cơ bản.\n"
            "[Tài liệu 2]: Gồm các bài tập vận dụng 7 hằng đẳng thức đáng nhớ để khai triển, biến đổi đa thức và việc thực hiện phép tính và rút gọn biểu thức.\n"
            "[Tài liệu 3]: Ngoài ra tài liệu còn hướng dẫn các dạng bài tập nâng cao như chứng minh đẳng thức và nhiều bài toán Tính giá trị của biểu thức.\n"
            "### Tài liệu trích dẫn:\n"
        )
        cleaned = _sanitize_rag_output(long_rag, citations_count=4)
        self.assertIn("Những hằng đẳng thức đáng nhớ", cleaned)
        self.assertIn("việc thực hiện phép tính và rút gọn biểu thức", cleaned)
        self.assertIn("Tính giá trị của biểu thức", cleaned)
        self.assertNotRegex(cleaned, r"(?:^|\s|\])nh\s+giá\s+trị")
        self.assertNotIn("### Tài liệu trích dẫn:", cleaned)

        # 4. Follow-up suggestions cho tài liệu toán học không dùng "quy định cụ thể những gì?" hay vỡ dòng
        math_chunks = [
            {
                "document_name": "chuyen-de-nhung-hang-dang-thuc-dang-nho-3812.pdf",
                "content": (
                    "A. LÝ THUYẾT:\n"
                    "1. Bình phương của một tổng: (A + B)² = A² + 2AB + B²\n"
                    "Dạng 1: Biến đổi biểu thức\n"
                    "Bài 1: Thực hiện phép tính:\n1.\n\n3 3 2 1 1 1 9 27 a) Ta có\n"
                ),
            }
        ]
        math_sugs = _build_instant_followup_suggestions(
            "File này chứa nội dung gì, hãy nói chi tiết",
            [{"source_type": "document", "document_name": "chuyen-de-nhung-hang-dang-thuc-dang-nho-3812.pdf"}],
            math_chunks,
        )
        self.assertEqual(len(math_sugs), 3)
        self.assertFalse(any("quy định cụ thể" in s.lower() for s in math_sugs))
        self.assertFalse(any("\n" in s for s in math_sugs))

    def test_pdf_math_superscript_reconstruction(self) -> None:
        from pathlib import Path
        import pymupdf
        from app.services.document_service import _extract_pdf_page_clean_text

        sample_pdf = Path(
            r"D:\PBL6\sourcecode\backend\data\uploads\a53832cb-8f3a-4256-96f8-b0158a811d3c_chuyen-de-nhung-hang-dang-thuc-dang-nho-3812.pdf"
        )
        if not sample_pdf.exists():
            self.skipTest("Sample math PDF not present in local uploads")
        doc = pymupdf.open(str(sample_pdf))
        try:
            p1 = _extract_pdf_page_clean_text(doc[0])
        finally:
            doc.close()
        self.assertIn("1. Bình phương của một tổng: (A + B)² = A² + 2AB + B²", p1)
        self.assertIn("3. Hiệu hai bình phương: A² - B² = (A - B)(A + B)", p1)

    def test_pinpoint_ordinal_item_hits_formula_1_instead_of_3(self) -> None:
        from app.services.llm_service import _extract_pinpointed_answer_sentences, _sanitize_rag_output

        chunks = [
            {
                "content": (
                    "A. LÝ THUYẾT:\n"
                    "1. Bình phương của một tổng: (A + B)² = A² + 2AB + B²\n"
                    "2. Bình phương của một hiệu: (A - B)² = A² - 2AB + B²\n"
                    "3. Bình phương của tổng 3 số hạng:\n"
                    "(A + B + C)² = A² + B² + C² + 2(AB + BC + CA)\n"
                )
            }
        ]
        pin = _extract_pinpointed_answer_sentences("hằng đẳng thức số 1 là gì", chunks) or ""
        self.assertIn("1. Bình phương của một tổng: (A + B)² = A² + 2AB + B²", pin)
        self.assertNotIn("3. Bình phương của tổng 3 số hạng", pin)
        self.assertEqual(
            _sanitize_rag_output("[H1] Bình phương của một tổng là (A + B)² = A² + 2AB + B² [1]", 1),
            "Bình phương của một tổng là (A + B)² = A² + 2AB + B² [1]",
        )

    def test_p0_audit_remediations_local_only_intent_sandbox_cjk(self) -> None:
        from app.services.ai_router import _detect_web_intent, _resolve_routing_modes
        from app.services.intent_service import classify_chat_intent
        from app.services.llm_service import _try_build_exact_cjk_vocab_answer
        from app.services.python_sandbox_service import evaluate_python_sandbox

        # 1. local_only KHÔNG BAO GIỜ kích hoạt web search
        self.assertEqual(_resolve_routing_modes("local_only", "Trong kho tài liệu hiện tại có những tài liệu nào?"), (False, True))
        self.assertFalse(_detect_web_intent("Trong kho tài liệu hiện tại có những tài liệu nào?"))

        # 2. Intent: câu hỏi thông tin chứa 'trắc nghiệm' -> rag_qa; 'đề' nâng cao -> hard; viết ra Word -> compose_document
        self.assertEqual(
            classify_chat_intent("Bài kiểm tra trắc nghiệm trong tài liệu nói về nội dung gì?").kind,
            "rag_qa",
        )
        quiz_dec = classify_chat_intent("Tạo đề trắc nghiệm nâng cao chương 3 gồm 8 câu")
        self.assertEqual(quiz_dec.kind, "create_quiz")
        self.assertEqual(quiz_dec.params["question_count"], 8)
        self.assertEqual(quiz_dec.params["difficulty"], "hard")
        doc_dec = classify_chat_intent("Viết bảng tổng hợp công thức Toán 9 ra file Word docx")
        self.assertEqual(doc_dec.kind, "compose_document")
        self.assertEqual(doc_dec.params["default_export_format"], "docx")
        exp_dec = classify_chat_intent("Xuất câu trả lời vừa rồi ra file PDF giúp tôi")
        self.assertEqual(exp_dec.kind, "export_previous")

        # 3. Python Sandbox hỗ trợ ký hiệu Unicode π, ², ³, √ và chặn pow/int*list DoS
        sb = evaluate_python_sandbox({"R": 7, "h": 10}, ["C = round(2*π*R, 4)", "Sxq = round(2*π*R*h, 4)", "V = round(π*R²*h, 4)"])
        self.assertTrue(sb["ok"], sb.get("error"))
        self.assertAlmostEqual(sb["steps"][0]["value"], 43.9823, places=3)
        self.assertAlmostEqual(sb["steps"][1]["value"], 439.823, places=3)
        self.assertAlmostEqual(sb["steps"][2]["value"], 1539.3804, places=3)
        self.assertFalse(evaluate_python_sandbox({}, ["pow(10, 10000000)"])["ok"])
        self.assertFalse(evaluate_python_sandbox({}, ["1000000 * [0]"])["ok"])

        # 4. Tra cứu CJK ngắn trả về 100% tiếng Việt chuẩn xác, không rò tiếng Trung
        cjk_ans = _try_build_exact_cjk_vocab_answer(
            "後半 là gì",
            [{"document_name": "Mimikara N3.xlsx", "content": "12 | 後半 | こうはん | phần cuối"}],
        )
        self.assertIsNotNone(cjk_ans)
        self.assertIn("こうはん", cjk_ans or "")
        self.assertIn("phần cuối", cjk_ans or "")
        self.assertNotIn("是指", cjk_ans or "")


if __name__ == "__main__":
    unittest.main()
