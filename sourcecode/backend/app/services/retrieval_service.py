import re
import json
import logging
import numpy as np
from typing import List, Dict, Any

from app.database import get_db_connection
from app.config import TOP_K_RETRIEVAL
from app.services.embedding_service import embedding_service
from app.services.reranker_service import reranker_service

logger = logging.getLogger(__name__)

class RetrievalService:
    def __init__(self, rrf_k: int = 60):
        self.rrf_k = rrf_k

    def hybrid_search(self, workspace_id: str, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        """
        Thực hiện Hybrid Search kết hợp Dense Vector Search (BGE-M3) và Sparse Search (FTS5 BM25)
        thông qua thuật toán Reciprocal Rank Fusion (RRF).
        """
        # 1. Dense Search (Cosine Similarity từ BGE-M3 vectors)
        dense_results = self._dense_search(workspace_id, query, top_k=top_k)

        # 2. Sparse Search (BM25 qua FTS5)
        sparse_results = self._sparse_search(workspace_id, query, top_k=top_k)

        # 3. Kết hợp bằng Reciprocal Rank Fusion (RRF)
        fused_results = self._apply_rrf(dense_results, sparse_results, top_k=top_k)
        return fused_results

    def _dense_search(self, workspace_id: str, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        """
        Dense vector search: tính cosine similarity giữa query embedding và chunk embeddings.
        Chỉ load chunk_ids cần thiết thay vì toàn bộ DB để tránh OOM.
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        # Lấy số lượng embeddings để ước tính bộ nhớ
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM chunk_embeddings WHERE workspace_id = ?",
            (workspace_id,)
        )
        count = cursor.fetchone()["cnt"]

        if count == 0:
            conn.close()
            return []

        # Sinh vector cho query trước
        query_emb = np.array(embedding_service.generate_embeddings(query)[0], dtype=np.float32)
        norm_q = np.linalg.norm(query_emb) + 1e-8

        # Xử lý theo batch để tránh OOM khi DB lớn
        BATCH_SIZE = 500
        scores = []

        for offset in range(0, count, BATCH_SIZE):
            cursor.execute("""
                SELECT e.chunk_id, e.embedding_json, c.document_id, c.content, c.page_number, c.chunk_index, d.file_name
                FROM chunk_embeddings e
                JOIN document_chunks c ON e.chunk_id = c.id
                JOIN documents d ON c.document_id = d.id
                WHERE e.workspace_id = ?
                LIMIT ? OFFSET ?
            """, (workspace_id, BATCH_SIZE, offset))

            for r in cursor.fetchall():
                emb = np.array(json.loads(r["embedding_json"]), dtype=np.float32)
                sim = float(np.dot(query_emb, emb) / (norm_q * (np.linalg.norm(emb) + 1e-8)))
                scores.append({
                    "chunk_id": r["chunk_id"],
                    "document_id": r["document_id"],
                    "document_name": r["file_name"],
                    "page_number": r["page_number"],
                    "chunk_index": r["chunk_index"],
                    "content": r["content"],
                    "dense_score": sim
                })

        conn.close()
        scores.sort(key=lambda x: x["dense_score"], reverse=True)
        logger.debug(f"Dense search: {len(scores)} chunks scored, returning top {top_k}")
        return scores[:top_k]

    def _sparse_search(self, workspace_id: str, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()

        clean_query = re.sub(r'[^\w\s]', ' ', query)
        tokens = [t for t in clean_query.split() if len(t) > 1]
        results = []

        if tokens:
            fts_match_query = " OR ".join(tokens)
            try:
                cursor.execute("""
                SELECT f.chunk_id, f.content, bm25(chunks_fts) as rank_score,
                       c.page_number, c.chunk_index, d.file_name, d.id as document_id
                FROM chunks_fts f
                JOIN document_chunks c ON f.chunk_id = c.id
                JOIN documents d ON c.document_id = d.id
                WHERE chunks_fts MATCH ? AND f.workspace_id = ?
                ORDER BY rank_score ASC
                LIMIT ?
                """, (fts_match_query, workspace_id, top_k))
                for row in cursor.fetchall():
                    results.append({
                        "chunk_id": row["chunk_id"],
                        "document_id": row["document_id"],
                        "document_name": row["file_name"],
                        "page_number": row["page_number"],
                        "chunk_index": row["chunk_index"],
                        "content": row["content"],
                        "sparse_score": float(row["rank_score"])
                    })
            except Exception as e:
                logger.error(f"Lỗi FTS5 BM25 match: {e}")

        # Fallback LIKE nếu không có kết quả FTS
        if not results:
            logger.info("FTS5 không có kết quả, dùng fallback ORDER BY created_at")
            cursor.execute("""
            SELECT c.id as chunk_id, c.content, c.page_number, c.chunk_index,
                   d.file_name, d.id as document_id
            FROM document_chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE c.workspace_id = ?
            ORDER BY c.created_at DESC
            LIMIT ?
            """, (workspace_id, top_k))
            for row in cursor.fetchall():
                results.append({
                    "chunk_id": row["chunk_id"],
                    "document_id": row["document_id"],
                    "document_name": row["file_name"],
                    "page_number": row["page_number"],
                    "chunk_index": row["chunk_index"],
                    "content": row["content"],
                    "sparse_score": 1.0
                })

        conn.close()
        logger.debug(f"Sparse search: {len(results)} chunks returned")
        return results

    def _apply_rrf(self, dense_list: List[Dict], sparse_list: List[Dict], top_k: int) -> List[Dict]:
        """
        Reciprocal Rank Fusion: RRF(d) = sum(1 / (k + rank_i(d)))
        """
        rrf_scores = {}
        doc_map = {}

        for rank, doc in enumerate(dense_list):
            cid = doc["chunk_id"]
            doc_map[cid] = doc
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (self.rrf_k + rank + 1))

        for rank, doc in enumerate(sparse_list):
            cid = doc["chunk_id"]
            doc_map[cid] = doc
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (self.rrf_k + rank + 1))

        sorted_ids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)
        results = []
        for cid in sorted_ids[:top_k]:
            item = dict(doc_map[cid])
            item["rrf_score"] = rrf_scores[cid]
            results.append(item)

        logger.debug(f"RRF fusion: {len(results)} chunks after fusion")
        return results

retrieval_service = RetrievalService()

def search_relevant_chunks(workspace_id: str, query: str, top_k: int = TOP_K_RETRIEVAL) -> List[Dict[str, Any]]:
    """
    Hàm truy xuất chính:
    1. Hybrid Search (Dense BGE-M3 + Sparse FTS5 BM25 + RRF) lấy Top-20 candidates
    2. Cross-Encoder Reranker (bge-reranker-v2-m3) chấm điểm và chọn Top-K chất lượng nhất
    """
    candidates = retrieval_service.hybrid_search(workspace_id=workspace_id, query=query, top_k=20)
    if not candidates:
        logger.info(f"Không tìm thấy chunk nào cho workspace='{workspace_id}', query='{query[:50]}...'")
        return []

    # Tiến hành Re-ranking qua Cross-Encoder
    reranked = reranker_service.rerank(query=query, documents=candidates, top_k=top_k)
    logger.info(f"Retrieval hoàn tất: {len(reranked)} chunks sau rerank")
    return reranked
