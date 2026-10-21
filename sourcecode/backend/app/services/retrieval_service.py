import re
from typing import List, Dict, Any
from app.database import get_db_connection
from app.config import TOP_K_RETRIEVAL
import numpy as np
import sqlite3
import json
from typing import List, Dict, Any
from app.services.embedding_service import embedding_service

class RetrievalService:
    def __init__(self, rrf_k: int = 60):
        self.rrf_k = rrf_k

    def hybrid_search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        # 1. Dense Search (Cosine Similarity)
        query_embedding = embedding_service.generate_embeddings(query)[0]
        dense_results = self._dense_search(query_embedding, top_k=20)
        
        # 2. Sparse Search (BM25 / Full-Text Search)
        sparse_results = self._sparse_search(query, top_k=20)
        
        # 3. Kết hợp kết quả bằng thuật toán Reciprocal Rank Fusion (RRF)
        fused_results = self._apply_rrf(dense_results, sparse_results, top_k=top_k)
        return fused_results

    def _dense_search(self, query_emb: List[float], top_k: int) -> List[Dict]:
        conn = sqlite3.connect("data/knowledge.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, content, embedding FROM document_chunks")
        rows = cursor.fetchall()
        conn.close()
        
        scores = []
        for row_id, content, emb_str in rows:
            emb = json.loads(emb_str)
            # Cosine similarity
            sim = np.dot(query_emb, emb) / (np.linalg.norm(query_emb) * np.linalg.norm(emb) + 1e-8)
            scores.append({"id": row_id, "content": content, "score": float(sim)})
            
        scores.sort(key=lambda x: x["score"], reverse=True)
        return scores[:top_k]

    def _sparse_search(self, query: str, top_k: int) -> List[Dict]:
        conn = sqlite3.connect("data/knowledge.db")
        cursor = conn.cursor()
        # Tìm kiếm từ khóa đơn giản (sparse mimic)
        words = query.split()
        match_pattern = "%" + "%".join(words) + "%"
        cursor.execute("SELECT id, content FROM document_chunks WHERE content LIKE ? LIMIT ?", (match_pattern, top_k))
        rows = cursor.fetchall()
        conn.close()
        
        return [{"id": r[0], "content": r[1], "score": 1.0 / (idx + 1)} for idx, r in enumerate(rows)]

    def _apply_rrf(self, dense_list: List[Dict], sparse_list: List[Dict], top_k: int) -> List[Dict]:
        rrf_scores = {}
        content_map = {}

        def add_ranks(doc_list):
            for rank, doc in enumerate(doc_list):
                doc_id = doc["id"]
                content_map[doc_id] = doc["content"]
                if doc_id not in rrf_scores:
                    rrf_scores[doc_id] = 0.0
                # Công thức RRF: 1 / (k + rank)
                rrf_scores[doc_id] += 1.0 / (self.rrf_k + (rank + 1))

        add_ranks(dense_list)
        add_ranks(sparse_list)

        # Sắp xếp theo điểm RRF giảm dần
        sorted_docs = sorted(rrf_scores.items(), key=lambda item: item[1], reverse=True)
        
        return [{"id": doc_id, "content": content_map[doc_id], "rrf_score": score} for doc_id, score in sorted_docs[:top_k]]

retrieval_service = RetrievalService()

def search_relevant_chunks(workspace_id: str, query: str, top_k: int = TOP_K_RETRIEVAL) -> List[Dict[str, Any]]:
    """
    Truy xuất các đoạn văn bản liên quan nhất sử dụng Full-Text Search FTS5 kết hợp xếp hạng BM25
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Làm sạch câu truy vấn cho FTS5 (loại bỏ ký tự đặc biệt gây lỗi syntax)
    clean_query = re.sub(r'[^\w\s]', ' ', query)
    tokens = [t for t in clean_query.split() if len(t) > 1]
    
    results = []
    
    if tokens:
        # Tạo chuỗi MATCH truy vấn từ khóa OR để tối đa hóa khả năng bắt khớp (Recall)
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
                    "score": float(row["rank_score"])
                })
        except Exception as e:
            print(f"Lỗi FTS5 Match, chuyển sang fallback: {e}")
            
    # 2. Fallback tìm kiếm LIKE nếu FTS không tìm thấy hoặc câu hỏi quá ngắn
    if not results:
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
                "score": 1.0
            })
            
    conn.close()
    return results
