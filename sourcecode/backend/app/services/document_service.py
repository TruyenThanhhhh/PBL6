import uuid
import re
import logging
import threading
from pathlib import Path
from typing import List, Dict, Any

from app.config import CHUNK_SIZE, CHUNK_OVERLAP, UPLOAD_DIR, EMBEDDING_MODEL
from app.database import get_db_connection
from app.services.embedding_service import embed_texts, pack_vector

logger = logging.getLogger(__name__)
SUPPORTED_TYPES = {"pdf", "docx", "pptx", "txt", "md", "py", "json", "csv", "xlsx"}

def extract_text_from_file(file_path: Path, file_type: str) -> List[Dict[str, Any]]:
    """
    Trích xuất text sạch từ file (PDF, DOCX, PPTX, TXT, MD) và giữ metadata số trang/slide.
    """
    results = []
    
    if file_type == "pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(file_path))
            for i, page in enumerate(reader.pages):
                extracted = page.extract_text() or ""
                if extracted.strip():
                    results.append({"page": i + 1, "text": extracted})
        except Exception as e:
            logger.exception("PDF extraction failed")
            raise ValueError("Không thể trích xuất nội dung PDF") from e
            
    elif file_type == "docx":
        try:
            import docx
            doc = docx.Document(str(file_path))
            full_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
            if full_text.strip():
                results.append({"page": 1, "text": full_text})
        except Exception as e:
            logger.exception("DOCX extraction failed")
            raise ValueError("Không thể trích xuất nội dung DOCX") from e

    elif file_type == "pptx":
        try:
            from pptx import Presentation
            prs = Presentation(str(file_path))
            for i, slide in enumerate(prs.slides):
                slide_texts = []
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        slide_texts.append(shape.text.strip())
                if slide_texts:
                    results.append({"page": i + 1, "text": "\n".join(slide_texts)})
        except Exception as e:
            logger.exception("PPTX extraction failed")
            raise ValueError("Không thể trích xuất nội dung PPTX") from e
            
    elif file_type in ["txt", "md", "py", "json", "csv"]:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                if content.strip():
                    results.append({"page": 1, "text": content})
        except Exception as e:
            logger.exception("Text extraction failed")
            raise ValueError("Không thể đọc tệp văn bản") from e

    elif file_type == "xlsx":
        try:
            import openpyxl
            wb = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
            for sheet in wb.worksheets:
                lines = []
                for row in sheet.iter_rows(values_only=True):
                    cells = [str(v).strip() for v in row if v is not None and str(v).strip()]
                    if cells:
                        lines.append(" | ".join(cells))
                if lines:
                    results.append({"page": sheet.title, "text": "\n".join(lines)})
            wb.close()
        except Exception as e:
            logger.exception("Excel extraction failed")
            raise ValueError("Không thể trích xuất nội dung Excel") from e

    return results

def recursive_chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """
    Chia nhỏ văn bản thông minh bám theo dấu câu và ngắt dòng logic
    """
    text = re.sub(r'\r\n', '\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    
    if len(text) <= chunk_size:
        return [text.strip()] if text.strip() else []
        
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end >= len(text):
            chunk = text[start:].strip()
            if chunk:
                chunks.append(chunk)
            break
            
        cut = -1
        for delim in ["\n\n", "\n", ". ", "; ", ", ", " "]:
            pos = text.rfind(delim, start + chunk_size // 2, end)
            if pos != -1:
                cut = pos + len(delim)
                break
                
        if cut == -1:
            cut = end
            
        chunk = text[start:cut].strip()
        if chunk:
            chunks.append(chunk)
        start = cut - overlap if cut - overlap > start else cut
        
    return chunks

def _save_upload(workspace_id: str, file_name: str, file_bytes: bytes):
    """Lưu file và tạo bản ghi documents (status=processing). Trả về thông tin cơ bản."""
    doc_id = str(uuid.uuid4())
    safe_name = Path(file_name or "upload.txt").name
    ext = Path(safe_name).suffix.lower().lstrip(".") or "txt"
    if ext not in SUPPORTED_TYPES:
        raise ValueError(f"Định dạng không hỗ trợ: {ext}")
    saved_path = UPLOAD_DIR / f"{doc_id}_{safe_name}"

    with open(saved_path, "wb") as f:
        f.write(file_bytes)

    conn = get_db_connection()
    try:
        conn.execute(
            """
    INSERT INTO documents (id, workspace_id, file_name, file_type, file_size, file_path, total_chunks, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
            (doc_id, workspace_id, safe_name, ext, len(file_bytes), str(saved_path), 0, "processing"),
        )
        conn.commit()
    finally:
        conn.close()

    return doc_id, safe_name, ext, saved_path


def _index_saved_document(doc_id: str, workspace_id: str, safe_name: str, ext: str, saved_path: Path) -> Dict[str, Any]:
    """Trích xuất text, chunking, sinh vector BGE-M3 và lưu chunks/FTS/embeddings."""
    try:
        pages = extract_text_from_file(saved_path, ext)
        if not pages and ext in ["txt", "md", "csv", "json"]:
            text = saved_path.read_bytes().decode("utf-8", errors="ignore")
            if text.strip():
                pages = [{"page": 1, "text": text}]

        if not pages:
            raise ValueError("Không trích xuất được văn bản từ tài liệu")

        # Chunking
        all_chunks = []
        chunk_index = 0
        for p in pages:
            for c in recursive_chunk_text(p["text"]):
                all_chunks.append({
                    "id": str(uuid.uuid4()),
                    "document_id": doc_id,
                    "workspace_id": workspace_id,
                    "chunk_index": chunk_index,
                    "page_number": p["page"],
                    "content": c,
                })
                chunk_index += 1

        vectors = embed_texts([chunk["content"] for chunk in all_chunks])

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            for c in all_chunks:
                cursor.execute(
                    """
        INSERT INTO document_chunks (id, document_id, workspace_id, chunk_index, page_number, content)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
                    (c["id"], c["document_id"], c["workspace_id"], c["chunk_index"], c["page_number"], c["content"]),
                )
                clean_fts_content = re.sub(r'["\']', '', c["content"])
                cursor.execute(
                    """
        INSERT INTO chunks_fts (chunk_id, document_id, workspace_id, content)
        VALUES (?, ?, ?, ?)
        """,
                    (c["id"], c["document_id"], c["workspace_id"], clean_fts_content),
                )

            if vectors:
                for chunk, vector in zip(all_chunks, vectors):
                    cursor.execute(
                        "INSERT INTO chunk_embeddings (chunk_id, model, dimensions, vector) VALUES (?, ?, ?, ?)",
                        (chunk["id"], EMBEDDING_MODEL, len(vector), pack_vector(vector)),
                    )

            cursor.execute(
                "UPDATE documents SET total_chunks = ?, status = ? WHERE id = ?",
                (len(all_chunks), "indexed", doc_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        return {
            "document_id": doc_id,
            "file_name": safe_name,
            "file_type": ext,
            "total_chunks": len(all_chunks),
            "dense_indexed": bool(vectors),
            "status": "indexed",
        }
    except Exception:
        saved_path.unlink(missing_ok=True)
        conn = get_db_connection()
        try:
            conn.execute("UPDATE documents SET status = ? WHERE id = ?", ("failed", doc_id))
            conn.commit()
        finally:
            conn.close()
        raise


def process_and_index_document(workspace_id: str, file_name: str, file_bytes: bytes) -> Dict[str, Any]:
    """Xử lý đồng bộ (dùng cho eval/CLI)."""
    doc_id, safe_name, ext, saved_path = _save_upload(workspace_id, file_name, file_bytes)
    return _index_saved_document(doc_id, workspace_id, safe_name, ext, saved_path)


def process_and_index_document_async(workspace_id: str, file_name: str, file_bytes: bytes) -> Dict[str, Any]:
    """Lưu file nhanh rồi lập chỉ mục ở luồng nền để HTTP trả về ngay."""
    doc_id, safe_name, ext, saved_path = _save_upload(workspace_id, file_name, file_bytes)

    def _run() -> None:
        try:
            _index_saved_document(doc_id, workspace_id, safe_name, ext, saved_path)
        except Exception:
            logger.exception("Background indexing failed for document %s", doc_id)

    threading.Thread(target=_run, name=f"index-{doc_id}", daemon=True).start()

    return {
        "document_id": doc_id,
        "file_name": safe_name,
        "file_type": ext,
        "total_chunks": 0,
        "dense_indexed": False,
        "status": "processing",
    }


def reindex_document_embeddings(document_id: str) -> Dict[str, Any]:
    """Build or refresh BGE-M3 vectors for a document that was indexed FTS-only."""
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT id, content FROM document_chunks WHERE document_id = ? ORDER BY chunk_index",
            (document_id,),
        ).fetchall()
        if not rows:
            exists = conn.execute("SELECT 1 FROM documents WHERE id = ?", (document_id,)).fetchone()
            if not exists:
                raise ValueError("Không tìm thấy tài liệu")
        vectors = embed_texts([row["content"] for row in rows])
        if vectors is None:
            raise RuntimeError("BGE-M3 chưa sẵn sàng; hãy kiểm tra fastembed và kết nối tải model")
        conn.execute("DELETE FROM chunk_embeddings WHERE chunk_id IN "
                     "(SELECT id FROM document_chunks WHERE document_id = ?)", (document_id,))
        for row, vector in zip(rows, vectors):
            conn.execute(
                "INSERT INTO chunk_embeddings (chunk_id, model, dimensions, vector) VALUES (?, ?, ?, ?)",
                (row["id"], EMBEDDING_MODEL, len(vector), pack_vector(vector)),
            )
        conn.commit()
        return {"document_id": document_id, "dense_indexed": len(vectors), "total_chunks": len(rows)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
