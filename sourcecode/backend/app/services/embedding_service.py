"""Optional BGE-M3 dense embeddings, stored as packed float32 in SQLite."""
import logging
import struct
from functools import lru_cache
from typing import List, Optional

from app.config import EMBEDDING_MODEL, ENABLE_DENSE_RETRIEVAL

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_model():
    from fastembed import TextEmbedding
    return TextEmbedding(model_name=EMBEDDING_MODEL)


def embed_texts(texts: List[str]) -> Optional[List[List[float]]]:
    if not ENABLE_DENSE_RETRIEVAL or not texts:
        return None
    try:
        return [list(map(float, vector)) for vector in _get_model().embed(texts)]
    except Exception:
        logger.exception("Dense embedding unavailable; continuing with FTS5")
        return None


def pack_vector(vector: List[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def unpack_vector(blob: bytes, dimensions: int) -> List[float]:
    return list(struct.unpack(f"{dimensions}f", blob))
