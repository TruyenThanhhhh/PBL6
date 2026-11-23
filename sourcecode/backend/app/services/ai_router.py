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
    "mới nhất", "hiện tại", "bây giờ", "giá vàng", "tỷ giá", "chứng khoán",
    "sự kiện", "update", "latest", "today", "weather", "news"
]


def _detect_web_intent(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in TIME_SENSITIVE_KEYWORDS)


def _resolve_routing_modes(mode: str, query: str, include_web: Optional[bool] = None) -> tuple[bool, bool]:
    m = (mode or "auto").lower()
    if m == "web":
        return True, False
    if m == "hybrid":
        return True, True
    if m == "local":
        return False, True

    # Auto mode: ưu tiên Local RAG, chỉ kích hoạt Web khi có từ khóa thời gian hoặc được yêu cầu
    auto_web = bool(include_web) or _detect_web_intent(query)
    return auto_web, True


_FOLLOW_UP_CUE_RE = re.compile(
    r"(?:\b(?:nó|đó|này|ở đâu|khi nào|thế nào|sao lại|còn gì|chi tiết|rõ hơn|tiếp theo|tiếp tục|"
    r"tại sao|vì sao|như thế nào|giải thích thêm|nữa không)\b|^(?:vậy|thế|còn|ngoài ra)\b)",
    re.IGNORECASE | re.UNICODE,
)


def _build_retrieval_query(query: str, history: Optional[list[Dict[str, str]]] = None) -> str:
    """
    Xây dựng câu truy vấn độc lập và giàu ngữ cảnh cho RAG.
    Chỉ ghép câu hỏi trước khi câu hỏi hiện tại thực sự chứa đại từ/từ nối tiếp,
    tránh làm nhiễu các truy vấn tra cứu thuật ngữ/Kanji độc lập (vd: '夢').
    """
    history_turns = (history or [])[-8:]
    prior_user_queries = [
        turn["content"].strip()
        for turn in history_turns
        if turn.get("role") == "user" and turn.get("content")
    ]
    if not prior_user_queries:
        return query.strip()

    q_lower = query.lower().strip()
    if _FOLLOW_UP_CUE_RE.search(q_lower):
        return f"{prior_user_queries[-1]} {query}".strip()

    return query.strip()


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
    # 1. Kiểm tra xem có đang hỏi về một Bài/Chương/Lab cụ thể không
    sec_intent = detect_section_intent(query, history)
    if sec_intent:
        sec_type, sec_num = sec_intent
        section_chunks = await run_in_threadpool(
            search_section_chunks,
            workspace_id,
            sec_type,
            sec_num,
            12,
            selected_document_id,
            document_ids,
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
            12,
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
) -> Dict[str, Any]:
    history = (history or [])[-8:]
    is_chitchat = is_conversational_query(query) and not image_base64
    should_web, should_local = _resolve_routing_modes(mode, query, include_web)

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
    result = await generate_rag_answer(
        query,
        local_sources,
        selected_model,
        web_sources,
        history=history,
        image_base64=image_base64,
    )
    result.update({
        "workspace_id": workspace_id,
        "mode_requested": mode,
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
    history = (history or [])[-8:]
    intent = classify_chat_intent(
        query,
        reasoning_mode=reasoning_mode,
        has_image=bool(image_base64),
    )
    selected_model = (VISION_MODEL if image_base64 else (model or DEFAULT_LLM_MODEL))

    # 1. Hành động tạo Học liệu hoặc Đối chiếu Phiên bản (không cần RAG chat tiêu chuẩn)
    if intent.kind in {"create_quiz", "create_flashcards", "create_mindmap", "create_plan", "version_diff"}:
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

    async for chunk in stream_rag_answer(
        query,
        local_sources,
        selected_model,
        web_sources,
        history=history,
        image_base64=image_base64,
        collector=collector,
        is_disconnected=is_disconnected,
    ):
        yield chunk
