"""Routes a turn through local retrieval and optionally adds online sources, supporting sync and streaming."""
import json
import logging
import re
from typing import Any, Dict, List, Optional, AsyncGenerator
from starlette.concurrency import run_in_threadpool

from app.config import DEFAULT_LLM_MODEL, VISION_MODEL, TOP_K_RETRIEVAL
from app.services.llm_service import generate_rag_answer, stream_rag_answer
from app.services.retrieval_service import (
    search_relevant_chunks,
    search_spanning_chunks,
    search_section_chunks,
    detect_section_intent,
    is_global_summary_query,
)
from app.services.vocabulary_listing_service import extract_vocabulary_listing
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


def _is_document_summary_query(query: str) -> bool:
    return is_global_summary_query(query) and bool(re.search(
        r"\b(?:tài\s+liệu|file|tệp|pdf|slide|presentation|bài\s+trình\s+bày|nội\s+dung\s+chính)\b",
        query,
        flags=re.IGNORECASE,
    ))


def _apply_document_scope_to_routing(
    mode: str,
    query: str,
    selected_document_id: Optional[str],
    document_ids: Optional[list[str]],
    should_web: bool,
    should_local: bool,
) -> tuple[bool, bool]:
    # A selected local source, or an explicit document-summary request, must
    # not be silently ignored just because the UI is in Internet mode.
    if (selected_document_id or document_ids or _is_document_summary_query(query)) and (mode or "").lower() == "web":
        return False, True
    return should_web, should_local


def _build_retrieval_query(query: str, history: Optional[list[Dict[str, str]]] = None) -> str:
    """
    Xây dựng câu truy vấn độc lập và giàu ngữ cảnh cho RAG.
    - Kết hợp câu hỏi user hiện tại với các từ khóa trọng tâm của câu hỏi user trước.
    - Đối với câu hỏi ngắn / chứa đại từ, tái sử dụng câu hỏi gần nhất để giảm thiểu tìm kiếm lệch hướng.
    """
    history_turns = (history or [])[-10:]
    prior_user_queries = [
        turn["content"].strip()
        for turn in history_turns
        if turn.get("role") == "user" and turn.get("content")
    ]
    if not prior_user_queries:
        return query.strip()

    q_lower = query.lower().strip()
    pronouns = [
        "nó", "đó", "này", "ở đâu", "khi nào", "thế nào", "sao lại", "còn gì",
        "chi tiết", "rõ hơn", "tiếp", "tại sao", "vì sao", "như thế nào", "giải thích"
    ]
    is_follow_up = len(q_lower.split()) <= 7 or any(p in q_lower for p in pronouns)

    if is_follow_up:
        last_query = prior_user_queries[-1]
        combined = f"{last_query} {query}".strip()
        if len(prior_user_queries) >= 2:
            context_query = prior_user_queries[-2]
            combined = f"{context_query} {combined}".strip()
        return combined

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
    2. Nếu hỏi tóm tắt toàn bộ -> Lấy chunk phân phối đều khắp tài liệu.
    3. Tra cứu chi tiết -> Hybrid RAG (BM25 + Dense + Rerank).
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
            16,
            selected_document_id,
            document_ids,
        )
        if section_chunks:
            return section_chunks

    # 2. Kiểm tra câu hỏi tóm tắt toàn bộ tài liệu
    if is_global_summary_query(query):
        spanning_chunks = await run_in_threadpool(
            search_spanning_chunks,
            workspace_id,
            query,
            32,
            selected_document_id,
            document_ids,
            7800,
        )
        if spanning_chunks:
            return spanning_chunks

    # 3. Hybrid RAG thông thường cho câu hỏi tra cứu khái niệm hoặc chi tiết
    retrieval_query = _build_retrieval_query(query, history)
    effective_top_k = max(top_k, 8)
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
    if not image_base64:
        vocabulary_listing = await run_in_threadpool(
            extract_vocabulary_listing,
            workspace_id,
            query,
            selected_document_id,
            document_ids,
        )
        if vocabulary_listing:
            vocabulary_listing.update({
                "workspace_id": workspace_id,
                "mode_requested": mode,
                "retrieval": "exact_document_listing",
                "selected_document_id": selected_document_id,
                "web_search": "not_requested",
                "network_fallback": False,
            })
            return vocabulary_listing

    should_web, should_local = _resolve_routing_modes(mode, query, include_web)
    should_web, should_local = _apply_document_scope_to_routing(
        mode, query, selected_document_id, document_ids, should_web, should_local
    )

    local_sources: List[Dict[str, Any]] = []
    if should_local:
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
    if should_web:
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
        "retrieval": "hybrid" if (local_sources and web_sources) else ("local" if local_sources else ("web" if web_sources else "no_matches")),
        "selected_document_id": selected_document_id,
        "web_search": network_status,
        "network_fallback": should_web and not web_sources,
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
) -> AsyncGenerator[str, None]:
    history = (history or [])[-8:]
    if not image_base64:
        vocabulary_listing = await run_in_threadpool(
            extract_vocabulary_listing,
            workspace_id,
            query,
            selected_document_id,
            document_ids,
        )
        if vocabulary_listing:
            answer = vocabulary_listing["answer"]
            citations = vocabulary_listing["citations"]
            yield f"data: {json.dumps({'citations': citations, 'model_used': vocabulary_listing['model_used'], 'engine': vocabulary_listing['engine']}, ensure_ascii=False)}\n\n"
            if collector is not None:
                collector["full_answer"] = answer
                collector["citations"] = citations
                collector["model_used"] = vocabulary_listing["model_used"]
                collector["engine"] = vocabulary_listing["engine"]
            for offset in range(0, len(answer), 240):
                yield f"data: {json.dumps({'delta': answer[offset:offset + 240]}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'answer': answer, 'done': True}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return

    should_web, should_local = _resolve_routing_modes(mode, query, include_web)
    should_web, should_local = _apply_document_scope_to_routing(
        mode, query, selected_document_id, document_ids, should_web, should_local
    )

    local_sources: List[Dict[str, Any]] = []
    if should_local:
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
    if should_web:
        web_sources = await search_web(query)

    selected_model = (VISION_MODEL if image_base64 else (model or DEFAULT_LLM_MODEL))

    async for chunk in stream_rag_answer(
        query,
        local_sources,
        selected_model,
        web_sources,
        history=history,
        image_base64=image_base64,
        collector=collector,
    ):
        yield chunk
