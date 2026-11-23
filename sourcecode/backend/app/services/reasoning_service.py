"""Bộ máy Suy luận Tự chủ Đa bước (Autonomous Multi-Step Reasoning + General Tool Registry)."""
import json
import logging
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Optional
from starlette.concurrency import run_in_threadpool

from app.config import DEFAULT_LLM_MODEL
from app.services.hardware_profile_service import get_active_profile_config
from app.services.llm_service import (
    _build_bounded_history_messages,
    _prepare_rag_prompts_and_citations,
    _resolve_model_for_chat,
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
    chosen_model, model_available = _resolve_model_for_chat(model_name, ollama_status, None)
    trace_steps: List[Dict[str, Any]] = []

    def _emit_step(step_num: int, title: str, detail: str, status: str = "done") -> Dict[str, Any]:
        item = {"step": step_num, "title": title, "detail": detail, "status": status}
        trace_steps.append(item)
        return item

    # Bước 1: Lập kế hoạch phân rã vấn đề
    yield f"data: {json.dumps({'stage': 'reasoning_plan', 'stage_label': 'Đang phân tách vấn đề và lập kế hoạch suy luận...'}, ensure_ascii=False)}\n\n"

    plan: Optional[Dict[str, Any]] = None
    if ollama_status.get("running") and model_available:
        plan = await _plan_reasoning_steps(
            query=query,
            initial_chunks=initial_chunks,
            model_name=chosen_model,
            max_sub_queries=max(1, max_sub_queries := min(2, max_steps - 1)),
        )

    if is_disconnected and await is_disconnected():
        return

    goal_text = str((plan or {}).get("goal") or "Phân tích và suy luận từ ngữ cảnh tài liệu").strip()
    step1 = _emit_step(1, "Phân rã bài toán", goal_text)
    yield f"data: {json.dumps({'reasoning_step': step1}, ensure_ascii=False)}\n\n"

    # Bước 2: Multi-hop RAG + Cross-Check
    consolidated_chunks = list(initial_chunks)
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
        steps_lines = "\n".join(f"  - `{st['expr']}` => **{st['value']}**" for st in sandbox_res.get("steps", []))
        sandbox_block = (
            "\n\n## KẾT QUẢ ĐÃ KIỂM CHỨNG BẰNG PYTHON SANDBOX (SỐ LIỆU CHÍNH XÁC 100%, BẮT BUỘC DÙNG ĐÚNG KẾT QUẢ NÀY):\n"
            f"{steps_lines}\n"
            f"  - Đáp số cuối cùng đã xác thực: **{sandbox_res.get('final_result')}**"
        )

    verify_directive = (
        "\n- TỰ KIỂM CHỨNG (SELF-VERIFY): Trước khi kết thúc, rà soát xem kết luận đã xét đủ điều kiện/ngoại lệ trong tài liệu và khớp tuyệt đối với kết quả kiểm chứng hay chưa."
        if enable_self_verify
        else ""
    )

    synth_system = (
        "Bạn là Chuyên gia Suy luận Tri thức AI. Thay vì chỉ chép lại nguyên văn tài liệu, hãy ÁP DỤNG các quy tắc, "
        "công thức hoặc nguyên lý trong nguồn vào đúng tình huống người dùng hỏi theo quy trình 4 phần rõ ràng:\n"
        "1. **Căn cứ / Quy tắc gốc trong tài liệu** (gắn trích dẫn [1], [2]...)\n"
        "2. **Phân tích & Áp dụng từng bước vào tình huống mới**\n"
        "3. **Tính toán / Kiểm chứng điều kiện** (dùng đúng kết quả Sandbox nếu có)\n"
        "4. **Kết luận & Lưu ý ngoại lệ**\n"
        "Cuối cùng luôn kèm 3 gợi ý tiếp theo dưới nhãn `---GỢI Ý TIẾP THEO---`."
        f"{verify_directive}"
    )

    synth_user = (
        f"Mục tiêu phân tích: {goal_text}\n"
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
                    "keep_alive": "30m",
                    "options": {
                        "num_ctx": int(profile.get("num_ctx") or 4096),
                        "num_predict": int(profile.get("num_predict") or 2048),
                        "temperature": 0.30,
                        "repeat_penalty": 1.12,
                    },
                },
                citations=citations,
                model_name=chosen_model,
                engine_name="reasoning_engine",
                collector=local_collector,
                is_disconnected=is_disconnected,
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

            step4 = _emit_step(len(trace_steps) + 1, "Tổng hợp & Kiểm chứng kết luận", "Đã hoàn thành lập luận có căn cứ trích dẫn.")
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
