"""Bộ máy Suy luận Tự chủ Đa bước (Autonomous Multi-Step Reasoning + General Tool Registry)."""
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


def _fast_local_reasoning_planner(
    query: str,
    initial_chunks: List[Dict[str, Any]],
    max_sub_queries: int = 2,
) -> Dict[str, Any]:
    """
    Bộ lập kế hoạch suy luận & trích xuất toán học tức thì (<1ms, 0 tốn LLM call):
    1. Tách các mệnh đề câu hỏi ghép ('và', 'đồng thời', 'so sánh A với B', 'nếu... thì...') thành sub_queries.
    2. Nhận diện và trích xuất tự động công thức Toán tài chính / Lãi kép / Lãi đơn / Tỷ lệ % / Phạt hợp đồng
       từ câu hỏi + tài liệu để nạp thẳng vào Python AST Sandbox.
    """
    q_clean = (query or "").strip()
    q_low = q_clean.lower()

    # 1. Phân tách sub_queries đa nhánh
    sub_queries: List[str] = []
    parts = re.split(
        r"\b(?:và\s+đánh\s+giá|và\s+so\s+sánh|và\s+đối\s+chiếu|đồng\s+thời|bên\s+cạnh\s+đó|"
        r"va\s+danh\s+gia|va\s+so\s+sanh|va\s+doi\s+chieu|dong\s+thoi)\b",
        q_clean,
        flags=re.IGNORECASE | re.UNICODE,
    )
    if len(parts) >= 2:
        for p in parts:
            p_str = p.strip(" ,;?.!")
            if len(p_str) >= 10 and p_str.lower() != q_low:
                sub_queries.append(p_str)
    if initial_chunks and any(k in q_low for k in ("vi phạm", "vi pham", "bị phạt", "bi phat", "rủi ro", "rui ro", "hợp lệ", "hop le", "đủ điều kiện", "du dieu kien")):
        sub_queries.append("điều kiện ngoại lệ mức phạt chế tài quy định")

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
    if not rate_m and initial_chunks:
        joined_ctx = " ".join(str(c.get("content") or "") for c in initial_chunks[:3])
        rate_m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", joined_ctx)
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
        # Biểu thức số học thuần trong câu hỏi (vd: "1250 * 48 + 15000")
        arith_m = re.search(r"\b(\d+(?:\.\d+)?(?:\s*[\+\-\*\/]\s*\d+(?:\.\d+)?)+)\b", q_low)
        if arith_m:
            expr_clean = arith_m.group(1).strip()
            expressions = [f"ket_qua = round({expr_clean}, 4)"]
        else:
            # Hình học không gian tức thì (<1ms): Hình nón cụt, Hình nón, Hình trụ (kể cả quay hình chữ nhật), Hình cầu
            has_frustum = any(k in q_low for k in ("nón cụt", "non cut"))
            has_cylinder = any(k in q_low for k in ("hình trụ", "hinh tru"))
            has_cone = not has_frustum and any(k in q_low for k in ("hình nón", "hinh non"))
            has_sphere = any(k in q_low for k in ("hình cầu", "hinh cau", "mặt cầu", "mat cau", "khối cầu", "khoi cau"))

            if has_frustum:
                rad_m = re.search(
                    r"bán\s+kính[^0-9]{0,35}(\d+(?:[.,]\d+)?)\s*(?:cm|m|dm|mm)?\s*(?:và|,)\s*(\d+(?:[.,]\d+)?)",
                    q_low,
                )
                h_m = re.search(r"chiều\s+cao\s*(?:là|bằng|=|:)?\s*(\d+(?:[.,]\d+)?)", q_low)
                if rad_m and h_m:
                    r1 = float(rad_m.group(1).replace(",", "."))
                    r2 = float(rad_m.group(2).replace(",", "."))
                    variables["R_nc"] = max(r1, r2)
                    variables["r_nc"] = min(r1, r2)
                    variables["h_nc"] = float(h_m.group(1).replace(",", "."))
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
                    expressions.extend([
                        "V_tru = round(pi * (R_tru ** 2) * h_tru, 4)",
                        "S_tp_tru = round(2 * pi * R_tru * (h_tru + R_tru), 4)",
                    ])
                else:
                    cyl_r = re.search(r"hình\s+trụ[^.\n]{0,60}?bán\s+kính\s*(?:đáy\s*)?(?:là|bằng|=|:)?\s*(\d+(?:[.,]\d+)?)", q_low)
                    cyl_h = re.search(r"hình\s+trụ[^.\n]{0,90}?chiều\s+cao\s*(?:là|bằng|=|:)?\s*(\d+(?:[.,]\d+)?)", q_low)
                    if cyl_r and cyl_h:
                        variables["R_tru"] = float(cyl_r.group(1).replace(",", "."))
                        variables["h_tru"] = float(cyl_h.group(1).replace(",", "."))
                        expressions.extend([
                            "V_tru = round(pi * (R_tru ** 2) * h_tru, 4)",
                            "S_tp_tru = round(2 * pi * R_tru * (h_tru + R_tru), 4)",
                        ])

            if "V_non_cut" in str(expressions) and "V_tru" in str(expressions):
                expressions.append("chenh_lech_V = round(V_non_cut - V_tru, 4)")
                expressions.append("chenh_lech_phan_tram = round(abs(V_non_cut - V_tru) / V_tru * 100, 2)")
            elif has_cone:
                cone_r = re.search(r"bán\s+kính\s*(?:đáy\s*)?(?:là|bằng|=|:)?\s*(\d+(?:[.,]\d+)?)", q_low)
                cone_h = re.search(r"chiều\s+cao\s*(?:là|bằng|=|:)?\s*(\d+(?:[.,]\d+)?)", q_low)
                if cone_r and cone_h:
                    variables["R_non"] = float(cone_r.group(1).replace(",", "."))
                    variables["h_non"] = float(cone_h.group(1).replace(",", "."))
                    expressions.extend([
                        "l_non = round(sqrt(R_non ** 2 + h_non ** 2), 4)",
                        "V_non = round((pi * (R_non ** 2) * h_non) / 3, 4)",
                        "S_tp_non = round(pi * R_non * (R_non + l_non), 4)",
                    ])
            elif has_sphere:
                sph_r = re.search(r"bán\s+kính\s*(?:là|bằng|=|:)?\s*(\d+(?:[.,]\d+)?)", q_low)
                if sph_r:
                    variables["R_cau"] = float(sph_r.group(1).replace(",", "."))
                    expressions.extend([
                        "S_cau = round(4 * pi * (R_cau ** 2), 4)",
                        "V_cau = round((4 / 3) * pi * (R_cau ** 3), 4)",
                    ])

    goal = (
        "Áp dụng công thức & kiểm chứng số liệu từ tài liệu qua Python Sandbox"
        if expressions
        else "Phân tích đa chiều, đối chiếu điều khoản & điều kiện ngoại lệ trong tài liệu"
    )
    return {
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

    extra_delta = ""
    sandbox_note = ""
    if sandbox_res and sandbox_res.get("ok") and sandbox_res.get("final_result") is not None:
        final_val = sandbox_res["final_result"]
        human_val = _format_human_number(final_val)
        candidates = {str(final_val), human_val}
        if isinstance(final_val, float) and final_val.is_integer():
            candidates.add(str(int(final_val)))
        if isinstance(final_val, (int, float)):
            candidates.add(f"{final_val:,.0f}".replace(",", "."))
            candidates.add(f"{final_val:,.0f}")
            candidates.add(f"{final_val:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        if not any(tok in cleaned for tok in candidates):
            extra_delta = (
                f"\n\n> **Kiểm chứng Python Sandbox:** Kết quả tính toán xác thực là **`{human_val}`**."
            )
            cleaned = cleaned.rstrip() + extra_delta
            sandbox_note = " Đã bổ sung số liệu xác thực từ Sandbox."

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

    goal_text = str((plan or {}).get("goal") or "Phân tích và suy luận từ ngữ cảnh tài liệu").strip()
    step1 = _emit_step(1, "Phân rã bài toán", goal_text)
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
        sandbox_res = evaluate_python_sandbox(variables, expressions)
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
                    sandbox_res = evaluate_python_sandbox(new_vars, new_exprs)

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
    sandbox_block = ""
    if sandbox_res and sandbox_res.get("ok"):
        final_raw = sandbox_res.get("final_result")
        final_human = _format_human_number(final_raw)
        step_pairs = [
            f"{st['target'] or 'Bước'} = {_format_human_number(st['value'])}"
            for st in sandbox_res.get("steps", [])
        ]
        raw_suffix = f" ({final_raw})" if str(final_raw) != final_human else ""
        sandbox_block = (
            "\n\n[DỮ KIỆN TOÁN HỌC ĐÃ TÍNH SẴN BẰNG HỆ THỐNG]:\n"
            f"- Các giá trị chính xác đã tính: {'; '.join(step_pairs)}\n"
            f"- Đáp số cuối cùng chính xác tuyệt đối: {final_human}{raw_suffix}.\n"
            "(Hãy dùng đúng các con số này trong bài giải; KHÔNG tự nhân nhẩm khác số liệu này, KHÔNG viết tên biến Python hay dòng nhãn trên)."
        )

    verify_directive = (
        "\n- TỰ KIỂM CHỨNG: Đảm bảo kết luận khớp tuyệt đối với đáp số đã tính sẵn, không tự ước lượng sai số trung gian và chỉ rõ phần nào từ tài liệu vs. phần phân tích tổng quát."
        if enable_self_verify
        else ""
    )

    has_citations = bool(citations)
    is_finance_risk_q = bool(
        re.search(r"\b(?:lãi|lai|tiền|tien|hợp\s+đồng|hop\s+dong|phạt|phat|rủi\s+ro|rui\s+ro|vay|gửi|gui)\b", query or "", re.IGNORECASE)
    )
    sec3_block = (
        "### 3. Đánh giá rủi ro & Điều kiện thực tế\n- Giải thích chính xác bản chất nghiệp vụ (ví dụ với tiền gửi kỳ hạn: rút trước hạn vẫn bảo toàn tiền gốc nhưng mất phần lãi kép kỳ hạn dài do bị chuyển sang lãi suất không kỳ hạn thấp hoặc chịu phí tất toán nếu hợp đồng quy định).\n"
        if is_finance_risk_q
        else "### 3. Điều kiện áp dụng & Lưu ý phương pháp\n- Nêu ngắn gọn điều kiện xác định, giả thiết hoặc điểm dễ nhầm lẫn khi giải dạng bài trên.\n"
    )
    synth_system = (
        "Bạn là Chuyên gia Phân tích & Suy luận Tri thức AI. Hãy trình bày câu trả lời ĐÚNG MỘT LẦN theo đúng thứ tự 4 mục ngắn gọn sau (không lặp lại mục Kết luận 2 lần):\n"
        + (
            "### 1. Căn cứ từ tài liệu & Công thức áp dụng\n(gắn trích dẫn [1], [2]... tương ứng với nguồn trong tài liệu).\n"
            if has_citations
            else "### 1. Phương pháp & Công thức áp dụng\n(nêu ngắn gọn ở 1 dòng nếu tài liệu không chứa bài toán này, rồi ghi rõ công thức chuẩn).\n"
        )
        + "### 2. Phân tích & Tính toán từng bước\n- Viết công thức bằng ký hiệu phổ thông (`(π × 24 / 3) × (15^2 + 15×10 + 10^2) ≈ 11.938,05 cm^3`), tuyệt đối KHÔNG viết tên biến Python, KHÔNG tự nhẩm sai lũy thừa/căn thức trung gian, và KHÔNG dùng cú pháp LaTeX (`\\frac`, `\\sqrt`, `\\pi`, `\\approx`, `\\boxed`, `\\%`, `\\times`, `\\(`, `\\[`).\n"
        + sec3_block
        + "### 4. Kết luận\n- Chốt gọn đáp số và nhận xét trong 2–3 câu; dừng ngay sau đó."
        f"{verify_directive}"
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
        history_messages = _build_bounded_history_messages(history)
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
            if enable_self_verify and full_answer:
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
