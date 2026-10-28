"""Routes a turn through local retrieval and optionally adds online sources."""
import logging
from typing import Any, Dict, Optional
from starlette.concurrency import run_in_threadpool

from app.config import DEFAULT_LLM_MODEL, VISION_MODEL, TOP_K_RETRIEVAL
from app.services.llm_service import generate_rag_answer
from app.services.retrieval_service import search_relevant_chunks
from app.services.web_search_service import search_web

logger = logging.getLogger(__name__)


async def answer_query(workspace_id: str, query: str, model: Optional[str] = None,
                       include_web: bool = False, top_k: int = TOP_K_RETRIEVAL,
                       history: Optional[list[Dict[str, str]]] = None,
                       image_base64: Optional[str] = None,
                       selected_document_id: Optional[str] = None) -> Dict[str, Any]:
    history = (history or [])[-8:]
    prior_user_context = " ".join(turn["content"] for turn in history if turn.get("role") == "user")
    retrieval_query = f"{prior_user_context} {query}".strip()
    local_sources = await run_in_threadpool(
        search_relevant_chunks, workspace_id, retrieval_query, top_k, selected_document_id
    )
    web_sources = []
    network_status = "not_requested"
    if include_web:
        web_sources = await search_web(query)
        network_status = "online" if web_sources else "unavailable_or_no_results"

    # Local Ollama remains primary; the generator degrades to source excerpts if it is down.
    selected_model = (VISION_MODEL if image_base64 else (model or DEFAULT_LLM_MODEL))
    result = await generate_rag_answer(query, local_sources, selected_model,
                                       web_sources, history=history, image_base64=image_base64)
    result.update({
        "workspace_id": workspace_id,
        "retrieval": "hybrid" if local_sources else "no_local_matches",
        "selected_document_id": selected_document_id,
        "web_search": network_status,
        "network_fallback": include_web and not web_sources,
    })
    return result
