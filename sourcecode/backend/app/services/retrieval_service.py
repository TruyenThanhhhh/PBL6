import re
from typing import List, Dict, Any
from app.database import get_db_connection
from app.config import TOP_K_RETRIEVAL

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
