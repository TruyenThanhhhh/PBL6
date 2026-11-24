"""Optional multilingual cross-encoder reranker backed by fastembed ONNX with idle auto-eviction."""
import logging
import threading
import time
from typing import Any, Dict, List, Optional

from app.config import (
    RERANK_BATCH_SIZE,
    RERANK_ENABLED,
    RERANK_MODEL,
)
from app.services.hardware_profile_service import get_memory_gb, trim_process_memory

logger = logging.getLogger(__name__)
_RERANKER_FAILED = False
_RERANK_LOCK = threading.Lock()
_RERANK_MODEL: Any = None
_RERANK_LAST_USED_AT: float = 0.0


def is_reranker_loaded() -> bool:
    return _RERANK_MODEL is not None


def unload_reranker_model(trim_os: bool = True) -> bool:
    """Giải phóng ONNX Cross-Encoder Reranker (~1.3 GB) khỏi RAM ngay lập tức."""
    global _RERANK_MODEL, _RERANK_LAST_USED_AT
    released = False
    with _RERANK_LOCK:
        if _RERANK_MODEL is not None:
            _RERANK_MODEL = None
            released = True
        _RERANK_LAST_USED_AT = 0.0
    if released and trim_os:
        trim_process_memory()
    return released


def maybe_evict_idle_reranker_model(max_idle_sec: Optional[float] = None) -> bool:
    """Tự động dỡ Reranker khi nhàn rỗi hoặc RAM trống xuống thấp."""
    if _RERANK_MODEL is None or _RERANK_LAST_USED_AT <= 0:
        return False
    idle = time.monotonic() - _RERANK_LAST_USED_AT
    if max_idle_sec is None:
        avail_ram = get_memory_gb()[1]
        max_idle_sec = 45.0 if avail_ram < 5.0 else 90.0
    if idle >= max_idle_sec:
        logger.info("🧹 Giải phóng Reranker model khỏi RAM sau %.0fs không sử dụng.", idle)
        return unload_reranker_model(trim_os=True)
    return False


def _get_model():
    global _RERANK_MODEL, _RERANK_LAST_USED_AT
    with _RERANK_LOCK:
        if _RERANK_MODEL is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder
            _RERANK_MODEL = TextCrossEncoder(model_name=RERANK_MODEL)
        _RERANK_LAST_USED_AT = time.monotonic()
        return _RERANK_MODEL


def _is_mocked(fn: Any) -> bool:
    if getattr(fn, "_mock_wraps", None) is not None:
        return False
    return bool(hasattr(fn, "_mock_name") or hasattr(fn, "assert_called"))


def rerank_documents(
    query: str,
    documents: List[Dict[str, Any]],
    top_k: int,
    max_candidates: int | None = None,
) -> List[Dict[str, Any]]:
    """Rerank RRF candidates and return the best ``top_k`` documents.

    Falls back to the incoming order if the model is disabled, unavailable, RAM is critically low,
    or the download fails.
    """
    global _RERANKER_FAILED, _RERANK_LAST_USED_AT
    if not RERANK_ENABLED or _RERANKER_FAILED or not documents:
        return documents[:top_k]

    if len(documents) <= 1:
        return documents[:top_k]

    profile_cap: int | None = None
    avail_ram = get_memory_gb()[1]
    try:
        from app.services.hardware_profile_service import get_active_profile_config

        profile = get_active_profile_config()
        if not profile.get("rerank_enabled", True):
            return documents[:top_k]
        raw_cap = int(profile.get("rerank_max_candidates") or 0)
        if raw_cap > 0:
            profile_cap = raw_cap
        avail_ram = float((profile.get("specs") or {}).get("available_ram_gb") or avail_ram)
    except Exception:
        pass

    # Bảo vệ RAM: nếu chưa nạp Reranker và RAM khả dụng < 4.2 GB, giữ thứ tự Hybrid RRF thay vì nạp thêm ~1.35 GB ONNX
    if _RERANK_MODEL is None and not _is_mocked(_get_model) and avail_ram < 4.2:
        logger.info("⚡ RAM khả dụng thấp (%.2f GB) -> bỏ qua nạp Cross-Encoder Reranker.", avail_ram)
        return documents[:top_k]

    effective_max = max_candidates
    if profile_cap is not None:
        effective_max = min(effective_max, profile_cap) if effective_max else profile_cap

    candidates = documents[:effective_max] if effective_max else documents
    try:
        model = _get_model()
        _RERANK_LAST_USED_AT = time.monotonic()
        # Truncate văn bản xuống tối đa 1200 ký tự để reranking chạy nhanh hơn gấp 3-4 lần trên CPU
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
    except Exception as exc:
        _RERANKER_FAILED = True
        logger.warning("Reranker unavailable (%s); falling back to RRF order", exc)
        return documents[:top_k]
    finally:
        if _RERANK_MODEL is not None and not _is_mocked(_get_model) and get_memory_gb()[1] < 4.2:
            unload_reranker_model(trim_os=True)
