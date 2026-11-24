"""Routes a turn through local retrieval and optionally adds online sources, supporting sync and streaming."""
import json
import logging
import re
from typing import Any, Dict, List, Optional, AsyncGenerator, Awaitable, Callable
from starlette.concurrency import run_in_threadpool

from app.config import DEFAULT_LLM_MODEL, VISION_MODEL, TOP_K_RETRIEVAL
from app.services.chat_action_service import stream_chat_action
from app.services.hardware_profile_service import get_active_profile_config
from app.services.intent_service import classify_chat_intent
from app.services.llm_service import (
    generate_rag_answer,
    is_conversational_query,
    stream_rag_answer,
)
from app.services.reasoning_service import stream_autonomous_reasoning
from app.services.retrieval_service import (
    search_relevant_chunks,
    search_spanning_chunks,
    search_section_chunks,
    search_positional_chunks,
    detect_section_intent,
    detect_positional_intent,
    is_global_summary_query,
)
from app.services.web_search_service import search_web

logger = logging.getLogger(__name__)

TIME_SENSITIVE_KEYWORDS = [
    "hôm nay", "ngày mai", "hôm qua", "tin tức", "thời sự", "thời tiết",
    "mới nhất", "giá vàng", "tỷ giá", "chứng khoán", "giá cổ phiếu",
    "latest", "today", "weather", "news",
]

_LOCAL_SCOPE_CUE_RE = re.compile(
    r"\b(?:kho\s*tài\s*liệu|tài\s*liệu|file|tệp|chương\s*\d+|bài\s*\d+|trang\s*\d+|mục\s*\d+|điều\s*\d+|pdf|docx|xlsx)\b",
    re.IGNORECASE | re.UNICODE,
)

_WORKSPACE_INVENTORY_RE = re.compile(
    r"(?:trong\s+(?:kho\s+)?(?:tài\s*liệu|workspace|không\s*gian).{0,25}(?:có\s+những|gồm\s+những|có\s+các|liệt\s+kê).{0,25}(?:tài\s*liệu|file|tệp)\s*(?:nào)?|"
    r"(?:kho\s+tài\s+liệu|workspace)\s*(?:hiện\s*tại\s*)?(?:có|gồm)\s*(?:những\s*)?(?:tài\s*liệu|file|tệp)\s*nào)",
    re.IGNORECASE | re.UNICODE,
)


def _detect_web_intent(query: str) -> bool:
    q = (query or "").lower()
    if _LOCAL_SCOPE_CUE_RE.search(q) or _WORKSPACE_INVENTORY_RE.search(q):
        return False
    return any(kw in q for kw in TIME_SENSITIVE_KEYWORDS)


def _resolve_routing_modes(mode: str, query: str, include_web: Optional[bool] = None) -> tuple[bool, bool]:
    m = (mode or "auto").strip().lower()
    if m in ("web", "web_only"):
        return True, False
    if m == "hybrid":
        return True, True
    if m in ("local", "local_only", "private", "offline"):
        return False, True

    # Auto mode: ưu tiên Local RAG, chỉ kích hoạt Web khi có từ khóa thời gian thực sự (không đụng tài liệu cá nhân)
    auto_web = bool(include_web) or _detect_web_intent(query)
    return auto_web, True


_FOLLOW_UP_CUE_RE = re.compile(
    r"(?:\b(?:nó|đó|này|ở đâu|khi nào|thế nào|sao lại|còn gì|chi tiết|rõ hơn|tiếp theo|tiếp tục|"
    r"tại sao|vì sao|như thế nào|giải thích thêm|nữa không|ngoại lệ|ngắn gọn|dễ hiểu hơn|ví dụ|trường hợp|rủi ro)\b"
    r"|^(?:vậy|thế|còn|ngoài ra|tóm lại)\b)",
    re.IGNORECASE | re.UNICODE,
)
_ACTION_OR_QUIZ_QUERY_RE = re.compile(
    r"\b(?:tạo|soạn|sinh|ra|làm|câu\s*hỏi\s*ôn\s*tập|trắc\s*nghiệm|quiz|flashcard|mindmap|sơ\s*đồ\s*tư\s*duy|xuất\s*file)\b",
    re.IGNORECASE | re.UNICODE,
)


def _sanitize_incoming_query(query: str) -> str:
    """Làm sạch tiền tố ': ' hoặc '- [1]: ' do các nút gợi ý cũ gửi lên."""
    return re.sub(r"^\s*(?:[-*•]?\s*(?:\[\d+\])?\s*[:.-]\s*)+", "", (query or "").strip()).strip()


_ANAPHORIC_REF_RE = re.compile(
    r"\b(?:chương\s+này|bài\s+này|phần\s+này|mục\s+này|điều\s+này|ở\s+trên|vừa\s+nêu|vừa\s+rồi|đoạn\s+trên|câu\s+trên)\b",
    re.IGNORECASE | re.UNICODE,
)


def _build_retrieval_query(query: str, history: Optional[list[Dict[str, str]]] = None) -> str:
    """
    Xây dựng câu truy vấn độc lập và giàu ngữ cảnh cho RAG.
    Ghép câu hỏi trước khi câu hiện tại ngắn (<= 7 từ) và chứa đại từ/từ nối tiếp,
    HOẶC khi câu dài hơn (<= 15 từ) nhưng có tham chiếu tường minh ('chương này', 'bài này', 'vừa nêu', 'ở trên').
    """
    clean_q = _sanitize_incoming_query(query)
    words = clean_q.split()
    has_anaphora = bool(_ANAPHORIC_REF_RE.search(clean_q))
    if len(words) >= 8 and not (has_anaphora and len(words) <= 15):
        return clean_q

    history_turns = (history or [])[-8:]
    prior_user_queries = [
        _sanitize_incoming_query(turn["content"])
        for turn in history_turns
        if turn.get("role") == "user"
        and turn.get("content")
        and not _ACTION_OR_QUIZ_QUERY_RE.search(turn["content"])
    ]
    if not prior_user_queries:
        return clean_q

    q_lower = clean_q.lower()
    if has_anaphora or _FOLLOW_UP_CUE_RE.search(q_lower):
        # Bổ sung thêm tiêu đề/câu mở đầu của lượt trả lời trước khi có đại từ hồi chỉ ('chương này', 'bài này', 'ở trên')
        # để định vị chính xác mục đang bàn (vd 'nội dung chương 9' + 'hai đường thẳng cắt nhau thỏa mãn điều kiện K')
        extra_topic = ""
        if has_anaphora:
            for turn in reversed(history_turns):
                if turn.get("role") == "assistant" and turn.get("content"):
                    first_sent = re.split(r"[\n.!?]", str(turn["content"]).strip())[0][:120].strip()
                    if first_sent and not _ACTION_OR_QUIZ_QUERY_RE.search(first_sent):
                        extra_topic = first_sent
                    break
        parts = [prior_user_queries[-1], extra_topic, clean_q]
        return " ".join(p for p in parts if p).strip()

    return clean_q


def _fetch_pinned_history_chunks(
    workspace_id: str,
    history: Optional[list[Dict[str, Any]]],
    max_chunks: int = 4,
) -> List[Dict[str, Any]]:
    """Lấy trực tiếp các chunk trích dẫn từ lượt trả lời gần nhất khi người dùng hỏi nối tiếp ('chương này', 'bước 3 của bài này')."""
    if not history:
        return []
    refs: List[tuple[str, int]] = []
    for turn in reversed(history[-4:]):
        if turn.get("role") == "assistant" and turn.get("chunk_refs"):
            for item in (turn.get("chunk_refs") or [])[:3]:
                if isinstance(item, dict) and item.get("document_id") and item.get("chunk_index") is not None:
                    doc_id = str(item["document_id"])
                    c_idx = int(item["chunk_index"])
                    refs.append((doc_id, c_idx))
                    refs.append((doc_id, c_idx + 1))
            if refs:
                break
    if not refs:
        return []

    from app.database import get_db_connection
    conn = get_db_connection()
    try:
        grouped: Dict[str, List[int]] = {}
        for d_id, c_idx in refs:
            grouped.setdefault(d_id, []).append(c_idx)
        where_parts = []
        params: List[Any] = [workspace_id]
        for d_id, idxs in grouped.items():
            uniq = sorted(set(idxs))
            ph = ",".join("?" for _ in uniq)
            where_parts.append(f"(c.document_id = ? AND c.chunk_index IN ({ph}))")
            params.append(d_id)
            params.extend(uniq)
        rows = conn.execute(
            f"""
            SELECT c.id AS chunk_id, c.document_id, c.workspace_id, c.content,
                   c.page_number, c.chunk_index, d.file_name AS document_name,
                   COALESCE(d.version_number, 1) AS version_number, d.effective_date
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.workspace_id = ? AND ({" OR ".join(where_parts)})
            ORDER BY c.document_id, c.chunk_index ASC
            LIMIT ?
            """,
            (*params, max_chunks),
        ).fetchall()
        out = [dict(r) for r in rows]
        for c in out:
            if "page_label" not in c and c.get("page_number") is not None:
                c["page_label"] = f"Trang {c['page_number']}"
        return out
    finally:
        conn.close()


def _build_workspace_inventory_chunks(
    workspace_id: str,
    document_ids: Optional[list[str]] = None,
) -> List[Dict[str, Any]]:
    """Tạo danh sách nguồn xác thực 100% từ bảng documents + chunk đầu mỗi tài liệu khi hỏi tổng quan kho."""
    from app.database import get_db_connection

    conn = get_db_connection()
    try:
        if document_ids:
            ph = ",".join("?" for _ in document_ids)
            docs = conn.execute(
                f"""
                SELECT id, file_name, file_type, total_pages, total_chunks, version_number, effective_date
                FROM documents
                WHERE workspace_id = ? AND id IN ({ph}) AND COALESCE(is_latest, 1) = 1
                ORDER BY created_at DESC
                """,
                (workspace_id, *document_ids),
            ).fetchall()
        else:
            docs = conn.execute(
                """
                SELECT id, file_name, file_type, total_pages, total_chunks, version_number, effective_date
                FROM documents
                WHERE workspace_id = ? AND COALESCE(is_latest, 1) = 1
                ORDER BY created_at DESC
                """,
                (workspace_id,),
            ).fetchall()
        out: List[Dict[str, Any]] = []
        for d in docs[:12]:
            doc_id = d["id"]
            first_chunks = conn.execute(
                """
                SELECT chunk_index, page_number, content
                FROM document_chunks
                WHERE document_id = ?
                ORDER BY chunk_index ASC
                LIMIT 2
                """,
                (doc_id,),
            ).fetchall()
            preview_parts = []
            for fc in first_chunks:
                txt = (fc["content"] or "").strip()
                if txt:
                    preview_parts.append(txt[:420])
            preview_body = "\n".join(preview_parts) if preview_parts else "(Chưa có trích đoạn nội dung)"
            summary_text = (
                f"[TÀI LIỆU TRONG KHO TRI THỨC: {d['file_name']}]\n"
                f"- Định dạng: {(d['file_type'] or '').upper()} | Số trang: {d['total_pages'] or 1} | Số đoạn chỉ mục: {d['total_chunks'] or 0}\n"
                f"- Nội dung chính / Mục lục:\n{preview_body}"
            )
            out.append({
                "chunk_id": f"inventory_{doc_id}",
                "document_id": doc_id,
                "workspace_id": workspace_id,
                "document_name": d["file_name"],
                "page_number": 1,
                "page_label": "Tổng quan tài liệu",
                "chunk_index": 0,
                "version_number": d["version_number"] or 1,
                "effective_date": d["effective_date"],
                "content": summary_text,
            })
        return out
    finally:
        conn.close()


async def _retrieve_local_sources(
    workspace_id: str,
    query: str,
    history: Optional[list[Dict[str, str]]],
    top_k: int,
    selected_document_id: Optional[str] = None,
    document_ids: Optional[list[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Thuật toán chọn chiến lược truy xuất tối ưu:
    1. Nếu hỏi về Bài/Chương/Lab cụ thể -> Lấy toàn bộ các chunk liên tục thuộc phần đó.
    2. Nếu hỏi vị trí đầu/cuối tài liệu hoặc từ bắt đầu bằng chữ cái X -> Lấy theo thứ tự tài liệu.
    3. Nếu hỏi tóm tắt toàn bộ -> Lấy chunk phân phối đều khắp tài liệu.
    4. Tra cứu chi tiết -> Hybrid RAG (Exact + BM25 + Dense + Rerank).
    """
    # 0. Nếu hỏi tổng quan toàn kho tài liệu hiện tại (kể cả khi người dùng tick chọn tất cả / nhiều file ở cột Nguồn) -> trả về inventory xác thực
    is_single_doc_scope = bool(selected_document_id) and (not document_ids or len(document_ids) == 1)
    if not is_single_doc_scope and _WORKSPACE_INVENTORY_RE.search(query or ""):
        inv_chunks = await run_in_threadpool(_build_workspace_inventory_chunks, workspace_id, document_ids)
        if inv_chunks:
            return inv_chunks

    # 0b. Nếu là câu hỏi hồi chỉ trực tiếp ('chương này', 'bài này', 'bước 3 ở trên') và lịch sử có chunk_refs -> ghim thẳng nguồn lượt trước
    if history and _ANAPHORIC_REF_RE.search(query or ""):
        pinned = await run_in_threadpool(_fetch_pinned_history_chunks, workspace_id, history, 4)
        if pinned:
            return pinned

    # 1. Kiểm tra xem có đang hỏi về một Bài/Chương/Lab cụ thể không
    sec_intent = detect_section_intent(query, history)
    if sec_intent:
        sec_type, sec_num = sec_intent
        sec_query = _build_retrieval_query(query, history)
        section_chunks = await run_in_threadpool(
            search_section_chunks,
            workspace_id,
            sec_type,
            sec_num,
            12,
            selected_document_id,
            document_ids,
            sec_query,
        )
        if section_chunks:
            return section_chunks

    # 2. Kiểm tra câu hỏi theo vị trí (đầu file/cuối file) hoặc chữ cái mở đầu
    pos_intent = detect_positional_intent(query)
    if pos_intent:
        pos_type, letter_filter = pos_intent
        positional_chunks = await run_in_threadpool(
            search_positional_chunks,
            workspace_id,
            pos_type,
            letter_filter,
            5,
            selected_document_id,
            document_ids,
        )
        if positional_chunks:
            return positional_chunks

    # 3. Kiểm tra câu hỏi tóm tắt toàn bộ tài liệu
    if is_global_summary_query(query):
        spanning_chunks = await run_in_threadpool(
            search_spanning_chunks,
            workspace_id,
            query,
            8,
            selected_document_id,
            document_ids,
        )
        if spanning_chunks:
            return spanning_chunks

    # 4. Hybrid RAG thông thường cho câu hỏi tra cứu khái niệm hoặc chi tiết
    retrieval_query = _build_retrieval_query(query, history)
    profile_top_k = int(get_active_profile_config().get("top_k") or 5)
    effective_top_k = max(3, min(max(top_k, profile_top_k), profile_top_k + 1))
    return await run_in_threadpool(
        search_relevant_chunks,
        workspace_id,
        retrieval_query,
        effective_top_k,
        selected_document_id,
        document_ids,
    )


_STREAM_DELEGATED_INTENTS = frozenset({
    "create_quiz",
    "create_flashcards",
    "create_mindmap",
    "create_plan",
    "compose_document",
    "version_diff",
    "export_previous",
    "deep_reasoning",
})


async def answer_query(
    workspace_id: str,
    query: str,
    model: Optional[str] = None,
    include_web: bool = False,
    top_k: int = TOP_K_RETRIEVAL,
    history: Optional[list[Dict[str, str]]] = None,
    image_base64: Optional[str] = None,
    selected_document_id: Optional[str] = None,
    document_ids: Optional[list[str]] = None,
    mode: str = "auto",
    reasoning_mode: Optional[str] = "auto",
) -> Dict[str, Any]:
    query = _sanitize_incoming_query(query)
    history = (history or [])[-8:]
    intent = classify_chat_intent(
        query,
        reasoning_mode=reasoning_mode,
        has_image=bool(image_base64),
    )
    should_web, should_local = _resolve_routing_modes(mode, query, include_web)

    if intent.kind in _STREAM_DELEGATED_INTENTS:
        selected_model = (VISION_MODEL if image_base64 else (model or DEFAULT_LLM_MODEL))
        collector: Dict[str, Any] = {
            "full_answer": "",
            "citations": [],
            "model_used": selected_model,
            "engine": "ollama_local",
        }
        reasoning_steps: List[Dict[str, str]] = []
        async for event_line in stream_query(
            workspace_id=workspace_id,
            query=query,
            model=model,
            mode=mode,
            include_web=include_web,
            top_k=top_k,
            history=history,
            image_base64=image_base64,
            selected_document_id=selected_document_id,
            document_ids=document_ids,
            collector=collector,
            reasoning_mode=reasoning_mode or "auto",
        ):
            if not event_line.startswith("data:"):
                continue
            try:
                evt = json.loads(event_line[5:].strip())
            except Exception:
                continue
            if evt.get("stage") and evt.get("stage_label"):
                reasoning_steps.append({
                    "stage": str(evt["stage"]),
                    "label": str(evt["stage_label"]),
                })
            elif evt.get("error") and not collector.get("full_answer"):
                collector["full_answer"] = str(evt["error"])

        citations = collector.get("citations") or []
        has_web_citations = any(c.get("sourceType") == "web" or c.get("url") for c in citations)
        is_action = intent.kind != "deep_reasoning"
        return {
            "answer": collector.get("full_answer", ""),
            "citations": citations,
            "model_used": collector.get("model_used", selected_model),
            "engine": collector.get("engine", "ollama_local"),
            "workspace_id": workspace_id,
            "mode_requested": mode,
            "intent": intent.kind,
            "retrieval": (
                "action"
                if is_action
                else (
                    "hybrid"
                    if (citations and has_web_citations)
                    else ("local" if citations else "reasoning")
                )
            ),
            "selected_document_id": selected_document_id,
            "web_search": (
                "online"
                if has_web_citations
                else ("unavailable_or_no_results" if (should_web and not is_action) else "not_requested")
            ),
            "network_fallback": bool(should_web and not is_action and not has_web_citations),
            "action_result": collector.get("action_result"),
            "reasoning_steps": reasoning_steps,
        }

    is_chitchat = intent.kind == "chitchat"

    local_sources: List[Dict[str, Any]] = []
    if should_local and not is_chitchat:
        if image_base64 and not (selected_document_id or document_ids):
            local_sources = []
        else:
            local_sources = await _retrieve_local_sources(
                workspace_id=workspace_id,
                query=query,
                history=history,
                top_k=top_k,
                selected_document_id=selected_document_id,
                document_ids=document_ids,
            )

    web_sources: List[Dict[str, Any]] = []
    network_status = "not_requested"
    if should_web and not is_chitchat:
        web_sources = await search_web(query)
        network_status = "online" if web_sources else "unavailable_or_no_results"

    selected_model = (VISION_MODEL if image_base64 else (model or DEFAULT_LLM_MODEL))
    task_tier = "fast" if reasoning_mode == "fast" else ("deep" if reasoning_mode == "deep" else "standard")
    result = await generate_rag_answer(
        query,
        local_sources,
        selected_model,
        web_sources,
        history=history,
        image_base64=image_base64,
        task_tier=task_tier,
    )
    result.update({
        "workspace_id": workspace_id,
        "mode_requested": mode,
        "intent": intent.kind,
        "retrieval": (
            "conversational"
            if is_chitchat
            else (
                "hybrid"
                if (local_sources and web_sources)
                else ("local" if local_sources else ("web" if web_sources else "no_matches"))
            )
        ),
        "selected_document_id": selected_document_id,
        "web_search": network_status,
        "network_fallback": should_web and not web_sources and not is_chitchat,
    })
    return result


async def stream_query(
    workspace_id: str,
    query: str,
    model: Optional[str] = None,
    mode: str = "auto",
    include_web: Optional[bool] = None,
    top_k: int = TOP_K_RETRIEVAL,
    history: Optional[list[Dict[str, str]]] = None,
    image_base64: Optional[str] = None,
    selected_document_id: Optional[str] = None,
    document_ids: Optional[list[str]] = None,
    collector: Optional[Dict[str, Any]] = None,
    is_disconnected: Optional[Callable[[], Awaitable[bool]]] = None,
    reasoning_mode: Optional[str] = "auto",
) -> AsyncGenerator[str, None]:
    query = _sanitize_incoming_query(query)
    history = (history or [])[-8:]
    intent = classify_chat_intent(
        query,
        reasoning_mode=reasoning_mode,
        has_image=bool(image_base64),
    )
    selected_model = (VISION_MODEL if image_base64 else (model or DEFAULT_LLM_MODEL))

    # 1. Hành động tạo Học liệu, Đối chiếu Phiên bản hoặc Xuất nhanh câu trả lời trước
    if intent.kind in {
        "create_quiz",
        "create_flashcards",
        "create_mindmap",
        "create_plan",
        "version_diff",
        "export_previous",
    }:
        async for chunk in stream_chat_action(
            action_kind=intent.kind,
            params=intent.params,
            workspace_id=workspace_id,
            query=query,
            model_name=selected_model,
            history=history,
            selected_document_id=selected_document_id,
            document_ids=document_ids,
            collector=collector,
            is_disconnected=is_disconnected,
        ):
            yield chunk
        return

    is_chitchat = intent.kind == "chitchat"
    should_web, should_local = _resolve_routing_modes(mode, query, include_web)

    if not is_chitchat and (should_local or should_web):
        yield f"data: {json.dumps({'stage': 'retrieving', 'stage_label': 'Đang tìm thông tin trong tài liệu...'}, ensure_ascii=False)}\n\n"

    local_sources: List[Dict[str, Any]] = []
    if should_local and not is_chitchat:
        if image_base64 and not (selected_document_id or document_ids):
            local_sources = []
        else:
            local_sources = await _retrieve_local_sources(
                workspace_id=workspace_id,
                query=query,
                history=history,
                top_k=top_k,
                selected_document_id=selected_document_id,
                document_ids=document_ids,
            )

    if is_disconnected and await is_disconnected():
        return

    # 2. Hành động Soạn thảo Văn bản chuẩn thể thức & xuất Word/PDF/MD
    if intent.kind == "compose_document":
        if not local_sources and should_local:
            local_sources = await run_in_threadpool(
                search_spanning_chunks,
                workspace_id,
                query,
                6,
                selected_document_id,
                document_ids,
            )
        async for chunk in stream_chat_action(
            action_kind=intent.kind,
            params=intent.params,
            workspace_id=workspace_id,
            query=query,
            model_name=selected_model,
            context_chunks=local_sources,
            history=history,
            selected_document_id=selected_document_id,
            document_ids=document_ids,
            collector=collector,
            is_disconnected=is_disconnected,
        ):
            yield chunk
        return

    web_sources: List[Dict[str, Any]] = []
    if should_web and not is_chitchat:
        if local_sources:
            yield f"data: {json.dumps({'stage': 'web_search', 'stage_label': 'Đang đối chiếu thêm nguồn Internet...'}, ensure_ascii=False)}\n\n"
        else:
            yield f"data: {json.dumps({'stage': 'web_search', 'stage_label': 'Đang tìm kiếm thông tin trên Internet...'}, ensure_ascii=False)}\n\n"
        web_sources = await search_web(query)

    if is_disconnected and await is_disconnected():
        return

    # 3. Động cơ Suy luận Tự chủ Đa bước (Multi-hop + Python Sandbox + Cross-Check + Self-Verify)
    if intent.kind == "deep_reasoning":
        async for chunk in stream_autonomous_reasoning(
            workspace_id=workspace_id,
            query=query,
            initial_chunks=local_sources,
            model_name=selected_model,
            web_sources=web_sources,
            history=history,
            selected_document_id=selected_document_id,
            document_ids=document_ids,
            collector=collector,
            is_disconnected=is_disconnected,
        ):
            yield chunk
        return

    task_tier = "fast" if reasoning_mode == "fast" else ("deep" if reasoning_mode == "deep" else "standard")
    async for chunk in stream_rag_answer(
        query,
        local_sources,
        selected_model,
        web_sources,
        history=history,
        image_base64=image_base64,
        collector=collector,
        is_disconnected=is_disconnected,
        task_tier=task_tier,
    ):
        yield chunk
