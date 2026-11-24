"""BGE-M3 dense embeddings, stored as packed float32 in SQLite with low-RAM BF16 & idle auto-unload."""
import os
import logging
import struct
import threading
import time
from pathlib import Path
from typing import Any, List, Optional

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# Nếu đã có cache model BAAI/bge-m3 trong máy, bật offline mode để tải tức thì, tránh timeout và request mạng thừa
hf_cache = Path.home() / ".cache" / "huggingface" / "hub" / "models--BAAI--bge-m3"
if hf_cache.exists():
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from app.config import (
    EMBEDDING_BACKEND,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_MODEL,
    ENABLE_DENSE_RETRIEVAL,
)
from app.services.hardware_profile_service import (
    get_active_profile_config,
    get_memory_gb,
    trim_process_memory,
)

logger = logging.getLogger(__name__)

# Tắt các thông báo kết nối kiểm tra ồn ào từ httpx và huggingface
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

_EMBED_LOCK = threading.Lock()
_ST_MODEL: Any = None
_FE_MODEL: Any = None
_EMBED_LAST_USED_AT: float = 0.0


def _get_runtime_profile() -> dict:
    try:
        return get_active_profile_config()
    except Exception:
        return {"cpu_threads_cap": max(4, os.cpu_count() or 4), "embed_batch_size": EMBEDDING_BATCH_SIZE}


def is_embedding_model_loaded() -> bool:
    return _ST_MODEL is not None or _FE_MODEL is not None


def unload_embedding_model(trim_os: bool = True) -> bool:
    """Giải phóng BGE-M3 khỏi RAM ngay lập tức."""
    global _ST_MODEL, _FE_MODEL, _EMBED_LAST_USED_AT
    released = False
    with _EMBED_LOCK:
        if _ST_MODEL is not None:
            _ST_MODEL = None
            released = True
        if _FE_MODEL is not None:
            _FE_MODEL = None
            released = True
        _EMBED_LAST_USED_AT = 0.0
    if released and trim_os:
        trim_process_memory()
    return released


def maybe_evict_idle_embedding_model(max_idle_sec: Optional[float] = None) -> bool:
    """Tự động giải phóng model Embedding sau thời gian nhàn rỗi hoặc khi RAM trống xuống thấp."""
    if not is_embedding_model_loaded() or _EMBED_LAST_USED_AT <= 0:
        return False
    idle = time.monotonic() - _EMBED_LAST_USED_AT
    if max_idle_sec is None:
        profile = _get_runtime_profile()
        avail_ram = float((profile.get("specs") or {}).get("available_ram_gb") or get_memory_gb()[1])
        profile_id = str(profile.get("id") or "balanced").lower()
        if avail_ram < 4.5 or profile_id == "eco":
            max_idle_sec = 60.0
        elif profile_id == "balanced":
            max_idle_sec = 150.0
        else:
            max_idle_sec = 300.0
    if idle >= max_idle_sec:
        logger.info("🧹 Giải phóng Embedding model khỏi RAM sau %.0fs không sử dụng.", idle)
        return unload_embedding_model(trim_os=True)
    return False


def _load_sentence_transformer_instance() -> Any:
    import torch
    from sentence_transformers import SentenceTransformer

    profile = _get_runtime_profile()
    cpu_threads = int(profile.get("cpu_threads_cap") or max(4, os.cpu_count() or 4))
    try:
        torch.set_num_threads(cpu_threads)
    except Exception:
        pass

    # Trên CPU phổ thông (không có AVX512-BF16), float32 nhanh hơn ~6x so với bfloat16 giả lập (2.4s vs 14.8s / 8 chunks),
    # đồng thời giữ low_cpu_mem_usage=True để không nhân đôi RAM lúc nạp trọng số.
    load_kwargs = {"low_cpu_mem_usage": True}
    try:
        model = SentenceTransformer(
            EMBEDDING_MODEL,
            device="cpu",
            local_files_only=True,
            model_kwargs=load_kwargs,
        )
    except Exception:
        try:
            model = SentenceTransformer(EMBEDDING_MODEL, device="cpu", local_files_only=True)
        except Exception:
            try:
                model = SentenceTransformer(EMBEDDING_MODEL, device="cpu", model_kwargs=load_kwargs)
            except Exception:
                model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")

    # Chunks tối đa ~1100 ký tự (~220-320 tokens); 384 đủ phủ trọn vẹn mà tăng tốc attention CPU rõ rệt
    model.max_seq_length = 384
    return model


def _get_sentence_transformer():
    global _ST_MODEL, _EMBED_LAST_USED_AT
    with _EMBED_LOCK:
        if _ST_MODEL is None:
            _ST_MODEL = _load_sentence_transformer_instance()
        _EMBED_LAST_USED_AT = time.monotonic()
        return _ST_MODEL


def _get_fastembed_model():
    global _FE_MODEL, _EMBED_LAST_USED_AT
    with _EMBED_LOCK:
        if _FE_MODEL is None:
            from fastembed import TextEmbedding
            _FE_MODEL = TextEmbedding(model_name=EMBEDDING_MODEL)
        _EMBED_LAST_USED_AT = time.monotonic()
        return _FE_MODEL


def _embed_with_sentence_transformers(texts: List[str]) -> List[List[float]]:
    import numpy as np

    profile = _get_runtime_profile()
    try:
        import torch
        torch.set_num_threads(int(profile.get("cpu_threads_cap") or 4))
    except Exception:
        pass

    profile_batch = int(profile.get("embed_batch_size") or EMBEDDING_BATCH_SIZE)
    batch_size = min(profile_batch, 12) if profile.get("id") == "eco" else max(EMBEDDING_BATCH_SIZE, profile_batch)
    vectors = _get_sentence_transformer().encode(
        texts,
        batch_size=max(1, batch_size),
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    arr = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    arr = arr / np.where(norms > 0, norms, 1.0)
    return arr.tolist()


def _embed_with_fastembed(texts: List[str]) -> List[List[float]]:
    return [list(map(float, vector)) for vector in _get_fastembed_model().embed(texts)]


def embed_texts(texts: List[str], allow_unload: bool = True) -> Optional[List[List[float]]]:
    global _EMBED_LAST_USED_AT
    if not ENABLE_DENSE_RETRIEVAL or not texts:
        return None

    backends = [EMBEDDING_BACKEND]
    if EMBEDDING_BACKEND != "fastembed":
        backends.append("fastembed")

    for backend in backends:
        try:
            if backend == "sentence_transformers":
                out = _embed_with_sentence_transformers(texts)
            elif backend == "fastembed":
                out = _embed_with_fastembed(texts)
            else:
                continue
            _EMBED_LAST_USED_AT = time.monotonic()
            # Chỉ giải phóng ngay khi không nằm trong vòng lặp batch và RAM trống xuống mức nguy cấp (< 1.4 GB)
            if allow_unload and get_memory_gb()[1] < 1.4:
                unload_embedding_model(trim_os=True)
            return out
        except Exception:
            logger.exception(
                "Dense embedding backend '%s' unavailable with model %s",
                backend,
                EMBEDDING_MODEL,
            )

    logger.error("Dense embedding unavailable; continuing with FTS5")
    return None


def pack_vector(vector: List[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def unpack_vector(blob: bytes, dimensions: int) -> List[float]:
    return list(struct.unpack(f"{dimensions}f", blob))
