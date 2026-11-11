"""Workspace-scoped hybrid retrieval: SQLite FTS5 plus optional BGE-M3 (NumPy SIMD accelerated), RRF, and Section Extraction.

Các chế độ truy xuất:
1. Section Extraction (search_section_chunks): Dành cho câu hỏi về Bài/Chương/Lab cụ thể (ví dụ: "bài 1 làm về gì", "cách làm bài 1", "các bước tiếp theo"), lấy toàn bộ các chunk liên tục thuộc phần đó để không bị cắt xén.
2. Spanning Retrieval (search_spanning_chunks): Dành cho câu hỏi tóm tắt toàn bộ tài liệu (ví dụ: "tóm tắt các bài cần làm", "tài liệu gồm những gì"), lấy chunk phân phối đều từ đầu đến cuối.
3. Hybrid Retrieval (search_relevant_chunks): Dành cho câu hỏi tra cứu khái niệm hoặc chi tiết cụ thể (ví dụ: "DNS là gì", "port 80 dùng làm gì"), kết hợp BM25 + Dense BGE-M3 + Rerank.
"""
import math
import re
import logging
from typing import Any, Dict, List, Optional, Tuple

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

logger = logging.getLogger(__name__)

# Từ khóa nhận biết câu hỏi muốn TÓM TẮT TOÀN BỘ tài liệu
_GLOBAL_SUMMARY_KEYWORDS = [
    "tóm tắt", "tóm lại", "tổng hợp", "liệt kê tất cả", "liệt kê các",
    "các bài", "các chương", "các phần", "nội dung chính", "toàn bộ",
    "overview", "summarize", "summary", "list all", "all chapters",
    "all sections", "main topics", "những bài", "những chương",
    "nêu các", "kể tên", "có những gì", "gồm những gì",
]

# Regex nhận diện "bài X", "chương X", "phần X", "lab X"
_SECTION_PATTERN = re.compile(
    r"\b(bài|chương|phần|lab|exercise|chapter|section)\s*(\d+)\b",
    re.IGNORECASE | re.UNICODE,
)

# Từ khóa thể hiện ý định hỏi về các bước hoặc câu hỏi nối tiếp về bài đang làm
_FOLLOW_UP_KEYWORDS = [
    "bước tiếp", "bước iếp", "tiếp theo", "tiếp tục", "các bước",
    "từng bước", "hướng dẫn", "cách làm", "làm thế nào", "còn gì nữa",
    "chi tiết hơn", "bước mấy",
]


def is_global_summary_query(query: str) -> bool:
    """Trả về True nếu người dùng muốn tóm tắt/liệt kê toàn bộ nội dung tài liệu."""
    q = query.lower().strip()
    # Nếu có chỉ định rõ bài cụ thể (ví dụ: "tóm tắt bài 1") thì ưu tiên Section Extraction
    if _SECTION_PATTERN.search(q):
        return False
    return any(kw in q for kw in _GLOBAL_SUMMARY_KEYWORDS)


def detect_section_intent(
    query: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> Optional[Tuple[str, int]]:
    """
    Phát hiện xem người dùng đang hỏi về Bài/Chương/Lab mấy.
    Hỗ trợ phát hiện trong câu hỏi hiện tại hoặc suy luận từ ngữ cảnh hội thoại trước đó.
    """
    q = query.lower().strip()
    m = _SECTION_PATTERN.search(q)
    if m:
        return m.group(1).lower(), int(m.group(2))

    # Nếu câu hỏi hiện tại là câu nối tiếp (ví dụ: "các bước tiếp theo đâu", "bước iếp theo")
    is_follow_up = any(kw in q for kw in _FOLLOW_UP_KEYWORDS) or len(q.split()) <= 5
    if is_follow_up and history:
        for turn in reversed(history[-8:]):
            if turn.get("role") == "user":
                prev_text = turn.get("content", "").lower()
                pm = _SECTION_PATTERN.search(prev_text)
                if pm:
                    return pm.group(1).lower(), int(pm.group(2))

    return None


def search_section_chunks(
    workspace_id: str,
    sec_type: str,
    sec_num: int,
    max_chunks: int = 16,
    document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Trích xuất toàn bộ các chunk liên tục thuộc về Bài X / Chương X trong tài liệu.
    Bắt đầu từ chunk chứa tiêu đề Bài X (bỏ qua trang Mục lục) cho đến khi gặp Bài X+1
    hoặc đạt tối đa max_chunks chunk.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if document_id:
            doc_filter = " AND c.document_id = ?"
            doc_params: tuple = (document_id,)
        elif document_ids:
            placeholders = ",".join("?" for _ in document_ids)
            doc_filter = f" AND c.document_id IN ({placeholders})"
            doc_params = tuple(document_ids)
        else:
            doc_filter = ""
            doc_params = ()

        cursor.execute(
            f"""
            SELECT c.id AS chunk_id, c.document_id, c.workspace_id, c.content,
                   c.page_number, c.chunk_index, d.file_name AS document_name
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.workspace_id = ?{doc_filter}
            ORDER BY c.document_id, c.page_number ASC, c.chunk_index ASC
            """,
            (workspace_id, *doc_params),
        )
        all_chunks = [dict(row) for row in cursor.fetchall()]
        if not all_chunks:
            return []

        pat_start = re.compile(rf"\b{sec_type}\s*{sec_num}\b", re.IGNORECASE)
        pat_next = re.compile(rf"\b{sec_type}\s*{sec_num + 1}\b", re.IGNORECASE)

        start_idx = None
        end_idx = None

        for i, c in enumerate(all_chunks):
            # Bỏ qua 2 trang đầu nếu đó là trang Mục lục
            if c["page_number"] > 2 and pat_start.search(c["content"]):
                if start_idx is None:
                    start_idx = i
            if start_idx is not None and i > start_idx:
                if pat_next.search(c["content"]):
                    end_idx = i
                    break

        if start_idx is not None:
            if end_idx is None:
                end_idx = min(start_idx + max_chunks, len(all_chunks))
            else:
                end_idx = min(end_idx, start_idx + max_chunks)
            return all_chunks[start_idx:end_idx]

        # Nếu không tìm thấy bằng regex có số, fallback lấy theo FTS anchor
        return []
    finally:
        conn.close()


def search_spanning_chunks(
    workspace_id: str,
    query: str,
    max_chunks: int = 14,
    document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Lấy chunk phân phối ĐỀU toàn bộ tài liệu (theo thứ tự trang/chunk_index).
    Dùng cho câu hỏi "tóm tắt toàn bộ", "liệt kê các chương", v.v.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if document_id:
            doc_filter = " AND c.document_id = ?"
            doc_params: tuple = (document_id,)
        elif document_ids:
            placeholders = ",".join("?" for _ in document_ids)
            doc_filter = f" AND c.document_id IN ({placeholders})"
            doc_params = tuple(document_ids)
        else:
            doc_filter = ""
            doc_params = ()

        cursor.execute(
            f"""
            SELECT c.id AS chunk_id, c.document_id, c.workspace_id, c.content,
                   c.page_number, c.chunk_index, d.file_name AS document_name
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.workspace_id = ?{doc_filter}
            ORDER BY c.document_id, c.page_number ASC, c.chunk_index ASC
            """,
            (workspace_id, *doc_params),
        )
        all_chunks = [dict(row) for row in cursor.fetchall()]

        if not all_chunks:
            return []

        total = len(all_chunks)
        if total <= max_chunks:
            return all_chunks

        step = total / max_chunks
        selected = [all_chunks[int(i * step)] for i in range(max_chunks)]
        return selected
    finally:
        conn.close()


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
    """
    Tìm kiếm đoạn văn bản liên quan kết hợp BM25 (FTS5) + Dense Embedding (BGE-M3) + RRF + Reranker.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        clean_query = re.sub(r"[^\w\s]", " ", query, flags=re.UNICODE)
        # Giữ lại token có độ dài >= 2 hoặc là chữ số (ví dụ: '1', '2' trong bài 1, bài 2)
        tokens = [token for token in clean_query.split() if len(token) >= 2 or token.isdigit()]
        candidate_limit = max(top_k * RETRIEVAL_CANDIDATE_MULTIPLIER, top_k, 24)
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

        # Reciprocal Rank Fusion (RRF)
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
