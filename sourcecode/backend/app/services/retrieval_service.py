"""Workspace-scoped hybrid retrieval: SQLite FTS5 plus optional BGE-M3 (NumPy SIMD accelerated) and RRF."""
import math
import re
from typing import Any, Dict, List, Optional

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore

from app.config import (
    EMBEDDING_MODEL,
    RERANK_MAX_CANDIDATES,
    RETRIEVAL_CANDIDATE_MULTIPLIER,
    RRF_K,
    SIMILARITY_CUTOFF,
    TOP_K_RETRIEVAL,
)
from app.database import get_db_connection
from app.services.embedding_service import embed_texts, unpack_vector
from app.services.reranker_service import rerank_documents


def _cosine(left: List[float], right: List[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    norm_left = math.sqrt(sum(a * a for a in left))
    norm_right = math.sqrt(sum(b * b for b in right))
    return dot / (norm_left * norm_right) if norm_left and norm_right else 0.0


def search_relevant_chunks(
    workspace_id: str,
    query: str,
    top_k: int = TOP_K_RETRIEVAL,
    document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        clean_query = re.sub(r"[^\w\s]", " ", query, flags=re.UNICODE)
        tokens = [token for token in clean_query.split() if len(token) > 1]
        candidate_limit = max(top_k * RETRIEVAL_CANDIDATE_MULTIPLIER, top_k)
        if document_id:
            document_filter = " AND c.document_id = ?"
            document_params = (document_id,)
        elif document_ids:
            placeholders = ",".join("?" for _ in document_ids)
            document_filter = f" AND c.document_id IN ({placeholders})"
            document_params = tuple(document_ids)
        else:
            document_filter = ""
            document_params = ()
        sparse: List[Dict[str, Any]] = []
        if tokens:
            match_query = " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens)
            try:
                cursor.execute(
                    """SELECT c.id AS chunk_id, c.document_id, c.workspace_id, c.content,
                       c.page_number, c.chunk_index, d.file_name AS document_name,
                       bm25(chunks_fts) AS score
                    FROM chunks_fts f
                    JOIN document_chunks c ON c.id = f.chunk_id
                    JOIN documents d ON d.id = c.document_id
                    WHERE chunks_fts MATCH ? AND c.workspace_id = ?{document_filter}
                    ORDER BY score ASC LIMIT ?
                """.format(document_filter=document_filter),
                    (match_query, workspace_id, *document_params, candidate_limit),
                )
                sparse = [dict(row) for row in cursor.fetchall()]
            except Exception:
                # FTS syntax differences or a damaged index should not take down chat.
                sparse = []

        dense: List[Dict[str, Any]] = []
        cursor.execute(
            "SELECT 1 FROM chunk_embeddings e JOIN document_chunks c ON c.id = e.chunk_id "
            "WHERE c.workspace_id = ? AND e.model = ?" + document_filter + " LIMIT 1",
            (workspace_id, EMBEDDING_MODEL, *document_params),
        )
        has_dense_index = cursor.fetchone() is not None
        query_vectors = embed_texts([query]) if has_dense_index else None
        if query_vectors:
            cursor.execute(
                """
                SELECT c.id AS chunk_id, c.document_id, c.workspace_id, c.content,
                       c.page_number, c.chunk_index, d.file_name AS document_name,
                       e.vector, e.dimensions
                FROM chunk_embeddings e
                JOIN document_chunks c ON c.id = e.chunk_id
                JOIN documents d ON d.id = c.document_id
                WHERE c.workspace_id = ? AND e.model = ?{document_filter}
            """.format(document_filter=document_filter),
                (workspace_id, EMBEDDING_MODEL, *document_params),
            )
            rows = cursor.fetchall()
            if rows and np is not None:
                q_vec = np.asarray(query_vectors[0], dtype=np.float32)
                q_norm = float(np.linalg.norm(q_vec))
                if q_norm > 0:
                    q_vec = q_vec / q_norm
                for row in rows:
                    item = dict(row)
                    blob = item.pop("vector")
                    dims = item.pop("dimensions")
                    vec = np.frombuffer(blob, dtype=np.float32, count=dims)
                    v_norm = float(np.linalg.norm(vec))
                    item["score"] = float(np.dot(q_vec, vec) / v_norm) if v_norm > 0 else 0.0
                    dense.append(item)
            else:
                for row in rows:
                    item = dict(row)
                    vector = unpack_vector(item.pop("vector"), item.pop("dimensions"))
                    item["score"] = _cosine(query_vectors[0], vector)
                    dense.append(item)
            dense = [item for item in dense if item.get("score", 0.0) >= SIMILARITY_CUTOFF]
            dense.sort(key=lambda item: item["score"], reverse=True)
            dense = dense[:candidate_limit]

        # Reciprocal Rank Fusion keeps scores from the two retrieval systems comparable.
        merged: Dict[str, Dict[str, Any]] = {}
        for ranking in (sparse, dense):
            for rank, item in enumerate(ranking, start=1):
                chunk_id = item["chunk_id"]
                if chunk_id not in merged:
                    merged[chunk_id] = {key: value for key, value in item.items() if key != "score"}
                    merged[chunk_id]["rrf_score"] = 0.0
                merged[chunk_id]["rrf_score"] += 1.0 / (RRF_K + rank)
        ranked = sorted(merged.values(), key=lambda item: item["rrf_score"], reverse=True)

        # A direct question about a named file (for example, "Data.txt chứa gì?")
        # should retrieve that file even when its name is absent from extracted text.
        query_terms = {term.lower() for term in tokens if len(term) > 2}
        named_ids: set[str] = set()
        if query_terms:
            cursor.execute(
                """
                SELECT c.id AS chunk_id, c.document_id, c.workspace_id, c.content,
                       c.page_number, c.chunk_index, d.file_name AS document_name
                FROM documents d JOIN document_chunks c ON c.document_id = d.id
                WHERE d.workspace_id = ?{document_filter}
                ORDER BY d.created_at DESC, c.chunk_index ASC
            """.format(document_filter=document_filter.replace("c.document_id", "d.id")),
                (workspace_id, *document_params),
            )
            named_matches = []
            for row in cursor.fetchall():
                item = dict(row)
                stem = re.sub(r"\.[^.]+$", "", item["document_name"]).lower()
                name_terms = set(re.findall(r"[\w]+", stem, flags=re.UNICODE))
                if name_terms & query_terms:
                    named_matches.append(item)
            named_ids = {item["chunk_id"] for item in named_matches}
            ranked = named_matches + [item for item in ranked if item["chunk_id"] not in named_ids]

        if named_ids:
            pinned = [item for item in ranked if item["chunk_id"] in named_ids][:top_k]
            pinned = rerank_documents(query, pinned, len(pinned), max_candidates=len(pinned))
            remaining = [item for item in ranked if item["chunk_id"] not in named_ids]
            if len(pinned) < top_k:
                remaining = rerank_documents(
                    query,
                    remaining,
                    top_k - len(pinned),
                    max_candidates=RERANK_MAX_CANDIDATES,
                )
            else:
                remaining = []
            return pinned + remaining

        # An explicitly attached document must remain readable even when it
        # has no dense vectors and the prompt is too generic for FTS5 (for
        # example, "What is in this file?"). In that case, provide its first
        # source chunks so the model can summarize the document instead of
        # claiming no attachment was found.
        if not ranked and (document_id or document_ids):
            cursor.execute(
                """
                SELECT c.id AS chunk_id, c.document_id, c.workspace_id, c.content,
                       c.page_number, c.chunk_index, d.file_name AS document_name
                FROM documents d
                JOIN document_chunks c ON c.document_id = d.id
                WHERE d.workspace_id = ?{document_filter}
                ORDER BY d.created_at DESC, c.chunk_index ASC
                LIMIT ?
                """.format(document_filter=document_filter.replace("c.document_id", "d.id")),
                (workspace_id, *document_params, top_k),
            )
            attached_document_chunks = [dict(row) for row in cursor.fetchall()]
            if attached_document_chunks:
                return attached_document_chunks

        return rerank_documents(
            query,
            ranked,
            top_k,
            max_candidates=RERANK_MAX_CANDIDATES,
        )
    finally:
        conn.close()
