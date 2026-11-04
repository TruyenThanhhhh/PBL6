"""BGE-M3 dense embeddings, stored as packed float32 in SQLite."""
import logging
import struct
from functools import lru_cache
from typing import List, Optional

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


@lru_cache(maxsize=1)
def _get_sentence_transformer():
    from sentence_transformers import SentenceTransformer
    try:
        # Ưu tiên sử dụng model đã tải trong cache cục bộ để xử lý tức thì, tránh timeout mạng
        return SentenceTransformer(EMBEDDING_MODEL, device="cpu", local_files_only=True)
    except Exception:
        # Tự động tải từ Hugging Face nếu máy mới chưa có file cache
        return SentenceTransformer(EMBEDDING_MODEL, device="cpu")


@lru_cache(maxsize=1)
def _get_fastembed_model():
    from fastembed import TextEmbedding
    return TextEmbedding(model_name=EMBEDDING_MODEL)


def _embed_with_sentence_transformers(texts: List[str]) -> List[List[float]]:
    vectors = _get_sentence_transformer().encode(
        texts,
        batch_size=EMBEDDING_BATCH_SIZE,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return [list(map(float, vector)) for vector in vectors]


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
