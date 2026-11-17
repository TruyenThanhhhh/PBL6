"""Optional multilingual cross-encoder reranker backed by fastembed ONNX."""
import logging
from functools import lru_cache
from typing import Any, Dict, List

from app.config import (
    RERANK_BATCH_SIZE,
    RERANK_ENABLED,
    RERANK_MODEL,
)

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_model():
    from fastembed.rerank.cross_encoder import TextCrossEncoder
    return TextCrossEncoder(model_name=RERANK_MODEL)


def rerank_documents(
    query: str,
    documents: List[Dict[str, Any]],
    top_k: int,
    max_candidates: int | None = None,
) -> List[Dict[str, Any]]:
    """Rerank RRF candidates and return the best ``top_k`` documents.

    Falls back to the incoming order if the model is disabled, unavailable or
    the download fails. Retrieval must keep working even without the optional
    reranker model.
    """
    if not RERANK_ENABLED or not documents:
        return documents[:top_k]

    if len(documents) <= 1:
        return documents[:top_k]

    candidates = documents[:max_candidates] if max_candidates else documents
    try:
        model = _get_model()
        # Truncate văn bản xuống tối đa 1200 ký tự để reranking chạy nhanh hơn gấp 3-4 lần trên CPU
        # mà vẫn đảm bảo đánh giá chính xác ngữ nghĩa của phần mở đầu và trọng tâm chunk
        scores = list(
            model.rerank(
                query,
                [str(doc.get("content", ""))[:1200] for doc in candidates],
                batch_size=RERANK_BATCH_SIZE,
            )
        )
        ranked = sorted(
            zip(candidates, scores),
            key=lambda pair: float(pair[1]),
            reverse=True,
        )
        result = []
        for doc, score in ranked[:top_k]:
            enriched = dict(doc)
            enriched["rerank_score"] = float(score)
            result.append(enriched)
        return result
    except Exception:
        logger.exception("Reranker unavailable; falling back to RRF order")
        return documents[:top_k]
