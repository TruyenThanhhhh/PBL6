"""Routes a turn through local retrieval and optionally adds online sources, supporting sync and streaming."""
import logging
from typing import Any, Dict, List, Optional, AsyncGenerator
from starlette.concurrency import run_in_threadpool

from app.config import DEFAULT_LLM_MODEL, VISION_MODEL, TOP_K_RETRIEVAL
from app.services.llm_service import generate_rag_answer, stream_rag_answer
from app.services.retrieval_service import search_relevant_chunks
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
    prior_user_context = " ".join(turn["content"] for turn in history if turn.get("role") == "user")
    retrieval_query = f"{prior_user_context} {query}".strip()

    should_web, should_local = _resolve_routing_modes(mode, query, include_web)

    local_sources: List[Dict[str, Any]] = []
    if should_local:
        if image_base64 and not (selected_document_id or document_ids):
            local_sources = []
        else:
            retrieval_limit = min(top_k, 2) if image_base64 else top_k
            local_sources = await run_in_threadpool(
                search_relevant_chunks,
                workspace_id,
                retrieval_query,
                retrieval_limit,
                selected_document_id,
                document_ids,
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
    prior_user_context = " ".join(turn["content"] for turn in history if turn.get("role") == "user")
    retrieval_query = f"{prior_user_context} {query}".strip()

    should_web, should_local = _resolve_routing_modes(mode, query, include_web)

    local_sources: List[Dict[str, Any]] = []
    if should_local:
        if image_base64 and not (selected_document_id or document_ids):
            local_sources = []
        else:
            retrieval_limit = min(top_k, 2) if image_base64 else top_k
            local_sources = await run_in_threadpool(
                search_relevant_chunks,
                workspace_id,
                retrieval_query,
                retrieval_limit,
                selected_document_id,
                document_ids,
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
