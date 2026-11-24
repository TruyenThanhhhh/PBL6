"""Tests for AI Intelligence, Completeness & Naturalness upgrades: Roman/Legal section retrieval, bidirectional stitching, adaptive rescue query, web passage selection, overlap dedup, dynamic sampling, grounding audit, and export_previous + DB history fallback."""
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
from app.services.hardware_profile_service import set_selected_profile_mode  # noqa: E402
from app.services.intent_service import classify_chat_intent  # noqa: E402
from app.services.llm_service import (  # noqa: E402
    _build_instant_followup_suggestions,
    _deduplicate_chunk_overlap,
    _extract_pinpointed_answer_sentences,
    _prepare_rag_prompts_and_citations,
    _resolve_sampling_options,
    _sanitize_rag_output,
    decode_symbol_pua_text,
    select_optimal_chat_model,
)
from app.services.python_sandbox_service import evaluate_python_sandbox  # noqa: E402
from app.services.reasoning_service import (  # noqa: E402
    _audit_reasoning_grounding,
    _fast_local_reasoning_planner,
)
from app.services.retrieval_service import (  # noqa: E402
    _build_rescue_query,
    detect_positional_intent,
    detect_section_intent,
    expand_and_stitch_chunks,
    invalidate_workspace_vector_cache,
    is_global_summary_query,
    search_relevant_chunks,
    search_section_chunks,
)
from app.services.web_search_service import MainContentExtractor  # noqa: E402


def _zero_embed(texts):
    # Vector đồng nhất để cô lập kiểm thử phần từ khóa/adaptive rescue mà không dựa vào vector match giả
    return [[1.0, 0.0, 0.0] for _ in texts]


class Group3AIIntelligenceAndQualityTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp_dir.name)
        self.orig_db_path = db_mod.DATABASE_PATH
        self.orig_data_dir = db_mod.DATA_DIR
        self.orig_db_upload = db_mod.UPLOAD_DIR
        self.orig_doc_upload = doc_mod.UPLOAD_DIR

        db_mod.DATA_DIR = tmp_path / "data"
        db_mod.UPLOAD_DIR = db_mod.DATA_DIR / "uploads"
        db_mod.DATABASE_PATH = db_mod.DATA_DIR / "test_group3.db"
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

    def test_section_roman_and_legal_article_plus_bidirectional_stitching(self):
        self.assertEqual(detect_section_intent("Chương II tóm tắt thế nào?"), ("chương", 2))
        self.assertEqual(detect_section_intent("Điều 5 quy định về nội dung gì?"), ("điều", 5))
        self.assertFalse(is_global_summary_query("tóm tắt chương II"))

        content_chunks = [
            "Chương I: Giới thiệu chung về quy trình đào tạo nội bộ.",
            "Chương II: Quy định Kỷ luật và Hợp đồng.\nCác trường hợp áp dụng mức phạt gồm:",
            "phạt 8% giá trị hợp đồng nếu giao hàng quá 10 ngày không có lý do chính đáng.",
            "Chương III: Quy trình thanh quyết toán cuối kỳ.",
        ]
        conn = db_mod.get_db_connection()
        try:
            conn.execute(
                """
                INSERT INTO documents (id, workspace_id, file_name, file_type, file_size, file_path, total_pages, total_chunks, status, is_latest)
                VALUES ('doc_law', 'default', 'hop_dong_chuan.txt', 'txt', 1000, 'hop_dong_chuan.txt', 3, 4, 'ready', 1)
                """
            )
            for idx, txt in enumerate(content_chunks):
                cid = f"c_{idx}"
                conn.execute(
                    """
                    INSERT INTO document_chunks (id, document_id, workspace_id, chunk_index, page_number, content)
                    VALUES (?, 'doc_law', 'default', ?, ?, ?)
                    """,
                    (cid, idx, idx + 1, txt),
                )
            conn.commit()
        finally:
            conn.close()

        sec_chunks = search_section_chunks("default", "chương", 2, document_id="doc_law")
        joined_sec = "\n".join(c["content"] for c in sec_chunks)
        self.assertIn("Chương II", joined_sec)
        self.assertIn("phạt 8% giá trị", joined_sec)
        self.assertNotIn("Chương III", joined_sec)

        # Truyền chunk[2] (bắt đầu bằng chữ thường sau chunk[1] kết thúc bằng ':') -> tự động ghép ngược chunk[1]
        mid_hit = [
            {
                "chunk_id": "c_2",
                "document_id": "doc_law",
                "workspace_id": "default",
                "chunk_index": 2,
                "page_number": 3,
                "document_name": "hop_dong_chuan.txt",
                "content": content_chunks[2],
            }
        ]
        stitched = expand_and_stitch_chunks(mid_hit, max_total_chunks=4, max_total_chars=3000)
        self.assertEqual(len(stitched), 1)
        self.assertIn("Các trường hợp áp dụng mức phạt gồm:", stitched[0]["content"])
        self.assertIn("phạt 8% giá trị", stitched[0]["content"])
        self.assertEqual(stitched[0]["page_label"], "Trang 2 - 3")

    @patch("app.services.retrieval_service.rerank_documents", side_effect=lambda q, docs, top_k, **kw: docs[:top_k])
    @patch("app.services.retrieval_service.embed_texts", side_effect=_zero_embed)
    @patch("app.services.document_service.embed_texts", side_effect=_zero_embed)
    def test_adaptive_rescue_query_and_web_passage_relevance_filtering(self, _m_doc, _m_ret, _m_rerank):
        doc_mod.process_and_index_document(
            "default",
            "noi_quy_lao_dong.txt",
            "Điều 8: Kỷ luật thời gian làm việc — nhân viên chậm giờ quá 3 lần trong tháng sẽ bị khấu trừ 500000 đồng phụ cấp chuyên cần.".encode("utf-8"),
        )
        # Câu hỏi dùng từ đời thường ("đi muộn", "trừ lương") khác hoàn toàn từ vựng văn bản ("chậm giờ", "khấu trừ")
        hits = search_relevant_chunks("default", "đi muộn có bị trừ lương không?", top_k=3)
        self.assertTrue(hits)
        self.assertIn("khấu trừ 500000 đồng", hits[0]["content"])

        # Kiểm thử trích xuất đoạn web: nội dung đáp án nằm sâu ở đoạn cuối sau >2200 ký tự dẫn nhập
        filler_paras = "".join(
            f"<p>Đoạn dẫn nhập giới thiệu bối cảnh tổng quan kinh tế vĩ mô số {i} rất dài dòng và không chứa số liệu lãi suất điều hành năm mục tiêu cần tra cứu.</p>"
            for i in range(1, 20)
        )
        answer_para = "<p>Theo thông báo chính thức, lãi suất điều hành năm 2026 được giữ ổn định ở mức 4.5%/năm để hỗ trợ tăng trưởng tín dụng.</p>"
        html = f"<html><head><title>Báo cáo Tài chính 2026</title></head><body>{filler_paras}{answer_para}</body></html>"

        parser = MainContentExtractor()
        parser.feed(html)
        focused = parser.get_content(max_chars=1200, query="lãi suất điều hành năm 2026 bao nhiêu")
        self.assertIn("4.5%/năm", focused)
        self.assertLessEqual(len(focused), 1205)

    def test_overlap_dedup_dynamic_sampling_and_reasoning_grounding_audit(self):
        overlap = "Điều khoản thanh toán trong vòng 15 ngày kể từ khi nghiệm thu hoàn tất và bàn giao đủ hồ sơ."
        c1 = "Phần 1: Quy trình nghiệm thu bàn giao.\n" + overlap
        c2 = overlap + "\nPhần 2: Trường hợp quá hạn áp dụng lãi suất 0.05%/ngày."
        deduped = _deduplicate_chunk_overlap(c1, c2)
        self.assertNotIn("nghiệm thu hoàn tất", deduped)
        self.assertIn("Phần 2: Trường hợp quá hạn", deduped)

        chunks = [
            {"document_id": "d1", "document_name": "hd.txt", "page_number": 1, "chunk_index": 0, "content": c1},
            {"document_id": "d1", "document_name": "hd.txt", "page_number": 1, "chunk_index": 1, "content": c2},
        ]
        _sys, user_prompt, _cites = _prepare_rag_prompts_and_citations("lãi suất quá hạn là bao nhiêu?", chunks)
        context_only_part = user_prompt.split("🎯 [TRÍCH ĐOẠN")[0]
        self.assertEqual(context_only_part.count("nghiệm thu hoàn tất"), 1)

        precise_opts = _resolve_sampling_options("Điều 5 mức phạt tính bao nhiêu?", 4096, 1024, estimated_input_tokens=450)
        general_opts = _resolve_sampling_options("Hãy giải thích khái niệm kiến trúc hướng sự kiện và ưu điểm", 4096, 1024)
        self.assertEqual(precise_opts["temperature"], 0.20)
        self.assertEqual(precise_opts["num_ctx"], 1536)
        self.assertEqual(general_opts["temperature"], 0.45)

        pinpointed = _extract_pinpointed_answer_sentences("lãi suất quá hạn là bao nhiêu?", chunks)
        self.assertTrue(pinpointed)
        self.assertIn("0.05%/ngày", pinpointed)

        fast_plan = _fast_local_reasoning_planner(
            "Tính lãi kép 150 triệu lãi suất 6.8%/năm trong 5 năm và đánh giá rủi ro thanh khoản",
            chunks,
        )
        self.assertTrue(fast_plan["needs_calculation"])
        self.assertEqual(fast_plan["variables"]["von"], 150000000.0)
        self.assertTrue(fast_plan["expressions"])
        self.assertTrue(fast_plan["sub_queries"])

        sugs = _build_instant_followup_suggestions("lãi suất quá hạn là bao nhiêu?", [{"document_name": "hd.txt"}], chunks)
        self.assertEqual(len(sugs), 3)

        audited, extra_delta, detail = _audit_reasoning_grounding(
            "Căn cứ quy định [1] và nguồn ngoài [9], khoản tiền sau 2 năm đã được xét [2].",
            citations_count=2,
            sandbox_res={"ok": True, "final_result": 1123600},
        )
        self.assertNotIn("[9]", audited)
        self.assertIn("[1]", audited)
        self.assertIn("[2]", audited)
        self.assertIn("1.123.600", audited)
        self.assertIn("1.123.600", extra_delta)
        self.assertIn("loại bỏ 1 trích dẫn", detail)

    def test_export_previous_intent_and_db_history_fallback(self):
        exp = classify_chat_intent("xuất câu trả lời vừa rồi ra file Word")
        self.assertEqual(exp.kind, "export_previous")
        self.assertEqual(exp.params["default_export_format"], "docx")

        risk = classify_chat_intent("hợp đồng này có rủi ro hay điểm bất lợi nào không?")
        self.assertEqual(risk.kind, "deep_reasoning")

        with patch.dict(os.environ, {"DISABLE_MODEL_WARMUP": "1"}):
            client = TestClient(app)
            reg = client.post(
                "/api/v1/auth/register",
                json={"email": "prevexp@example.com", "password": "Password123!", "name": "Export Prev User"},
            )
            self.assertEqual(reg.status_code, 201)
            headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
            ws_id = client.post("/api/v1/workspaces", json={"name": "WS Followup"}, headers=headers).json()["workspace"]["id"]
            conv_id = client.post(
                f"/api/v1/workspaces/{ws_id}/conversations",
                json={"title": "Hội thoại Export"},
                headers=headers,
            ).json()["conversation"]["id"]

            # Lượt 1: Giả lập tin nhắn trợ lý đã lưu trong DB
            add_msg = client.post(
                f"/api/v1/conversations/{conv_id}/messages",
                json={
                    "role": "assistant",
                    "content": "# Quy chuẩn Nghiệm thu\nNội dung chi tiết quy chuẩn 2026.\n\n---GỢI Ý TIẾP THEO---\n- Chi tiết hơn",
                },
                headers=headers,
            )
            self.assertEqual(add_msg.status_code, 201, add_msg.text)

            # Lượt 2: Client KHÔNG gửi kèm mảng history -> backend tự lấy từ SQLite và đóng gói xuất Word tức thì
            stream_res = client.post(
                "/api/v1/chat/stream",
                json={
                    "workspace_id": ws_id,
                    "conversation_id": conv_id,
                    "query": "xuất câu trả lời vừa rồi ra file Word",
                },
                headers=headers,
            )
            self.assertEqual(stream_res.status_code, 200, stream_res.text)
            sse_body = stream_res.text
            self.assertIn('"action_type": "compose_document"', sse_body)
            self.assertIn("Quy chuẩn Nghiệm thu", sse_body)
            self.assertNotIn("---GỢI Ý TIẾP THEO---", sse_body.split('"markdown":')[-1])

    @patch("app.services.retrieval_service.rerank_documents", side_effect=lambda q, docs, top_k, **kw: docs[:top_k])
    @patch("app.services.retrieval_service.embed_texts", side_effect=_zero_embed)
    @patch("app.services.document_service.embed_texts", side_effect=_zero_embed)
    def test_accent_free_intents_tabular_analytics_and_document_outline(self, _m_doc, _m_ret, _m_rerank):
        # 1. Kiểm thử 100% câu hỏi tiếng Việt KHÔNG DẤU và phân tích sâu
        cases = [
            ("Tao 10 cau trac nghiem tu tai lieu nay", "create_quiz"),
            ("Tao 8 flashcard tu chuong II", "create_flashcards"),
            ("Xuat cau tra loi vua roi ra file word", "export_previous"),
            ("So sanh phien ban v1 va v2 cua quy che", "version_diff"),
            ("Tinh lai kep 150 trieu lai suat 6.8%/nam trong 5 nam", "deep_reasoning"),
            ("Phan tich nguyen nhan va danh gia rui ro thanh khoan", "deep_reasoning"),
            ("Phân tích nguyên nhân và đánh giá rủi ro thanh khoản", "deep_reasoning"),
        ]
        for query_str, expected_kind in cases:
            decision = classify_chat_intent(query_str)
            self.assertEqual(decision.kind, expected_kind, f"Failed for query: {query_str}")

        # 2. Kiểm thử Bảng dữ liệu lớn (Tabular Analytics Summary trên 120 dòng CSV)
        csv_lines = ["ChiNhanh,KhuVuc,DoanhThu,ChiPhi"]
        for i in range(1, 121):
            kv = "MienBac" if i % 2 == 0 else "MienNam"
            csv_lines.append(f"CN_{i:03d},{kv},1000,400")
        csv_bytes = "\n".join(csv_lines).encode("utf-8")

        doc_mod.process_and_index_document("default", "bao_cao_120_chi_nhanh.csv", csv_bytes)
        tab_hits = search_relevant_chunks(
            "default",
            "Tổng doanh thu toàn bảng của các chi nhánh là bao nhiêu?",
            top_k=3,
        )
        self.assertTrue(tab_hits)
        joined_tab = "\n".join(c["content"] for c in tab_hits)
        self.assertIn("[THỐNG KÊ TOÀN BẢNG DỮ LIỆU", joined_tab)
        self.assertIn("120 dòng dữ liệu", joined_tab)
        self.assertIn("Tổng cộng (SUM) = 120000", joined_tab)
        self.assertIn("Group-By Subtotals", joined_tab)
        self.assertIn("MienBac (60 dòng): SUM=60000", joined_tab)

        # 3. Kiểm thử Cây mục lục toàn tài liệu (Document Outline) cho tài liệu dài nhiều chương
        long_doc_sections = [
            f"Chương {idx}: Quy định quản trị hệ thống phân hệ số {idx}\n"
            + ("Nội dung chi tiết quy trình vận hành và kiểm soát rủi ro. " * 25)
            for idx in range(1, 9)
        ]
        long_doc_bytes = "\n\n".join(long_doc_sections).encode("utf-8")
        doc_mod.process_and_index_document("default", "quy_che_8_chuong.txt", long_doc_bytes)

        outline_hits = search_relevant_chunks(
            "default",
            "Mục lục và tổng quan tất cả các chương của quy chế gồm những gì?",
            top_k=3,
        )
        self.assertTrue(outline_hits)
        joined_outline = "\n".join(c["content"] for c in outline_hits)
        self.assertIn("[CÂY MỤC LỤC & TỔNG QUAN CẤU TRÚC TÀI LIỆU", joined_outline)
        self.assertIn("Chương 1:", joined_outline)
        self.assertIn("Chương 8:", joined_outline)

        # 4. Kiểm thử Hạng mục 4.1–4.3: Retrieval không dấu, Sanitize RAG output, và Adaptive Model Tiering
        self.assertEqual(detect_positional_intent("5 tu vung dau tien bat dau bang chu A"), ("start", "a"))
        self.assertTrue(is_global_summary_query("tom tat toan bo tai lieu"))
        self.assertIn("khấu trừ", _build_rescue_query("di muon co bi tru luong khong") or "")

        raw_3b_out = (
            "[1]: Điều kiện xét học bổng là GPA >= 3.60.\n"
            "[2]: Mức học bổng là 15.000.000 đồng/học kỳ.\n\n"
            "---GỢI Ý TIẾP THEO---\n"
            "- [Gợi ý 1] Điều kiện xét học bổng Khá là gì?\n"
            "- [Gợi ý 2]: Quy trình nộp hồ sơ ra sao?"
        )
        cleaned_out = _sanitize_rag_output(raw_3b_out, citations_count=1)
        self.assertNotIn("[2]", cleaned_out)
        self.assertIn("[1]", cleaned_out)
        self.assertNotIn("[Gợi ý 1]", cleaned_out)
        self.assertNotIn("[Gợi ý 2]", cleaned_out)
        self.assertIn("- Điều kiện xét học bổng Khá là gì?", cleaned_out)

        self.assertEqual(
            select_optimal_chat_model("auto", ["qwen2.5:7b", "qwen2.5:3b"], task_tier="fast"),
            "qwen2.5:3b",
        )
        self.assertEqual(
            select_optimal_chat_model("qwen2.5:7b", ["qwen2.5:7b", "qwen2.5:3b"], task_tier="standard"),
            "qwen2.5:7b",
        )

        # 5. Gợi ý theo loại tài liệu & làm sạch trích dẫn lồng tên file / câu lặp lại
        vocab_chunks = [
            {
                "document_name": "3000 TỪ TIẾNG ANH THÔNG DỤNG NHẤT.anhngumshoapdf.pdf",
                "content": 'allow v. /ə\'lau/ cho phép, để cho\nacknowledge v. /ək\'nɔlidʒ/ công nhận, thừa nhận',
            }
        ]
        vocab_sugs = _build_instant_followup_suggestions(
            "Lấy các từ vựng đầu tiên",
            [{"source_type": "document", "document_name": "3000 TỪ TIẾNG ANH THÔNG DỤNG NHẤT.anhngumshoapdf.pdf"}],
            vocab_chunks,
        )
        self.assertEqual(len(vocab_sugs), 3)
        self.assertFalse(any("ngoại lệ" in s.lower() for s in vocab_sugs))
        self.assertTrue(any("từ vựng" in s.lower() for s in vocab_sugs))

        noisy_vocab_ans = (
            'Câu hỏi của bạn là "Điều kiện ngoại lệ hoặc lưu ý quan trọng nào khác không?"\n\n'
            '[Tài liệu [1]: 3000 TỪ TIẾNG ANH THÔNG DỤNG NHẤT.anhngumshoapdf.pdf (Trang 2)] mô tả các từ như '
            '"allow v. /ə\'lau/ cho phép, để cho", và '
            '"[tài liệu [2]]: 3000 TỪ TIẾNG ANH THÔNG DỤNG NHẤT.anhngumshoapdf.pdf (Trang 1)" mô tả các từ như '
            '"acknowledge v. /ək\'nɔlidʒ/ công nhận, thừa nhận".\n\n'
            'Nếu bạn cần thêm thông tin cụ thể về điều kiện ngoại lệ, xin vui lòng cung cấp chi tiết hơn.'
        )
        sanitized_vocab = _sanitize_rag_output(noisy_vocab_ans, citations_count=2)
        self.assertNotIn("Câu hỏi của bạn là", sanitized_vocab)
        self.assertNotIn("3000 TỪ TIẾNG ANH THÔNG DỤNG NHẤT", sanitized_vocab)
        self.assertNotIn("xin vui lòng cung cấp chi tiết hơn", sanitized_vocab)
        self.assertIn("[1]", sanitized_vocab)
        self.assertIn("[2]", sanitized_vocab)

        # 6. Giải mã font Symbol MS Word PUA + LaTeX \frac/\sqrt/\pi + Hình học không gian Python Sandbox + không để TOC lấn át trang công thức
        pua_raw = "Thể tích:\n(\n)\n2\n2\n3\nV\nR\nr\nrR\nh\n\uf03d\n\uf02b\n\uf02b\n\uf070"
        decoded_pua = decode_symbol_pua_text(pua_raw)
        self.assertIn("π", decoded_pua)
        self.assertIn("=", decoded_pua)
        self.assertIn("+", decoded_pua)

        raw_latex_ans = (
            "V_{nóncút} = \\frac{24}{3}(15^2 + 15\\times 10 + 10^2)\\pi \\approx 11938.05\\text{ cm}^3, "
            "l = \\sqrt{(15 - 10)^2 + 24^2} = \\sqrt{601}"
        )
        cleaned_math = _sanitize_rag_output(raw_latex_ans, citations_count=1)
        self.assertNotIn("\\frac", cleaned_math)
        self.assertNotIn("\\sqrt", cleaned_math)
        self.assertNotIn("\\pi", cleaned_math)
        self.assertNotIn("\\approx", cleaned_math)
        self.assertIn("24/3", cleaned_math)
        self.assertIn("√601", cleaned_math)
        self.assertIn("π ≈", cleaned_math)

        leaked_sandbox = (
            "Các giá trị chính xác đã tính: duong_sinh_l = 24,5153; V_non_cut = 11.938,05\n"
            "[5] _Sổ tay tra cứu công thức toán 9.pdf (Trang 26) - [1]\n"
            "Kết quả: V_non_cut = 11.938,05 cm^3 và V_tru = 10.857,34 cm^3."
        )
        cleaned_leaked = _sanitize_rag_output(leaked_sandbox, citations_count=5)
        self.assertNotIn("Các giá trị chính xác đã tính", cleaned_leaked)
        self.assertNotIn("_Sổ tay tra cứu", cleaned_leaked)
        self.assertNotIn("duong_sinh_l", cleaned_leaked)
        self.assertIn("V(nón cụt)", cleaned_leaked)
        self.assertIn("V(hình trụ)", cleaned_leaked)

        geo_q = (
            "Dựa vào công thức Hình nón cụt và Hình trụ trong tài liệu, hãy tính thể tích và diện tích toàn phần "
            "của một cái xô hình nón cụt có bán kính hai đáy lần lượt là 15 cm và 10 cm, chiều cao 24 cm; "
            "sau đó so sánh xem thể tích của nó lớn hơn hay nhỏ hơn thể tích hình trụ tạo thành khi quay hình chữ nhật "
            "ABCD (AB = 24 cm, BC = 12 cm) quanh cạnh AB bao nhiêu phần trăm?"
        )
        geo_plan = _fast_local_reasoning_planner(geo_q, [])
        self.assertTrue(geo_plan["needs_calculation"])
        geo_sb = evaluate_python_sandbox(geo_plan["variables"], geo_plan["expressions"])
        self.assertTrue(geo_sb["ok"])
        step_map = {st["target"]: st["value"] for st in geo_sb["steps"]}
        self.assertAlmostEqual(step_map["V_non_cut"], 11938.0521, places=2)
        self.assertAlmostEqual(step_map["V_tru"], 10857.3442, places=2)
        self.assertAlmostEqual(step_map["chenh_lech_phan_tram"], 9.95, places=2)

        with patch("app.services.retrieval_service.embed_texts", side_effect=_zero_embed), \
             patch("app.services.retrieval_service.rerank_documents", side_effect=lambda q, docs, limit, **kw: docs[:limit]):
            conn = db_mod.get_db_connection()
            try:
                cur = conn.cursor()
                ws_id = "default"
                doc_id = "doc-toan9"
                cur.execute(
                    "INSERT INTO documents (id, workspace_id, file_name, file_type, file_size, file_path, total_chunks, status, total_pages, is_latest) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
                    (doc_id, ws_id, "[toanthaycu.com]_Sổ tay tra cứu công thức toán 9.pdf", "pdf", 1000, "toan9.pdf", 3, "indexed", 74),
                )
                toc_chunk = (
                    "MỤC LỤC\n"
                    "1. HÀM SỐ BẬC NHẤT ...................................................... 14\n"
                    "2. ĐỒ THỊ HÀM SỐ ........................................................ 21\n"
                    "3. GIẢI PHƯƠNG TRÌNH .................................................... 27\n"
                    "4. HÌNH HỌC KHÔNG GIAN .................................................. 68"
                )
                intro_chunk = "VẤN ĐỀ 1: CĂN THỨC\nTính giá trị biểu thức chứa căn bậc hai và rút gọn."
                frustum_chunk = (
                    "VẤN ĐỀ 18. HÌNH HỌC KHÔNG GIAN\n"
                    "2. Hình trụ - Bài toán 2: Quay hình chữ nhật ABCD quanh cạnh AB thì h = AB, R = BC.\n"
                    "3. Hình nón - Hình nón cụt: Diện tích xung quanh S_xq = π(R + r)l. Thể tích V = (πh/3)(R^2 + r^2 + Rr)."
                )
                for idx, (pg, txt) in enumerate([(2, toc_chunk), (6, intro_chunk), (70, frustum_chunk)]):
                    cid = f"c-{idx}"
                    cur.execute(
                        "INSERT INTO document_chunks (id, document_id, workspace_id, chunk_index, page_number, content, token_count) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (cid, doc_id, ws_id, idx, pg, txt, 50),
                    )
                    cur.execute(
                        "INSERT INTO chunks_fts (chunk_id, document_id, workspace_id, content) VALUES (?, ?, ?, ?)",
                        (cid, doc_id, ws_id, txt),
                    )
                conn.commit()
            finally:
                conn.close()

            invalidate_workspace_vector_cache("default")
            top_hits = search_relevant_chunks("default", geo_q, top_k=2)
            self.assertTrue(top_hits)
            self.assertEqual(top_hits[0]["page_number"], 70)

        # 7. Suy luận đa lĩnh vực (Kỹ thuật/Debug, Pháp lý, Tài chính ROI, Phản biện, Chiến lược)
        tech_plan = _fast_local_reasoning_planner(
            "Vì sao API RAG bị chậm khi chạy BGE-M3 trên máy 8GB RAM và cách tối ưu kiến trúc?",
            [{"content": "RAG pipeline"}],
        )
        self.assertEqual(tech_plan["domain"], "tech_debug")
        self.assertTrue(any("kiến trúc" in sq for sq in tech_plan["sub_queries"]))

        legal_plan = _fast_local_reasoning_planner(
            "Hợp đồng này có vi phạm quy định bồi thường hay điều khoản bất lợi nào không?",
            [{"content": "Điều 5"}],
        )
        self.assertEqual(legal_plan["domain"], "legal_policy")
        self.assertTrue(any("ngoại lệ" in sq for sq in legal_plan["sub_queries"]))

        roi_plan = _fast_local_reasoning_planner(
            "Tính tỷ suất lợi nhuận ROI khi doanh thu đạt 250 triệu và chi phí bỏ ra là 150 triệu?",
            [],
        )
        self.assertEqual(roi_plan["domain"], "finance_biz")
        roi_sb = evaluate_python_sandbox(roi_plan["variables"], roi_plan["expressions"])
        self.assertTrue(roi_sb["ok"])
        self.assertAlmostEqual(roi_sb["final_result"], 66.67, places=2)

        critique_plan = _fast_local_reasoning_planner(
            "Hãy phản biện và kiểm tra xem mục 17 có mâu thuẫn hay nhầm lẫn gì không?",
            [],
        )
        self.assertEqual(critique_plan["domain"], "academic_critique")

        self.assertEqual(classify_chat_intent("Vì sao hệ thống tìm kiếm bị chậm và tối ưu hiệu năng ra sao?").kind, "deep_reasoning")
        self.assertEqual(classify_chat_intent("Phát hiện mâu thuẫn và kiểm tra tính hợp lệ của tài liệu trên").kind, "deep_reasoning")
        self.assertEqual(classify_chat_intent("Hãy phản biện lập luận ở mục 15 và 17").kind, "deep_reasoning")

        # 8. Khử lặp đoạn văn/đề mục + dọn heading '**[1]' & chuẩn hóa chỉ số dưới x_1 -> x₁, ^2 -> ²
        loop_3b_out = (
            'Để đáp lại yêu cầu của bạn về nội dung chi tiết của phần "HÀM SỐ ĐỒNG BIẾN":\n\n'
            '### **[1]\n'
            '- Giả sử x_1 < x_2 và tính ( f(x_2) - f(x_1) )\n'
            '- Nếu (f(x_2) - f(x_1))/(x_2 - x_1) > 0, hàm số đồng biến.\n\n'
            '### **[2]\n'
            '- Giả sử x_1 < x_2 và tính ( f(x_2) - f(x_1) )\n'
            '- Nếu (f(x_2) - f(x_1))/(x_2 - x_1) > 0, hàm số đồng biến.\n'
            'Trích dẫn được thực hiện dựa trên thông tin trong tài liệu 1 và 2.'
        )
        deduped_ans = _sanitize_rag_output(loop_3b_out, citations_count=2)
        self.assertNotIn("Để đáp lại yêu cầu", deduped_ans)
        self.assertNotIn("**[1]", deduped_ans)
        self.assertNotIn("Trích dẫn được thực hiện", deduped_ans)
        self.assertEqual(deduped_ans.count("hàm số đồng biến"), 1)
        self.assertIn("x₁", deduped_ans)
        self.assertIn("x₂", deduped_ans)

        # Kiểm tra a_1x -> a₁x, \infty -> ∞, \arctan -> arctan và khử công thức lặp cụt đuôi
        math_sub_txt = (
            "Góc giữa hai đường thẳng y = a_1x + b_1 và y = a_2x + b_2 là α = \\arctan|a_1 - a_2|.\n"
            "Kẻ OH \\perp AB, công thức góc: a = tan{α}.\n"
            "Hệ số góc của đường thẳng là: k = (y_2 - y_1)/(x_2 - x_1).\n"
            "Khi x → -\\infty thì không đạt.\n"
            "k = (y_2 - y_1)/(x_2 - x_1)\n"
            "Hãy đối chiếu tài liệu [1] và kết luận trọng tâm chương 3"
        )
        cleaned_sub = _sanitize_rag_output(math_sub_txt, citations_count=1)
        self.assertIn("a₁x", cleaned_sub)
        self.assertIn("a₂x", cleaned_sub)
        self.assertIn("OH ⊥ AB", cleaned_sub)
        self.assertIn("tan(α)", cleaned_sub)
        self.assertNotIn("Hãy đối chiếu tài liệu", cleaned_sub)
        self.assertIn("arctan", cleaned_sub)
        self.assertIn("-∞", cleaned_sub)
        self.assertEqual(cleaned_sub.count("y₂ - y₁"), 1)

        leaked_footer_out = (
            "Phương pháp chung gồm 3 bước [1].\n\n"
            "Câu hỏi/Yêu cầu của người dùng: nội dung của chương 9\n\n"
            "Hãy đối chiếu tài liệu và trả lời trực diện, đúng trọng tâm câu hỏi, gắn nhãn trích dẫn 1, 2... tương ứng: [9. HAI ĐƯỜNG THẲNG]: Phương pháp chung:;"
        )
        cleaned_footer = _sanitize_rag_output(leaked_footer_out, citations_count=1)
        self.assertEqual(cleaned_footer, "Phương pháp chung gồm 3 bước [1].")

        # 9. Kiểm tra đọc nối tiếp trọn vẹn mục 9 (a..f) qua nhiều chunk và tự dừng trước mục 10
        conn = db_mod.get_db_connection()
        try:
            cur = conn.cursor()
            sec_doc = "doc-sec9"
            cur.execute(
                "INSERT INTO documents (id, workspace_id, file_name, file_type, file_size, file_path, total_chunks, status, total_pages, is_latest) VALUES (?, 'default', 'toan9_sec.pdf', 'pdf', 500, 'toan9_sec.pdf', 3, 'indexed', 20, 1)",
                (sec_doc,),
            )
            sec_chunks = [
                (17, "8. VỊ TRÍ TƯƠNG ĐỐI: Cắt nhau a1 != a2.\n9. HAI ĐƯỜNG THẲNG CẮT NHAU THOẢ MÃN ĐIỀU KIỆN K\nPhương pháp chung: Bước 1 Tìm m."),
                (18, "a) Thuộc góc phần tư I: x > 0, y > 0.\nb) Cắt nhau trên Ox: A ≡ B."),
                (19, "f) Cắt nhau tại điểm tọa độ nguyên.\n10. LẬP PHƯƠNG TRÌNH ĐƯỜNG THẲNG:\nĐi qua hai điểm A, B."),
            ]
            for idx, (pg, txt) in enumerate(sec_chunks):
                cid = f"sec9-{idx}"
                cur.execute(
                    "INSERT INTO document_chunks (id, document_id, workspace_id, chunk_index, page_number, content, token_count) VALUES (?, ?, 'default', ?, ?, ?, 40)",
                    (cid, sec_doc, idx, pg, txt),
                )
                cur.execute(
                    "INSERT INTO chunks_fts (chunk_id, document_id, workspace_id, content) VALUES (?, ?, 'default', ?)",
                    (cid, sec_doc, txt),
                )
            conn.commit()
        finally:
            conn.close()

        with patch("app.services.retrieval_service.embed_texts", side_effect=_zero_embed), \
             patch("app.services.retrieval_service.rerank_documents", side_effect=lambda q, docs, limit, **kw: docs[:limit]):
            sec9_hits = search_relevant_chunks(
                "default",
                "nội dung của chương 9 . HAI ĐƯỜNG THẲNG CẮT NHAU THOẢ MÃN ĐIỀU KIỆN K",
                document_id="doc-sec9",
                top_k=4,
            )
            joined_sec9 = "\n".join(c["content"] for c in sec9_hits)
            self.assertIn("9. HAI ĐƯỜNG THẲNG CẮT NHAU", joined_sec9)
            self.assertIn("a) Thuộc góc phần tư I", joined_sec9)
            self.assertIn("f) Cắt nhau tại điểm tọa độ nguyên", joined_sec9)
            self.assertNotIn("8. VỊ TRÍ TƯƠNG ĐỐI", joined_sec9)
            self.assertNotIn("10. LẬP PHƯƠNG TRÌNH", joined_sec9)


if __name__ == "__main__":
    unittest.main()
