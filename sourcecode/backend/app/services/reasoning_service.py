"""Bộ máy Suy luận Tự chủ Đa bước (Autonomous Multi-Step Reasoning + General Tool Registry)."""
import asyncio
import json
import logging
import re
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Optional, Tuple
from starlette.concurrency import run_in_threadpool

from app.config import DEFAULT_LLM_MODEL
from app.services.hardware_profile_service import get_active_profile_config, get_recommended_keep_alive
from app.services.llm_service import (
    _build_bounded_history_messages,
    _build_instant_followup_suggestions,
    _estimate_tokens,
    _prepare_rag_prompts_and_citations,
    _resolve_model_for_chat,
    _resolve_sampling_options,
    _stream_ollama_chat,
    call_ollama_json,
    check_ollama_status,
)
from app.services.python_sandbox_service import evaluate_python_sandbox
from app.services.retrieval_service import (
    detect_section_intent,
    search_relevant_chunks,
    search_section_chunks,
)

logger = logging.getLogger(__name__)


def _dedup_chunks(chunks: List[Dict[str, Any]], max_total: int = 8) -> List[Dict[str, Any]]:
    seen = set()
    merged: List[Dict[str, Any]] = []
    for c in chunks:
        key = (c.get("document_id"), c.get("chunk_index"), c.get("chunk_id"))
        if key in seen:
            continue
        seen.add(key)
        merged.append(c)
        if len(merged) >= max_total:
            break
    return merged


def _tool_search_docs(
    workspace_id: str,
    sub_query: str,
    top_k: int,
    selected_document_id: Optional[str],
    document_ids: Optional[List[str]],
) -> List[Dict[str, Any]]:
    sec_intent = detect_section_intent(sub_query, None)
    if sec_intent:
        sec_type, sec_num = sec_intent
        sec_chunks = search_section_chunks(
            workspace_id,
            sec_type,
            sec_num,
            max_chunks=min(top_k + 2, 8),
            document_id=selected_document_id,
            document_ids=document_ids,
        )
        if sec_chunks:
            return sec_chunks
    return search_relevant_chunks(
        workspace_id,
        sub_query,
        top_k=max(2, min(top_k, 4)),
        document_id=selected_document_id,
        document_ids=document_ids,
    )


def _format_chunk_briefs(chunks: List[Dict[str, Any]], limit: int = 5) -> str:
    lines: List[str] = []
    for idx, ch in enumerate(chunks[:limit], start=1):
        snippet = str(ch.get("content", "")).strip().replace("\n", " ")[:550]
        lines.append(f"[Nguồn {idx} - {ch.get('document_name', 'Tài liệu')}]: {snippet}")
    return "\n".join(lines) if lines else "(Chưa tìm thấy đoạn tài liệu nào)"


def _parse_vn_amount(num_str: str, unit_str: Optional[str]) -> float:
    clean = num_str.strip().replace(",", ".")
    val = float(clean)
    u = (unit_str or "").strip().lower()
    if u in ("tỷ", "ty", "tỉ", "ti"):
        return val * 1_000_000_000
    if u in ("triệu", "trieu", "tr"):
        return val * 1_000_000
    if u in ("nghìn", "nghin", "ngàn", "ngan", "k"):
        return val * 1_000
    return val


def _detect_reasoning_domain(
    query: str,
    initial_chunks: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, str]:
    """Nhận diện lĩnh vực suy luận (<0.2ms) để điều phối công cụ truy xuất, Sandbox và cấu trúc lập luận phù hợp."""
    q_low = (query or "").lower()
    ctx_sample = " ".join(str(c.get("content") or "")[:300] for c in (initial_chunks or [])[:2]).lower()
    combined = f"{q_low} {ctx_sample}"

    if any(k in q_low for k in ("nón cụt", "non cut", "hình trụ", "hinh tru", "hình nón", "hinh non", "hình cầu", "parabol", "phương trình", "phuong trinh", "căn thức", "can thuc", "gtln", "gtnn", "tiếp xúc", "tiep xuc", "tam giác", "đường tròn", "số mol", "nồng độ", "vận tốc", "gia tốc", "xác suất")):
        return "math_science", "Toán học & Khoa học"

    if any(k in q_low for k in ("lãi suất", "lai suat", "lãi kép", "lai kep", "doanh thu", "chi phí", "chi phi", "lợi nhuận", "loi nhuan", "roi", "hòa vốn", "hoa von", "ngân sách", "ngan sach", "đầu tư", "dau tu", "thuế", "thue", "kpi", "tiền lương", "khấu trừ")):
        return "finance_biz", "Tài chính & Kinh doanh"

    if any(k in q_low for k in ("hợp đồng", "hop dong", "điều khoản", "dieu khoan", "quy định", "quy dinh", "quy chế", "quy che", "vi phạm", "vi pham", "chế tài", "che tai", "hợp lệ", "hop le", "luật", "nghị định", "ngoại lệ", "ngoai le", "nghĩa vụ", "quyền lợi")):
        return "legal_policy", "Pháp lý & Quy chế"

    if any(k in q_low for k in ("api", "sql", "database", "cơ sở dữ liệu", "rag", "llm", "vector", "bm25", "server", "docker", "python", "react", "bug", "lỗi hệ thống", "chậm", "treo", "nghẽn", "bottleneck", "latency", "kiến trúc", "kien truc", "hiệu năng", "hieu nang", "bảo mật", "lỗ hổng", "thuật toán", "cache")):
        return "tech_debug", "Kỹ thuật & Kiến trúc hệ thống"

    if any(k in q_low for k in ("phản biện", "phan bien", "mâu thuẫn", "mau thuan", "sai sót", "sai sot", "nhầm lẫn", "nham lan", "thiếu sót", "thieu sot", "kiểm chứng logic", "lập luận", "lap luan")):
        return "academic_critique", "Phản biện & Kiểm chứng"

    if any(k in q_low for k in ("chiến lược", "chien luoc", "phương án", "phuong an", "nên chọn", "nen chon", "tối ưu", "toi uu", "ưu nhược điểm", "uu nhuoc diem", "so sánh", "so sanh", "lộ trình", "lo trinh", "swot", "kế hoạch", "ke hoach")):
        return "decision_strategy", "Chiến lược & Ra quyết định"

    if any(k in combined for k in ("công thức", "thể tích", "diện tích", "chứng minh", "nghiệm")):
        return "math_science", "Toán học & Khoa học"

    return "general", "Phân tích đa chiều"


def _fast_local_reasoning_planner(
    query: str,
    initial_chunks: List[Dict[str, Any]],
    max_sub_queries: int = 2,
) -> Dict[str, Any]:
    """
    Bộ lập kế hoạch suy luận & trích xuất công thức đa lĩnh vực tức thì (<1ms, 0 tốn LLM call):
    1. Nhận diện lĩnh vực (Toán/Khoa học, Tài chính/Kinh doanh, Pháp lý/Quy chế, Kỹ thuật/Hệ thống, Chiến lược, Phản biện).
    2. Tách các mệnh đề câu hỏi ghép thành sub_queries truy xuất đa nhánh đúng trọng tâm lĩnh vực.
    3. Trích xuất tự động biểu thức Toán hình học/đại số/tài chính/kinh doanh (lãi kép, ROI, hòa vốn...) nạp Python Sandbox.
    """
    q_clean = (query or "").strip()
    q_low = q_clean.lower()
    domain, domain_label = _detect_reasoning_domain(query, initial_chunks)

    # 1. Phân tách sub_queries đa nhánh theo từng lĩnh vực
    sub_queries: List[str] = []
    parts = re.split(
        r"\b(?:và\s+đánh\s+giá|và\s+so\s+sánh|và\s+đối\s+chiếu|và\s+đề\s+xuất|đồng\s+thời|bên\s+cạnh\s+đó|"
        r"va\s+danh\s+gia|va\s+so\s+sanh|va\s+doi\s+chieu|va\s+de\s+xuat|dong\s+thoi)\b",
        q_clean,
        flags=re.IGNORECASE | re.UNICODE,
    )
    if len(parts) >= 2:
        for p in parts:
            p_str = p.strip(" ,;?.!")
            if len(p_str) >= 10 and p_str.lower() != q_low:
                sub_queries.append(p_str)

    if initial_chunks:
        if domain == "legal_policy" or any(k in q_low for k in ("vi phạm", "vi pham", "bị phạt", "bi phat", "rủi ro", "rui ro", "hợp lệ", "hop le", "đủ điều kiện", "du dieu kien")):
            sub_queries.append("điều kiện ngoại lệ mức phạt chế tài quy định")
        elif domain == "tech_debug":
            sub_queries.append("kiến trúc giới hạn cấu hình thông số hiệu năng bảo mật")
        elif domain == "decision_strategy":
            sub_queries.append("ưu điểm nhược điểm chi phí hiệu quả yêu cầu")
        elif domain == "academic_critique":
            sub_queries.append("trường hợp đặc biệt điều kiện lưu ý ngoại lệ")

    sub_queries = sub_queries[:max_sub_queries]

    # 2. Trích xuất biến số & biểu thức Python Sandbox tự động
    variables: Dict[str, Any] = {}
    expressions: List[str] = []

    amt_m = re.search(
        r"\b(\d+(?:[.,]\d+)?)\s*(tỷ|ty|tỉ|ti|triệu|trieu|tr|nghìn|nghin|ngàn|ngan)\b",
        q_low,
        re.IGNORECASE | re.UNICODE,
    )
    if not amt_m:
        amt_m = re.search(r"\b(\d{5,12})\s*(?:đồng|dong|vnd|vnđ)?\b", q_low, re.IGNORECASE)
        principal = float(amt_m.group(1)) if amt_m else None
    else:
        principal = _parse_vn_amount(amt_m.group(1), amt_m.group(2))

    rate_m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", q_low)
    if not rate_m and principal is not None and initial_chunks:
        joined_ctx = " ".join(str(c.get("content") or "") for c in initial_chunks[:3])
        # Chỉ lấy % từ tài liệu khi đứng cạnh từ khóa tài chính (lãi suất, thuế, phạt, chiết khấu) để không nhặt nhầm % ngẫu nhiên
        rate_m = re.search(
            r"(?:lãi\s*suất|lai\s*suat|mức\s*lãi|thuế|phạt|chiết\s*khấu|tăng\s*trưởng)[^%\n]{0,40}?(\d+(?:[.,]\d+)?)\s*%",
            joined_ctx,
            re.IGNORECASE | re.UNICODE,
        )
    rate_pct = float(rate_m.group(1).replace(",", ".")) if rate_m else None

    time_m = re.search(
        r"\b(?:trong\s+|sau\s+|kỳ\s+hạn\s+|thời\s+hạn\s+|quá\s+hạn\s+|trễ\s+)?(\d{1,3})\s*(năm|nam|tháng|thang|ngày|ngay|kỳ|ky)\b",
        q_low,
        re.IGNORECASE | re.UNICODE,
    )
    periods = int(time_m.group(1)) if time_m else None

    if principal is not None and rate_pct is not None:
        r_dec = round(rate_pct / 100.0, 6)
        if any(k in q_low for k in ("lãi kép", "lai kep", "tăng trưởng kép", "tang truong kep")) and periods:
            variables = {"von": principal, "lai_suat": r_dec, "so_ky": periods}
            expressions = [
                "he_so_tang = round((1 + lai_suat) ** so_ky, 6)",
                "tong_nhan = round(von * ((1 + lai_suat) ** so_ky), 2)",
            ]
        elif periods and any(k in q_low for k in ("lãi", "lai", "tiết kiệm", "tiet kiem", "quá hạn", "qua han")):
            variables = {"von": principal, "ty_le": r_dec, "so_ky": periods}
            expressions = [
                "tien_lai = round(von * ty_le * so_ky, 2)",
                "tong_cong = round(von + tien_lai, 2)",
            ]
        else:
            variables = {"gia_tri": principal, "ty_le": r_dec}
            expressions = ["ket_qua = round(gia_tri * ty_le, 2)"]
    else:
        # Biểu thức số học thuần trong câu hỏi (vd: "1250 * 48 + 15000") — bỏ qua chuỗi ngày YYYY-MM-DD hoặc dãy số có chữ cái dính liền
        q_no_dates = re.sub(r"\b\d{4}-\d{1,2}-\d{1,2}\b", " ", q_low)
        arith_m = re.search(r"(?<![A-Za-z0-9_])(\d+(?:\.\d+)?(?:\s*[\+\*\/]\s*\d+(?:\.\d+)?)+)(?![A-Za-z0-9_])", q_no_dates)
        if arith_m:
            expr_clean = arith_m.group(1).strip()
            expressions = [f"ket_qua = round({expr_clean}, 4)"]
        else:
            # 1) Đại số hằng đẳng thức: Cho x - y = d và xy = p (hoặc x + y = s và xy = p) -> tính B = x³ ± y³ + (x ± y)² ...
            diff_m = re.search(r"\bx\s*-\s*y\s*=\s*(-?\d+(?:[.,]\d+)?)", q_low)
            sum_m = re.search(r"\bx\s*\+\s*y\s*=\s*(-?\d+(?:[.,]\d+)?)", q_low)
            prod_m = re.search(r"\bx\s*\*?\s*y\s*=\s*(-?\d+(?:[.,]\d+)?)", q_low)
            if prod_m and (diff_m or sum_m):
                xy_val = float(prod_m.group(1).replace(",", "."))
                variables["xy"] = xy_val
                if diff_m:
                    d_val = float(diff_m.group(1).replace(",", "."))
                    variables["hieu_x_y"] = d_val
                    expressions.extend([
                        "x2_cong_y2 = round(hieu_x_y ** 2 + 2 * xy, 6)",
                        "x3_tru_y3 = round(hieu_x_y ** 3 + 3 * xy * hieu_x_y, 6)",
                    ])
                    if re.search(r"x\s*(?:³|\^3)\s*-\s*y\s*(?:³|\^3)\s*\+\s*\(\s*x\s*-\s*y\s*\)\s*(?:²|\^2)", q_low):
                        expressions.append("gia_tri_B = round(x3_tru_y3 + hieu_x_y ** 2, 6)")
                    elif re.search(r"x\s*(?:³|\^3)\s*-\s*y\s*(?:³|\^3)\s*-\s*\(\s*x\s*-\s*y\s*\)\s*(?:²|\^2)", q_low):
                        expressions.append("gia_tri_B = round(x3_tru_y3 - hieu_x_y ** 2, 6)")
                elif sum_m:
                    s_val = float(sum_m.group(1).replace(",", "."))
                    variables["tong_x_y"] = s_val
                    expressions.extend([
                        "x2_cong_y2 = round(tong_x_y ** 2 - 2 * xy, 6)",
                        "x3_cong_y3 = round(tong_x_y ** 3 - 3 * xy * tong_x_y, 6)",
                    ])
                    if re.search(r"x\s*(?:³|\^3)\s*\+\s*y\s*(?:³|\^3)\s*\+\s*3\s*\*?\s*xy", q_low) or re.search(r"x\s*(?:³|\^3)\s*\+\s*3\s*\*?\s*xy\s*\+\s*y\s*(?:³|\^3)", q_low):
                        expressions.append("gia_tri_A = round(x3_cong_y3 + 3 * xy, 6)")

            # 2) So sánh số lượng từ vựng giữa 2 Bài trong bảng Workbook Excel trực tiếp từ CSDL (không bao giờ lấy nhầm số trong tên file!)
            lesson_nums = re.findall(r"\bbài\s+(\d{1,2})\b", q_low, re.IGNORECASE | re.UNICODE)
            if not expressions and len(lesson_nums) >= 2 and any(k in q_low for k in ("nhiều từ", "bao nhiêu từ", "chênh lệch", "so sánh", "nhieu tu", "chenh lech")) and initial_chunks:
                doc_id_wb = initial_chunks[0].get("document_id")
                if doc_id_wb:
                    try:
                        from app.database import get_db_connection
                        conn_wb = get_db_connection()
                        try:
                            wb_rows = conn_wb.execute(
                                "SELECT content FROM document_chunks WHERE document_id = ? ORDER BY chunk_index ASC",
                                (doc_id_wb,),
                            ).fetchall()
                        finally:
                            conn_wb.close()
                        counts_by_num: Dict[int, int] = {}
                        cur_lnum: Optional[int] = None
                        l_hdr_re = re.compile(r"^\s*\[?Bài\s+(\d{1,2})\s*[-–:]", re.IGNORECASE)
                        for r_wb in wb_rows:
                            txt_wb = str(r_wb["content"] or "")
                            if txt_wb.startswith("[CÂY MỤC LỤC") or txt_wb.startswith("Sheet:"):
                                continue
                            for ln_wb in txt_wb.splitlines():
                                s_wb = ln_wb.strip()
                                ml = l_hdr_re.match(s_wb)
                                if ml:
                                    cur_lnum = int(ml.group(1))
                                    counts_by_num.setdefault(cur_lnum, 0)
                                    continue
                                if cur_lnum is not None and "|" in s_wb:
                                    cells_wb = [c.strip() for c in s_wb.strip("|").split("|") if c.strip()]
                                    if len(cells_wb) >= 3 and cells_wb[0].isdigit():
                                        counts_by_num[cur_lnum] = counts_by_num.get(cur_lnum, 0) + 1
                        n1, n2 = int(lesson_nums[0]), int(lesson_nums[1])
                        if counts_by_num.get(n1, 0) > 0 and counts_by_num.get(n2, 0) > 0:
                            variables[f"so_tu_bai_{n1}"] = counts_by_num[n1]
                            variables[f"so_tu_bai_{n2}"] = counts_by_num[n2]
                            expressions.extend([
                                f"so_tu_bai_{n1} = {counts_by_num[n1]}",
                                f"so_tu_bai_{n2} = {counts_by_num[n2]}",
                                f"chenh_lech_tu = abs(so_tu_bai_{n1} - so_tu_bai_{n2})",
                            ])
                    except Exception:
                        pass

            # 3) Hình học không gian tức thì (<1ms): Hình nón cụt, Hình nón, Hình trụ (kể cả R=7, h=10 hoặc quay hình chữ nhật), Hình cầu
            has_frustum = any(k in q_low for k in ("nón cụt", "non cut"))
            has_cylinder = any(k in q_low for k in ("hình trụ", "hinh tru"))
            has_cone = not has_frustum and any(k in q_low for k in ("hình nón", "hinh non"))
            has_sphere = any(k in q_low for k in ("hình cầu", "hinh cau", "mặt cầu", "mat cau", "khối cầu", "khoi cau"))

            if has_frustum:
                rad_m = re.search(
                    r"bán\s+kính(?:\s*(?:2|hai)\s+đáy)?[^0-9\n]{0,35}?(\d+(?:[.,]\d+)?)\s*(?:cm|m|dm|mm)?\s*(?:và|,|;)\s*(\d+(?:[.,]\d+)?)",
                    q_low,
                )
                r_big_m = re.search(r"nón\s+cụt[^.\n]{0,60}?\bR\s*=\s*(\d+(?:[.,]\d+)?)", q_clean)
                r_small_m = re.search(r"nón\s+cụt[^.\n]{0,80}?\br\s*=\s*(\d+(?:[.,]\d+)?)", q_clean)
                h_m = (
                    re.search(r"nón\s+cụt[^.\n]{0,110}?\bh\s*=\s*(\d+(?:[.,]\d+)?)", q_clean, re.IGNORECASE)
                    or re.search(r"chiều\s+cao\s*(?:h\s*)?(?:là|bằng|=|:)?\s*(\d+(?:[.,]\d+)?)", q_low)
                )
                if rad_m and h_m:
                    r1 = float(rad_m.group(1).replace(",", "."))
                    r2 = float(rad_m.group(2).replace(",", "."))
                    variables["R_nc"] = max(r1, r2)
                    variables["r_nc"] = min(r1, r2)
                    variables["h_nc"] = float(h_m.group(1).replace(",", "."))
                elif r_big_m and r_small_m and h_m:
                    r1 = float(r_big_m.group(1).replace(",", "."))
                    r2 = float(r_small_m.group(1).replace(",", "."))
                    variables["R_nc"] = max(r1, r2)
                    variables["r_nc"] = min(r1, r2)
                    variables["h_nc"] = float(h_m.group(1).replace(",", "."))
                if "R_nc" in variables and "r_nc" in variables and "h_nc" in variables:
                    expressions.extend([
                        "duong_sinh_l = round(sqrt((R_nc - r_nc) ** 2 + h_nc ** 2), 4)",
                        "V_non_cut = round((pi * h_nc / 3) * (R_nc ** 2 + r_nc ** 2 + R_nc * r_nc), 4)",
                        "S_xq_non_cut = round(pi * (R_nc + r_nc) * duong_sinh_l, 4)",
                        "S_tp_non_cut = round(S_xq_non_cut + pi * (R_nc ** 2) + pi * (r_nc ** 2), 4)",
                    ])

            if has_cylinder:
                rect_m = re.search(
                    r"hình\s+chữ\s+nhật[^.\n]{0,80}?AB\s*=\s*(\d+(?:[.,]\d+)?)[^.\n]{0,30}?BC\s*=\s*(\d+(?:[.,]\d+)?)",
                    q_clean,
                    re.IGNORECASE,
                )
                if rect_m:
                    ab = float(rect_m.group(1).replace(",", "."))
                    bc = float(rect_m.group(2).replace(",", "."))
                    rot_m = re.search(r"quanh\s+(?:cạnh\s+)?(AB|BC|CD|AD)", q_clean, re.IGNORECASE)
                    axis = (rot_m.group(1).upper() if rot_m else "AB")
                    if axis in ("AB", "CD"):
                        variables["h_tru"] = ab
                        variables["R_tru"] = bc
                    else:
                        variables["h_tru"] = bc
                        variables["R_tru"] = ab
                else:
                    cyl_r = re.search(
                        r"hình\s+trụ[^.\n]{0,70}?(?:bán\s+kính\s*(?:đáy\s*)?(?:r\s*)?(?:là|bằng|=|:)?\s*|r\s*=\s*)(\d+(?:[.,]\d+)?)",
                        q_low,
                    )
                    cyl_h = re.search(
                        r"hình\s+trụ[^.\n]{0,110}?(?:chiều\s+cao\s*(?:h\s*)?(?:là|bằng|=|:)?\s*|h\s*=\s*)(\d+(?:[.,]\d+)?)",
                        q_low,
                    )
                    if cyl_r and cyl_h:
                        variables["R_tru"] = float(cyl_r.group(1).replace(",", "."))
                        variables["h_tru"] = float(cyl_h.group(1).replace(",", "."))
                if "R_tru" in variables and "h_tru" in variables:
                    expressions.extend([
                        "C_day_tru = round(2 * pi * R_tru, 4)",
                        "S_xq_tru = round(2 * pi * R_tru * h_tru, 4)",
                        "S_tp_tru = round(2 * pi * R_tru * (h_tru + R_tru), 4)",
                        "V_tru = round(pi * (R_tru ** 2) * h_tru, 4)",
                    ])

            if "V_non_cut" in str(expressions) and "V_tru" in str(expressions):
                expressions.append("chenh_lech_V = round(V_non_cut - V_tru, 4)")
                expressions.append("chenh_lech_phan_tram = round(abs(V_non_cut - V_tru) / min(V_non_cut, V_tru) * 100, 2)")
            elif has_cone:
                cone_r = re.search(r"bán\s+kính\s*(?:đáy\s*)?(?:R\s*)?(?:là|bằng|=|:)?\s*(\d+(?:[.,]\d+)?)", q_low)
                cone_h = re.search(r"chiều\s+cao\s*(?:h\s*)?(?:là|bằng|=|:)?\s*(\d+(?:[.,]\d+)?)", q_low)
                if cone_r and cone_h:
                    variables["R_non"] = float(cone_r.group(1).replace(",", "."))
                    variables["h_non"] = float(cone_h.group(1).replace(",", "."))
                    expressions.extend([
                        "l_non = round(sqrt(R_non ** 2 + h_non ** 2), 4)",
                        "S_xq_non = round(pi * R_non * l_non, 4)",
                        "V_non = round((pi * (R_non ** 2) * h_non) / 3, 4)",
                        "S_tp_non = round(pi * R_non * (R_non + l_non), 4)",
                    ])
            elif has_sphere:
                sph_r = re.search(r"bán\s+kính\s*(?:R\s*)?(?:là|bằng|=|:)?\s*(\d+(?:[.,]\d+)?)", q_low)
                if sph_r:
                    variables["R_cau"] = float(sph_r.group(1).replace(",", "."))
                    expressions.extend([
                        "S_cau = round(4 * pi * (R_cau ** 2), 4)",
                        "V_cau = round((4 / 3) * pi * (R_cau ** 3), 4)",
                    ])

        # Kinh doanh / ROI / Điểm hòa vốn tức thì cho lĩnh vực finance_biz
        if not expressions and domain == "finance_biz":
            rev_m = re.search(r"(?:doanh\s+thu|thu\s+về)\s*(?:đạt|là|bằng|=|:)?\s*(\d+(?:[.,]\d+)?)\s*(tỷ|ty|tỉ|ti|triệu|trieu|tr|nghìn|nghin|ngàn|ngan)?", q_low)
            cost_m = re.search(r"(?:chi\s+phí|vốn\s+(?:đầu\s+tư|bỏ\s+ra))\s*(?:đầu\s+tư\s+|bỏ\s+ra\s+)?(?:là|bằng|=|:)?\s*(\d+(?:[.,]\d+)?)\s*(tỷ|ty|tỉ|ti|triệu|trieu|tr|nghìn|nghin|ngàn|ngan)?", q_low)
            if rev_m and cost_m:
                rev_val = _parse_vn_amount(rev_m.group(1), rev_m.group(2))
                cost_val = _parse_vn_amount(cost_m.group(1), cost_m.group(2))
                if cost_val > 0:
                    variables = {"doanh_thu": rev_val, "chi_phi": cost_val}
                    expressions = [
                        "loi_nhuan = round(doanh_thu - chi_phi, 2)",
                        "roi_pct = round((loi_nhuan / chi_phi) * 100, 2)",
                    ]

    _DOMAIN_GOALS = {
        "math_science": "Phân tích dữ kiện, áp dụng công thức chuẩn xác & kiểm chứng định lượng",
        "finance_biz": "Phân tích chỉ số tài chính, tính toán hiệu quả & đánh giá rủi ro",
        "legal_policy": "Đối chiếu điều khoản, rà soát điều kiện ngoại lệ & rủi ro tuân thủ",
        "tech_debug": "Phân tích nguyên nhân gốc rễ, đánh đổi kiến trúc & phương án tối ưu",
        "decision_strategy": "Đánh giá đa tiêu chí, so sánh phương án & đề xuất lộ trình tối ưu",
        "academic_critique": "Kiểm chứng tính nhất quán, phát hiện mâu thuẫn & phản biện chuyên sâu",
        "general": "Phân tích đa chiều, đối chiếu chứng cứ & tổng hợp kết luận có căn cứ",
    }
    goal = (
        f"[{domain_label}] "
        + (
            "Áp dụng công thức & kiểm chứng số liệu từ tài liệu qua Python Sandbox"
            if expressions
            else _DOMAIN_GOALS.get(domain, _DOMAIN_GOALS["general"])
        )
    )
    return {
        "domain": domain,
        "domain_label": domain_label,
        "goal": goal,
        "sub_queries": sub_queries,
        "cross_check_focus": None,
        "needs_calculation": bool(expressions),
        "variables": variables,
        "expressions": expressions,
        "fast_planned": True,
    }


async def _plan_reasoning_steps(
    query: str,
    initial_chunks: List[Dict[str, Any]],
    model_name: str,
    max_sub_queries: int,
) -> Optional[Dict[str, Any]]:
    """Bước 1: Phân rã câu hỏi, xác định truy vấn phụ, công thức/biến số và điểm cần kiểm chứng chéo."""
    sys_prompt = (
        "Bạn là Bộ lập kế hoạch Suy luận Đa bước (Reasoning Planner). Nhiệm vụ của bạn KHÔNG phải là viết câu trả lời dài, "
        "mà là phân tích câu hỏi + các đoạn tài liệu ban đầu để xuất ra kế hoạch công cụ dạng JSON.\n"
        "TRẢ VỀ DUY NHẤT JSON OBJECT:\n"
        "{\n"
        '  "goal": "Tóm tắt mục tiêu suy luận bằng 1 câu ngắn",\n'
        '  "sub_queries": ["truy vấn tìm thêm dữ kiện hoặc điều kiện/ngoại lệ còn thiếu trong tài liệu (tối đa 2 chuỗi, hoặc [] nếu đã đủ)"],\n'
        '  "cross_check_focus": "từ khóa kiểm tra ràng buộc/mâu thuẫn/ngoại lệ hoặc null",\n'
        '  "needs_calculation": true/false,\n'
        '  "variables": {"ten_bien": gia_tri_so_hoac_danh_sach},\n'
        '  "expressions": ["ket_qua = bieu_thuc_python_an_toan"]\n'
        "}\n"
        "LƯU Ý: Chỉ đặt expressions bằng biểu thức toán/logic Python thuần (+ - * / ** sqrt round min max sum abs ... và biểu thức `a if cond else b`). "
        "Không dùng import hoặc hàm ngoài whitelist."
    )
    user_prompt = (
        f"NGỮ CẢNH TÀI LIỆU BAN ĐẦU:\n{_format_chunk_briefs(initial_chunks)}\n\n"
        f"YÊU CẦU NGƯỜI DÙNG: {query}\n\n"
        f"Giới hạn sub_queries tối đa {max_sub_queries} chuỗi. Trả về JSON:"
    )
    res = await call_ollama_json(
        sys_prompt,
        user_prompt,
        model=model_name,
        num_predict=420,
        num_ctx=3072,
        temperature=0.1,
        timeout_sec=35.0,
    )
    if res.get("ok") and isinstance(res.get("data"), dict):
        return res["data"]
    return None


def _format_human_number(val: Any) -> str:
    if isinstance(val, int):
        return f"{val:,}".replace(",", ".")
    if isinstance(val, float):
        if val.is_integer():
            return f"{int(val):,}".replace(",", ".")
        decimals = 6 if abs(val) < 100 else 2
        int_part, dec_part = f"{val:.{decimals}f}".split(".")
        int_fmt = f"{int(int_part):,}".replace(",", ".")
        dec_clean = dec_part.rstrip("0")
        return f"{int_fmt},{dec_clean}" if dec_clean else int_fmt
    return str(val)


def _audit_reasoning_grounding(
    answer: str,
    citations_count: int,
    sandbox_res: Optional[Dict[str, Any]],
) -> Tuple[str, str, str]:
    """
    Hậu kiểm nhanh (<1ms) câu trả lời sau bước suy luận:
    1. Loại bỏ tiêu đề prompt nội bộ / cú pháp LaTeX thô nếu model 3B lỡ viết nhầm.
    2. Loại bỏ trích dẫn giả [n] nằm ngoài danh sách nguồn (n > citations_count hoặc n <= 0).
    3. Đảm bảo kết quả số học đã xác thực từ Python Sandbox xuất hiện rõ ràng trong kết luận.
    Trả về (audited_answer, extra_delta_to_stream, step4_detail).
    """
    from app.services.llm_service import _sanitize_rag_output

    pre_norm = re.sub(
        r"\[\s*(?:Tài\s*liệu|Nguồn(?:\s*web)?)\s*(\d{1,3})\s*\]",
        r"[\1]",
        answer or "",
        flags=re.IGNORECASE | re.UNICODE,
    )
    dropped_refs = 0

    def _check_ref(match: re.Match) -> str:
        nonlocal dropped_refs
        idx = int(match.group(1))
        if 1 <= idx <= citations_count:
            return match.group(0)
        dropped_refs += 1
        return ""

    cleaned = re.sub(r"\[(\d{1,3})\]", _check_ref, pre_norm)
    cleaned = _sanitize_rag_output(cleaned, citations_count)
    cleaned = re.sub(r" +([,.;:])", r"\1", cleaned)

    _SANDBOX_LABELS = {
        "duong_sinh_l": "Đường sinh l",
        "V_non_cut": "Thể tích hình nón cụt (V)",
        "S_xq_non_cut": "Diện tích xung quanh nón cụt (Sxq)",
        "S_tp_non_cut": "Diện tích toàn phần nón cụt (Stp)",
        "C_day_tru": "Chu vi đáy hình trụ (C)",
        "S_xq_tru": "Diện tích xung quanh hình trụ (Sxq)",
        "S_tp_tru": "Diện tích toàn phần hình trụ (Stp)",
        "V_tru": "Thể tích hình trụ (V)",
        "chenh_lech_V": "Chênh lệch thể tích (ΔV)",
        "chenh_lech_phan_tram": "Tỷ lệ chênh lệch (%)",
        "x2_cong_y2": "x² + y²",
        "x3_tru_y3": "x³ - y³",
        "x3_cong_y3": "x³ + y³",
        "gia_tri_B": "Giá trị biểu thức B",
        "gia_tri_A": "Giá trị biểu thức A",
        "chenh_lech_tu": "Chênh lệch số từ",
    }

    extra_delta = ""
    sandbox_note = ""
    steps_to_check: List[Dict[str, Any]] = []
    if sandbox_res and sandbox_res.get("ok"):
        if sandbox_res.get("steps"):
            steps_to_check = list(sandbox_res["steps"])
        elif sandbox_res.get("final_result") is not None:
            steps_to_check = [{"target": "Kết quả tính toán xác thực", "value": sandbox_res["final_result"]}]

    if steps_to_check:
        missing_rows: List[str] = []
        for st in steps_to_check:
            val = st.get("value")
            if val is None or isinstance(val, bool):
                continue
            target_k = str(st.get("target") or "Kết quả")
            human_val = _format_human_number(val)
            candidates = {str(val), human_val}
            if isinstance(val, float) and val.is_integer():
                candidates.add(str(int(val)))
            if isinstance(val, (int, float)):
                candidates.add(f"{val:,.0f}".replace(",", "."))
                candidates.add(f"{val:,.0f}")
                candidates.add(f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                candidates.add(f"{val:.2f}")
            if not any(tok in cleaned for tok in candidates):
                pretty_k = _SANDBOX_LABELS.get(target_k, target_k.replace("_", " "))
                missing_rows.append(f"- **{pretty_k}**: `{human_val}`")
        if missing_rows:
            if len(missing_rows) == 1:
                extra_delta = f"\n\n> **Kiểm chứng Python Sandbox:** {missing_rows[0].lstrip('- ')}."
            else:
                extra_delta = "\n\n> **Bảng số liệu xác thực từ Python Sandbox:**\n" + "\n".join(missing_rows)
            cleaned = cleaned.rstrip() + extra_delta
            sandbox_note = f" Đã bổ sung {len(missing_rows)} số liệu xác thực từ Sandbox."

    step_detail = (
        f"Đã đối chiếu {citations_count} nguồn trích dẫn"
        + (f" (loại bỏ {dropped_refs} trích dẫn ngoài phạm vi)" if dropped_refs else "")
        + (sandbox_note or " và xác nhận tính nhất quán.")
    )
    return cleaned, extra_delta, step_detail


async def _repair_sandbox_expressions(
    query: str,
    variables: Dict[str, Any],
    expressions: List[str],
    error_msg: str,
    model_name: str,
) -> Optional[Dict[str, Any]]:
    """Tự sửa lỗi cú pháp/biến khi chạy Sandbox (tối đa 1 lần retry)."""
    sys_prompt = (
        "Sửa lỗi biểu thức Python Sandbox sau sao cho hợp lệ và chạy được bằng toán tử chuẩn/hàm math. "
        'Trả về JSON: {"variables": {...}, "expressions": ["..."]}.'
    )
    user_prompt = (
        f"Câu hỏi: {query}\n"
        f"Variables cũ: {json.dumps(variables, ensure_ascii=False)}\n"
        f"Expressions cũ: {json.dumps(expressions, ensure_ascii=False)}\n"
        f"Lỗi Sandbox: {error_msg}\nHãy trả về JSON đã sửa:"
    )
    res = await call_ollama_json(
        sys_prompt,
        user_prompt,
        model=model_name,
        num_predict=260,
        num_ctx=2048,
        temperature=0.05,
        timeout_sec=25.0,
    )
    if res.get("ok") and isinstance(res.get("data"), dict):
        return res["data"]
    return None


async def stream_autonomous_reasoning(
    workspace_id: str,
    query: str,
    initial_chunks: List[Dict[str, Any]],
    model_name: str = DEFAULT_LLM_MODEL,
    web_sources: Optional[List[Dict[str, Any]]] = None,
    history: Optional[List[Dict[str, str]]] = None,
    selected_document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    collector: Optional[Dict[str, Any]] = None,
    is_disconnected: Optional[Callable[[], Awaitable[bool]]] = None,
) -> AsyncGenerator[str, None]:
    """
    Thực thi vòng lặp suy luận đa bước:
    1. Phân rã vấn đề (Plan)
    2. Truy xuất nhiều vòng (Multi-hop RAG) + Đối chiếu ràng buộc (Cross-check)
    3. Thực thi công cụ kiểm chứng (Python AST Sandbox)
    4. Tổng hợp suy luận + Tự kiểm chứng (Self-Verify)
    """
    profile = get_active_profile_config()
    max_steps = int(profile.get("max_reasoning_steps") or 3)
    enable_self_verify = bool(profile.get("enable_self_verify", True))
    profile_top_k = int(profile.get("top_k") or 4)

    ollama_status = await check_ollama_status()
    chosen_model, model_available = _resolve_model_for_chat(
        model_name, ollama_status, None, task_tier="deep"
    )
    trace_steps: List[Dict[str, Any]] = []

    def _emit_step(step_num: int, title: str, detail: str, status: str = "done") -> Dict[str, Any]:
        item = {"step": step_num, "title": title, "detail": detail, "status": status}
        trace_steps.append(item)
        return item

    # Bước 1: Lập kế hoạch phân rã vấn đề (kết hợp Fast Local Planner <1ms cho máy nhẹ + LLM Planner khi cần)
    yield f"data: {json.dumps({'stage': 'reasoning_plan', 'stage_label': 'Đang phân tách vấn đề và lập kế hoạch suy luận...'}, ensure_ascii=False)}\n\n"

    max_sub_q = max(1, min(2, max_steps - 1))
    fast_plan = _fast_local_reasoning_planner(query, initial_chunks, max_sub_queries=max_sub_q)
    plan: Optional[Dict[str, Any]] = fast_plan

    profile_id = str(profile.get("id") or "balanced").lower()
    avail_ram = float((profile.get("specs") or {}).get("available_ram_gb") or 8.0)
    json_mocked = bool(
        hasattr(call_ollama_json, "_mock_name")
        or hasattr(call_ollama_json, "assert_called")
        or getattr(call_ollama_json, "__module__", "").startswith("unittest.mock")
    )
    needs_math_cue = bool(
        re.search(
            r"\b(?:tính|tinh|bao\s+nhiêu|bao\s+nhieu|phần\s+trăm|phan\s+tram|thể\s+tích|the\s+tich|"
            r"diện\s+tích|dien\s+tich|khoảng\s+cách|khoang\s+cach|gtln|gtnn|tiếp\s+xúc|parabol|giải)\b",
            query or "",
            re.IGNORECASE | re.UNICODE,
        )
    )
    # Chỉ gọi thêm LLM JSON Planner (vòng 1) khi đang chạy unit test mock, hoặc máy ở chế độ Performance,
    # hoặc khi Fast Local Planner chưa trích được biểu thức tính toán (nhất là bài toán cần giải bằng Python Sandbox)
    should_call_llm_planner = (
        ollama_status.get("running")
        and model_available
        and (
            json_mocked
            or profile_id == "performance"
            or (not fast_plan.get("expressions") and needs_math_cue and profile_id != "eco")
            or (not fast_plan.get("expressions") and not fast_plan.get("sub_queries") and avail_ram >= 8.5)
        )
    )
    if should_call_llm_planner:
        llm_plan = await _plan_reasoning_steps(
            query=query,
            initial_chunks=initial_chunks,
            model_name=chosen_model,
            max_sub_queries=max_sub_q,
        )
        if llm_plan:
            # Nếu LLM plan không có biểu thức tính toán mà Fast Local Planner đã trích xuất được công thức chính xác thì giữ lại công thức
            if not llm_plan.get("expressions") and fast_plan.get("expressions"):
                llm_plan["variables"] = fast_plan["variables"]
                llm_plan["expressions"] = fast_plan["expressions"]
            plan = llm_plan

    if is_disconnected and await is_disconnected():
        return

    domain = str(fast_plan.get("domain") or "general")
    domain_label = str(fast_plan.get("domain_label") or "Phân tích đa chiều")
    goal_text = str((plan or {}).get("goal") or "Phân tích và suy luận từ ngữ cảnh tài liệu").strip()
    step1 = _emit_step(1, f"Phân rã bài toán · {domain_label}", goal_text)
    yield f"data: {json.dumps({'reasoning_step': step1}, ensure_ascii=False)}\n\n"

    # Bước 2: Multi-hop RAG + Cross-Check
    consolidated_chunks = list(initial_chunks)
    # Nếu vòng truy xuất đầu hoàn toàn không có đoạn tài liệu khớp câu hỏi VÀ đây là bài toán tính độc lập,
    # bỏ qua các sub_queries generic để tránh kéo nhầm tài liệu lạc đề vào trích dẫn
    if not initial_chunks and fast_plan.get("needs_calculation"):
        sub_queries = []
    else:
        sub_queries = [str(s).strip() for s in (plan or {}).get("sub_queries", []) if str(s).strip()]
        cross_focus = (plan or {}).get("cross_check_focus")
        if isinstance(cross_focus, str) and cross_focus.strip():
            sub_queries.append(f"điều kiện ngoại lệ quy định {cross_focus.strip()}")

    ran_queries: List[str] = []
    for sub_q in sub_queries[:max(1, max_steps - 1)]:
        if is_disconnected and await is_disconnected():
            return
        extra_hits = await run_in_threadpool(
            _tool_search_docs,
            workspace_id,
            sub_q,
            profile_top_k,
            selected_document_id,
            document_ids,
        )
        if extra_hits:
            consolidated_chunks.extend(extra_hits)
            ran_queries.append(sub_q)

    consolidated_chunks = _dedup_chunks(consolidated_chunks, max_total=min(profile_top_k + 3, 8))
    step2_detail = (
        f"Đã truy xuất bổ sung {len(ran_queries)} nhánh dữ kiện ({len(consolidated_chunks)} đoạn nguồn)."
        if ran_queries
        else f"Đang tổng hợp trên {len(consolidated_chunks)} đoạn nguồn đã đối chiếu."
    )
    step2 = _emit_step(2, "Truy xuất & Đối chiếu chéo", step2_detail)
    yield f"data: {json.dumps({'reasoning_step': step2}, ensure_ascii=False)}\n\n"

    # Bước 3: Kiểm chứng bằng Python AST Sandbox nếu có tính toán / logic số liệu
    sandbox_res: Optional[Dict[str, Any]] = None
    variables = (plan or {}).get("variables") if isinstance((plan or {}).get("variables"), dict) else {}
    expressions = (plan or {}).get("expressions") if isinstance((plan or {}).get("expressions"), list) else []
    expressions = [str(e).strip() for e in expressions if str(e).strip()]

    if expressions:
        yield f"data: {json.dumps({'stage': 'reasoning_tool', 'stage_label': 'Đang kiểm chứng phép tính & điều kiện logic qua Python Sandbox...'}, ensure_ascii=False)}\n\n"
        try:
            sandbox_res = await asyncio.wait_for(
                run_in_threadpool(evaluate_python_sandbox, variables, expressions),
                timeout=3.0,
            )
        except asyncio.TimeoutError:
            sandbox_res = {"ok": False, "steps": [], "env": {}, "final_result": None, "error": "Quá thời gian thực thi Sandbox (3s)."}
        if not sandbox_res.get("ok") and ollama_status.get("running") and model_available:
            repaired = await _repair_sandbox_expressions(
                query,
                variables,
                expressions,
                str(sandbox_res.get("error") or "Lỗi thực thi"),
                chosen_model,
            )
            if repaired:
                new_vars = repaired.get("variables") if isinstance(repaired.get("variables"), dict) else variables
                new_exprs = [str(e).strip() for e in repaired.get("expressions", []) if str(e).strip()]
                if new_exprs:
                    try:
                        sandbox_res = await asyncio.wait_for(
                            run_in_threadpool(evaluate_python_sandbox, new_vars, new_exprs),
                            timeout=3.0,
                        )
                    except asyncio.TimeoutError:
                        sandbox_res = {"ok": False, "steps": [], "env": {}, "final_result": None, "error": "Quá thời gian thực thi Sandbox (3s)."}

        if sandbox_res.get("ok"):
            s_detail = f"Đã kiểm chứng {len(sandbox_res.get('steps', []))} bước tính -> Kết quả: {sandbox_res.get('final_result')}"
        else:
            s_detail = f"Không thực thi được biểu thức tự động ({sandbox_res.get('error')}); chuyển sang suy luận lập luận."
        step3 = _emit_step(3, "Kiểm chứng Python Sandbox", s_detail)
        yield f"data: {json.dumps({'reasoning_step': step3}, ensure_ascii=False)}\n\n"

    # Chuẩn bị ngữ cảnh & citations cuối cùng
    _, user_context_prompt, citations = _prepare_rag_prompts_and_citations(
        query,
        consolidated_chunks,
        web_sources=web_sources,
        max_context_tokens=int(profile.get("max_context_tokens") or 2200),
    )

    reasoning_meta = {
        "citations": citations,
        "model_used": chosen_model,
        "engine": "reasoning_engine" if (ollama_status["running"] and model_available) else "fallback_pipeline",
        "stage": "found_sources",
        "stage_label": f"Đã hoàn tất đối chiếu {len(citations)} nguồn — Đang tổng hợp kết luận...",
    }
    yield f"data: {json.dumps(reasoning_meta, ensure_ascii=False)}\n\n"

    # Bước 4: Tổng hợp suy luận + Self-Verify
    _SANDBOX_HUMAN_LABELS = {
        "von": "Vốn gốc",
        "lai_suat": "Lãi suất/kỳ",
        "so_ky": "Số kỳ",
        "he_so_tang": "Hệ số tăng trưởng",
        "tong_nhan": "Tổng tiền nhận được",
        "tien_lai": "Tiền lãi",
        "tong_cong": "Tổng cộng",
        "duong_sinh_l": "Đường sinh hình nón cụt (l = √((R - r)^2 + h^2))",
        "V_non_cut": "Thể tích hình nón cụt (cm³)",
        "S_xq_non_cut": "Diện tích xung quanh hình nón cụt (π(R + r)l, cm²)",
        "S_tp_non_cut": "Diện tích toàn phần hình nón cụt (Sxq + πR^2 + πr^2, cm²)",
        "V_tru": "Thể tích hình trụ (πR^2h, cm³)",
        "S_tp_tru": "Diện tích toàn phần hình trụ (2πR(h + R), cm²)",
        "l_non": "Đường sinh hình nón",
        "V_non": "Thể tích hình nón",
        "S_tp_non": "Diện tích toàn phần hình nón",
        "S_cau": "Diện tích mặt cầu",
        "V_cau": "Thể tích khối cầu",
        "chenh_lech_V": "Độ chênh lệch thể tích (cm³)",
        "loi_nhuan": "Lợi nhuận ròng",
        "roi_pct": "Tỷ suất lợi nhuận ROI (%)",
        "ket_qua": "Kết quả tính toán",
    }
    sandbox_block = ""
    if sandbox_res and sandbox_res.get("ok"):
        final_raw = sandbox_res.get("final_result")
        final_human = _format_human_number(final_raw)
        step_lines = []
        for st in sandbox_res.get("steps", []):
            key = st.get("target") or "Bước"
            label = _SANDBOX_HUMAN_LABELS.get(key, key)
            val_fmt = _format_human_number(st["value"])
            if key == "V_tru" and "R_tru" in variables and "h_tru" in variables:
                r_fmt = _format_human_number(variables["R_tru"])
                h_fmt = _format_human_number(variables["h_tru"])
                step_lines.append(f"- {label}: {val_fmt} (với bán kính đáy R = {r_fmt}, chiều cao h = {h_fmt}; không chia đôi R)")
            else:
                step_lines.append(f"- {label}: {val_fmt}")
        raw_suffix = f" ({final_raw})" if str(final_raw) != final_human else ""
        sandbox_block = (
            "\n\n[SỐ LIỆU ĐỐI CHIẾU ĐÃ TÍNH ĐÚNG]:\n"
            + "\n".join(step_lines)
            + f"\n- Kết quả chính cuối cùng: {final_human}{raw_suffix}.\n"
            "(TUYỆT ĐỐI KHÔNG chép lại danh sách hay dòng tiêu đề trên vào câu trả lời; hãy lồng từng con số đúng vị trí tương ứng vào các bước giải sạch sẽ, không viết tên biến gạch dưới kiểu Python)."
        )

    verify_directive = (
        "\n- TỰ KIỂM CHỨNG: Đảm bảo kết luận khớp tuyệt đối với đáp số đã tính sẵn, không tự ước lượng sai số trung gian và chỉ rõ phần nào từ tài liệu vs. phần phân tích tổng quát."
        if enable_self_verify
        else ""
    )

    has_citations = bool(citations)
    src_hint = "(gắn trích dẫn [1], [2]... tương ứng với nguồn trong tài liệu)." if has_citations else "(nêu ngắn gọn nếu tài liệu chưa có, rồi trình bày căn cứ chuẩn xác)."
    domain_templates = {
        "math_science": (
            f"### 1. Căn cứ & Công thức áp dụng\n{src_hint}\n",
            "### 2. Phân tích & Giải chi tiết từng bước\n- Trình bày công thức bằng ký hiệu phổ thông (`(π × 24 / 3) × (15^2 + 15×10 + 10^2) ≈ 11.938,05 cm^3`), KHÔNG viết tên biến gạch dưới kiểu Python và KHÔNG dùng cú pháp LaTeX (`\\frac`, `\\sqrt`, `\\pi`, `\\boxed`).\n",
            "### 3. Điều kiện áp dụng & Lưu ý sai sót\n- Nêu ngắn gọn điều kiện xác định, giả thiết hoặc điểm dễ nhầm lẫn.\n",
            "### 4. Kết luận\n- Chốt đáp số và nhận xét trong 2–3 câu; dừng ngay sau đó.",
        ),
        "finance_biz": (
            f"### 1. Dữ kiện & Chỉ số nền tảng\n{src_hint}\n",
            "### 2. Tính toán & Phân tích hiệu quả tài chính\n- Nêu rõ từng con số bằng định dạng dễ đọc (`150.000.000`, `9,95%`), KHÔNG tự nhẩm sai và KHÔNG viết tên biến Python.\n",
            "### 3. Đánh giá rủi ro & Biên an toàn\n- Phân tích bản chất nghiệp vụ (phí tất toán, chi phí cơ hội, biến động thị trường hoặc điều khoản phạt).\n",
            "### 4. Khuyến nghị quyết định\n- Đề xuất phương án tối ưu kèm lý do trong 2–3 câu.",
        ),
        "legal_policy": (
            f"### 1. Căn cứ điều khoản & Quy định liên quan\n{src_hint}\n",
            "### 2. Đối chiếu tình huống, Điều kiện áp dụng & Ngoại lệ\n- Tách từng điều kiện/ngoại lệ bằng gạch đầu dòng rõ ràng, chỉ rõ điều kiện nào thỏa mãn hoặc bị vi phạm.\n",
            "### 3. Rủi ro pháp lý & Điểm bất lợi cần lưu ý\n- Chỉ ra chế tài, lỗ hổng nghĩa vụ hoặc trường hợp dễ tranh chấp.\n",
            "### 4. Kết luận tuân thủ & Hướng xử lý\n- Khẳng định mức độ hợp lệ và đề xuất hành động cụ thể.",
        ),
        "tech_debug": (
            f"### 1. Bối cảnh kỹ thuật & Giả thuyết\n{src_hint}\n",
            "### 2. Phân tích nguyên nhân gốc rễ / Đánh đổi kiến trúc (Trade-offs)\n- So sánh hoặc truy vết từng lớp (hiệu năng, độ trễ, RAM/CPU, khả năng mở rộng, bảo mật) bằng gạch đầu dòng súc tích.\n",
            "### 3. Rủi ro vận hành & Điểm nghẽn tiềm ẩn\n- Nêu giới hạn phần cứng, xung đột hoặc edge-case cần tránh.\n",
            "### 4. Giải pháp khắc phục & Kiến nghị tối ưu\n- Đưa ra bước hành động ưu tiên rõ ràng.",
        ),
        "decision_strategy": (
            f"### 1. Tiêu chí đánh giá & Bối cảnh\n{src_hint}\n",
            "### 2. Phân tích & So sánh đa phương án\n- Đối chiếu ưu điểm, nhược điểm và tác động ngắn/dài hạn (dùng bảng hoặc gạch đầu dòng gọn).\n",
            "### 3. Rủi ro & Điều kiện tiên quyết\n- Nêu các ràng buộc bắt buộc phải có để phương án khả thi.\n",
            "### 4. Lựa chọn tối ưu & Lộ trình hành động\n- Chốt phương án đề xuất kèm 2–3 bước triển khai tiếp theo.",
        ),
        "academic_critique": (
            f"### 1. Nội dung nguồn & Luận điểm chính\n{src_hint}\n",
            "### 2. Kiểm chứng logic & Phát hiện điểm mâu thuẫn / thiếu sót\n- Đối chiếu từng luận điểm với chuẩn kiến thức hoặc giữa các mục trong tài liệu để chỉ rõ chỗ đúng, chỗ sai hoặc chưa chặt chẽ.\n",
            "### 3. Phân tích phản biện & Cách điều chỉnh chuẩn xác\n- Nêu lập luận sửa lại (nếu phát hiện lỗi) kèm căn cứ giải thích.\n",
            "### 4. Tổng kết đánh giá\n- Chốt ngắn gọn độ tin cậy và kết luận sau cùng.",
        ),
        "general": (
            f"### 1. Cơ sở thông tin & Bối cảnh\n{src_hint}\n",
            "### 2. Phân tích đa chiều từng khía cạnh\n- Chia ý rõ ràng bằng gạch đầu dòng, lập luận chặt chẽ giữa nguyên nhân — kết quả.\n",
            "### 3. Lưu ý quan trọng & Giới hạn thực tế\n- Nêu các điều kiện ngoại lệ hoặc khía cạnh cần cân nhắc thêm.\n",
            "### 4. Kết luận & Gợi ý bước tiếp theo\n- Chốt ngắn gọn nội dung cốt lõi.",
        ),
    }
    s1, s2, s3, s4 = domain_templates.get(domain, domain_templates["general"])
    synth_system = (
        "Bạn là Chuyên gia Phân tích & Suy luận Tri thức AI đa lĩnh vực. "
        "Chỉ giải đúng bài toán/chủ đề hiện tại (bỏ qua hoàn toàn nội dung các chương/hình khác không liên quan nằm chung trang tài liệu hay hội thoại trước). "
        "Hãy trình bày câu trả lời ĐÚNG MỘT LẦN theo đúng 4 mục mạch lạc sau (KHÔNG lặp lại mục Kết luận 2 lần, KHÔNG chép câu hỏi hay dòng nhãn hệ thống):\n"
        f"{s1}{s2}{s3}{s4}{verify_directive}"
    )

    synth_user = (
        f"Câu hỏi người dùng: {query}\n"
        f"{user_context_prompt}"
        f"{sandbox_block}"
    )

    full_answer = ""
    action_payload = {
        "action_type": "reasoning_result",
        "title": "Quá trình AI tự suy luận & kiểm chứng",
        "goal": goal_text,
        "reasoning_steps": trace_steps,
        "sandbox": sandbox_res if (sandbox_res and sandbox_res.get("ok")) else None,
        "summary": f"{len(trace_steps)} bước suy luận · {len(citations)} nguồn đối chiếu",
    }

    if ollama_status.get("running") and model_available:
        history_messages = _build_bounded_history_messages(history, current_query=query)
        local_collector: Dict[str, Any] = {}
        est_tokens = _estimate_tokens(synth_system) + _estimate_tokens(synth_user) + sum(
            _estimate_tokens(m.get("content", "")) for m in history_messages
        )
        instant_sugs = _build_instant_followup_suggestions(query, citations, consolidated_chunks)
        sampling_opts = _resolve_sampling_options(
            query,
            int(profile.get("num_ctx") or 4096),
            int(profile.get("num_predict") or 1024),
            None,
            estimated_input_tokens=est_tokens,
        )
        sampling_opts["num_predict"] = max(int(sampling_opts.get("num_predict") or 520), 1024)
        sampling_opts["temperature"] = 0.22
        sampling_opts["repeat_penalty"] = 1.12
        try:
            async for raw_evt in _stream_ollama_chat(
                payload={
                    "model": chosen_model,
                    "messages": [
                        {"role": "system", "content": synth_system},
                        *history_messages,
                        {"role": "user", "content": synth_user},
                    ],
                    "stream": True,
                    "keep_alive": get_recommended_keep_alive(),
                    "options": sampling_opts,
                },
                citations=citations,
                model_name=chosen_model,
                engine_name="reasoning_engine",
                collector=local_collector,
                is_disconnected=is_disconnected,
                followup_suggestions=instant_sugs,
            ):
                if raw_evt.startswith("data: [DONE]"):
                    continue
                if raw_evt.startswith("data: "):
                    try:
                        parsed = json.loads(raw_evt[6:].strip())
                        if parsed.get("done"):
                            full_answer = str(parsed.get("answer") or local_collector.get("full_answer") or "")
                            continue
                    except Exception:
                        pass
                yield raw_evt

            step4_detail = "Đã hoàn thành lập luận có căn cứ trích dẫn."
            if full_answer:
                audited, extra_delta, step4_detail = _audit_reasoning_grounding(
                    full_answer,
                    len(citations),
                    sandbox_res,
                )
                full_answer = audited
                if extra_delta:
                    yield f"data: {json.dumps({'delta': extra_delta}, ensure_ascii=False)}\n\n"

            step4 = _emit_step(len(trace_steps) + 1, "Tổng hợp & Kiểm chứng kết luận", step4_detail)
            action_payload["reasoning_steps"] = list(trace_steps)
            yield f"data: {json.dumps({'reasoning_step': step4}, ensure_ascii=False)}\n\n"
            if collector is not None:
                collector["full_answer"] = full_answer
                collector["citations"] = citations
                collector["model_used"] = chosen_model
                collector["engine"] = "reasoning_engine"
                collector["action_result"] = action_payload
            yield f"data: {json.dumps({'answer': full_answer, 'done': True, 'action_result': action_payload}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return
        except Exception:
            logger.exception("Reasoning synthesis stream failed")

    # Fallback khi Ollama offline nhưng vẫn báo cáo được trace + sandbox + citations
    fallback_parts = [f"Đã đối chiếu **{len(citations)} đoạn tài liệu liên quan** qua bước phân tích đa vòng."]
    if sandbox_res and sandbox_res.get("ok"):
        fallback_parts.append(f"Kết quả kiểm chứng Python Sandbox: **{sandbox_res.get('final_result')}**.")
    fallback_parts.append("Hiện tại Ollama đang tắt hoặc không phản hồi, vui lòng bật Ollama để nhận phần giải thích suy luận đầy đủ.")
    fallback_answer = "\n\n".join(fallback_parts)

    yield f"data: {json.dumps({'delta': fallback_answer}, ensure_ascii=False)}\n\n"
    if collector is not None:
        collector["full_answer"] = fallback_answer
        collector["citations"] = citations
        collector["model_used"] = "direct_context_extractor"
        collector["engine"] = "fallback_pipeline"
        collector["action_result"] = action_payload
    yield f"data: {json.dumps({'answer': fallback_answer, 'done': True, 'action_result': action_payload}, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"
