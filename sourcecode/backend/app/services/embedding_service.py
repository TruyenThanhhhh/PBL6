"""BGE-M3 dense embeddings, stored as packed float32 in SQLite."""
import os
import logging
import struct
from pathlib import Path
from functools import lru_cache
from typing import List, Optional

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

logger = logging.getLogger(__name__)

# Tắt các thông báo kết nối kiểm tra ồn ào từ httpx và huggingface
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)


def _get_runtime_profile() -> dict:
    try:
        from app.services.hardware_profile_service import get_active_profile_config
        return get_active_profile_config()
    except Exception:
        return {"cpu_threads_cap": max(4, os.cpu_count() or 4), "embed_batch_size": EMBEDDING_BATCH_SIZE}


@lru_cache(maxsize=1)
def _get_sentence_transformer():
    import torch
    from sentence_transformers import SentenceTransformer

    profile = _get_runtime_profile()
    cpu_threads = int(profile.get("cpu_threads_cap") or max(4, os.cpu_count() or 4))
    try:
        torch.set_num_threads(cpu_threads)
    except Exception:
        pass

    try:
        # Ưu tiên sử dụng model đã tải trong cache cục bộ để xử lý tức thì, tránh timeout mạng
        model = SentenceTransformer(EMBEDDING_MODEL, device="cpu", local_files_only=True)
    except Exception:
        # Tự động tải từ Hugging Face nếu máy mới chưa có file cache
        model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")

    # Giới hạn chiều dài token hợp lý với kích thước chunk (~1100-1500 ký tự) để tăng tốc CPU gấp nhiều lần
    model.max_seq_length = 512
    return model


@lru_cache(maxsize=1)
def _get_fastembed_model():
    from fastembed import TextEmbedding
    return TextEmbedding(model_name=EMBEDDING_MODEL)


def _embed_with_sentence_transformers(texts: List[str]) -> List[List[float]]:
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
    return vectors.tolist()


def _embed_with_fastembed(texts: List[str]) -> List[List[float]]:
    return [list(map(float, vector)) for vector in _get_fastembed_model().embed(texts)]


def embed_texts(texts: List[str]) -> Optional[List[List[float]]]:
    if not ENABLE_DENSE_RETRIEVAL or not texts:
        return None

    backends = [EMBEDDING_BACKEND]
    if EMBEDDING_BACKEND != "fastembed":
        backends.append("fastembed")

    for backend in backends:
        try:
            if backend == "sentence_transformers":
                return _embed_with_sentence_transformers(texts)
            if backend == "fastembed":
                return _embed_with_fastembed(texts)
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
