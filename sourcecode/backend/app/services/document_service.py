import hashlib
import uuid
import re
import logging
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.config import CHUNK_SIZE, CHUNK_OVERLAP, UPLOAD_DIR, EMBEDDING_MODEL
from app.database import get_db_connection
from app.services.embedding_service import embed_texts, pack_vector

logger = logging.getLogger(__name__)
SUPPORTED_TYPES = {"pdf", "docx", "pptx", "txt", "md", "py", "json", "csv", "xlsx", "xls"}


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

    elif file_type in ["xlsx", "xls"]:
        try:
            if file_type == "xlsx":
                import openpyxl
                wb = openpyxl.load_workbook(str(file_path), data_only=True)
                for sheet_idx, sheet_name in enumerate(wb.sheetnames):
                    ws = wb[sheet_name]
                    lines = []
                    for row in ws.iter_rows(values_only=True):
                        cells = [str(c).strip() for c in row if c is not None and str(c).strip() != ""]
                        if cells:
                            lines.append(" | ".join(cells))
                    if lines:
                        sheet_text = f"Sheet: {sheet_name}\n" + "\n".join(lines)
                        results.append({"page": sheet_idx + 1, "text": sheet_text})
            else:
                import pandas as pd
                excel_file = pd.ExcelFile(str(file_path))
                for sheet_idx, sheet_name in enumerate(excel_file.sheet_names):
                    df = pd.read_excel(excel_file, sheet_name=sheet_name)
                    df_clean = df.dropna(how="all")
                    if not df_clean.empty:
                        text = df_clean.to_string(index=False)
                        results.append({"page": sheet_idx + 1, "text": f"Sheet: {sheet_name}\n{text}"})
        except Exception as e:
            logger.exception("Excel extraction failed")
            raise ValueError(f"Không thể trích xuất nội dung tệp Excel: {e}") from e

    elif file_type in ["txt", "md", "py", "json", "csv"]:
        try:
            try:
                with open(file_path, "r", encoding="utf-8-sig") as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            if content.strip():
                results.append({"page": 1, "text": content})
        except Exception as e:
            logger.exception("Text extraction failed")
            raise ValueError("Không thể đọc tệp văn bản") from e

    return results


def recursive_chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """
    Phân đoạn ngữ cảnh tự nhiên (Semantic & Markdown-aware Chunking):
    1. Bảo toàn nguyên vẹn Bảng biểu (| ... |) và Khối Code (``` ... ```), không xẻ đôi giữa chừng.
    2. Cắt theo ranh giới đoạn văn tự nhiên và tiêu đề phân cấp (#, ##, Bài, Chương).
    3. Đính kèm siêu dữ liệu cấu trúc (Structural Breadcrumb) [Chương/Bài] vào đầu các chunk tiếp nối
       để tăng cường độ chính xác tìm kiếm của BM25 và Vector BGE-M3.
    """
    text = re.sub(r'\r\n', '\n', text)
    if not text.strip():
        return []
    if len(text) <= chunk_size:
        return [text.strip()]

    lines = text.split('\n')
    blocks: List[Tuple[str, str]] = []
    current_block: List[str] = []
    current_type: Optional[str] = None

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 1. Khối mã lệnh Fenced Code Block
        if stripped.startswith('```'):
            if current_block:
                blocks.append((current_type or 'paragraph', '\n'.join(current_block)))
                current_block = []
                current_type = None
            code_lines = [line]
            i += 1
            while i < len(lines):
                code_lines.append(lines[i])
                if lines[i].strip().startswith('```'):
                    break
                i += 1
            blocks.append(('code', '\n'.join(code_lines)))
            i += 1
            continue

        # 2. Khối bảng biểu Markdown Table
        if stripped.startswith('|') and stripped.endswith('|'):
            if current_type != 'table' and current_block:
                blocks.append((current_type or 'paragraph', '\n'.join(current_block)))
                current_block = []
            current_type = 'table'
            current_block.append(line)
            i += 1
            continue
        elif current_type == 'table':
            blocks.append(('table', '\n'.join(current_block)))
            current_block = []
            current_type = None

        # 3. Tiêu đề phân cấp (Header & Section titles)
        is_heading = bool(
            re.match(r'^#{1,6}\s+', stripped) or
            re.match(r'^(?:chương|bài|phần|mục|lab|chapter|section)\s+\d+[:.]?', stripped, re.IGNORECASE)
        )
        if is_heading:
            if current_block:
                blocks.append((current_type or 'paragraph', '\n'.join(current_block)))
                current_block = []
            blocks.append(('heading', stripped))
            current_type = None
            i += 1
            continue

        # 4. Ngắt dòng đoạn văn (\n\n)
        if not stripped:
            if current_block:
                blocks.append((current_type or 'paragraph', '\n'.join(current_block)))
                current_block = []
                current_type = None
            i += 1
            continue

        current_type = current_type or 'paragraph'
        current_block.append(line)
        i += 1

    if current_block:
        blocks.append((current_type or 'paragraph', '\n'.join(current_block)))

    chunks: List[str] = []
    current_chunk: List[str] = []
    current_len = 0
    active_heading = ''

    for b_type, b_text in blocks:
        if b_type == 'heading':
            active_heading = re.sub(r'^#{1,6}\s*', '', b_text).strip()

        b_len = len(b_text)

        # Xử lý khối đơn lẻ có độ dài vượt quá chunk_size (ví dụ đoạn văn quá dài hoặc bảng khổng lồ)
        if b_len > chunk_size:
            if current_chunk:
                c_content = '\n\n'.join(current_chunk).strip()
                if active_heading and not c_content.startswith(f'[{active_heading}]') and not c_content.startswith(f'# {active_heading}'):
                    c_content = f'[{active_heading}]\n{c_content}'
                if c_content:
                    chunks.append(c_content)
                current_chunk = []
                current_len = 0

            sub_start = 0
            while sub_start < b_len:
                sub_end = sub_start + chunk_size
                if sub_end >= b_len:
                    piece = b_text[sub_start:].strip()
                    if piece:
                        chunks.append(piece)
                    break
                cut = b_text.rfind('\n', sub_start + chunk_size // 2, sub_end)
                if cut == -1:
                    cut = b_text.rfind('. ', sub_start + chunk_size // 2, sub_end)
                if cut == -1:
                    cut = sub_end
                else:
                    cut += 1
                piece = b_text[sub_start:cut].strip()
                if piece:
                    chunks.append(piece)
                sub_start = cut - overlap if cut - overlap > sub_start else cut
            continue

        if current_len + b_len + 2 > chunk_size and current_chunk:
            c_content = '\n\n'.join(current_chunk).strip()
            if active_heading and not c_content.startswith(f'[{active_heading}]') and not c_content.startswith(f'# {active_heading}'):
                c_content = f'[{active_heading}]\n{c_content}'
            if c_content:
                chunks.append(c_content)

            # Giữ block cuối cho độ gối đầu overlap nếu hợp lý
            last_block = current_chunk[-1]
            if overlap > 0 and len(last_block) <= overlap:
                current_chunk = [last_block, b_text]
                current_len = len(last_block) + b_len + 2
            else:
                current_chunk = [b_text]
                current_len = b_len
        else:
            current_chunk.append(b_text)
            current_len += b_len + 2

    if current_chunk:
        c_content = '\n\n'.join(current_chunk).strip()
        if active_heading and not c_content.startswith(f'[{active_heading}]') and not c_content.startswith(f'# {active_heading}'):
            c_content = f'[{active_heading}]\n{c_content}'
        if c_content:
            chunks.append(c_content)

    return chunks


def process_and_index_document(
    workspace_id: str,
    file_name: str,
    file_bytes: bytes,
    notebook_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Xử lý file tải lên: lưu trữ, trích xuất text, chunking, sinh vector BGE-M3
    và lưu đồng bộ vào SQLite (documents, document_chunks, chunks_fts, chunk_embeddings).
    """
    # Chuẩn hóa notebook_id để tránh vi phạm FOREIGN KEY constraint
    notebook_id = notebook_id.strip() if notebook_id and notebook_id.strip() else None
    if notebook_id:
        conn_chk = get_db_connection()
        nb_exists = conn_chk.execute("SELECT 1 FROM notebooks WHERE id = ?", (notebook_id,)).fetchone()
        conn_chk.close()
        if not nb_exists:
            notebook_id = None
    doc_id = str(uuid.uuid4())
    safe_name = Path(file_name or "upload.txt").name
    ext = Path(safe_name).suffix.lower().lstrip(".") or "txt"
    if ext not in SUPPORTED_TYPES:
        raise ValueError(f"Định dạng không hỗ trợ: {ext}")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    saved_path = UPLOAD_DIR / f"{doc_id}_{safe_name}"

    with open(saved_path, "wb") as f:
        f.write(file_bytes)

    file_size = len(file_bytes)
    content_hash = hashlib.sha256(file_bytes).hexdigest()

    # Khử trùng lặp: Nếu tài liệu đã được tải lên trong không gian này, tái sử dụng để tránh nhân bản dữ liệu
    conn_dedup = get_db_connection()
    try:
        cur_dedup = conn_dedup.cursor()
        existing = cur_dedup.execute(
            "SELECT id, file_name, file_type, file_size, total_pages, total_chunks, status "
            "FROM documents WHERE workspace_id = ? AND content_hash = ?",
            (workspace_id, content_hash),
        ).fetchone()
        if existing:
            saved_path.unlink(missing_ok=True)
            return dict(existing)
    finally:
        conn_dedup.close()

    # 1. Trích xuất text sạch
    try:
        pages = extract_text_from_file(saved_path, ext)
    except Exception:
        saved_path.unlink(missing_ok=True)
        raise
    if not pages:
        if ext in ["txt", "md", "csv", "json", "py"]:
            text = file_bytes.decode("utf-8", errors="ignore")
            if text.strip():
                pages = [{"page": 1, "text": text}]

    if not pages:
        saved_path.unlink(missing_ok=True)
        raise ValueError("Không trích xuất được văn bản từ tài liệu")

    total_pages = max(1, len(pages))

    # 2. Chunking
    all_chunks = []
    chunk_index = 0
    for p in pages:
        page_chunks = recursive_chunk_text(p["text"])
        for c in page_chunks:
            chunk_id = str(uuid.uuid4())
            token_count = max(1, len(c.split()))
            all_chunks.append({
                "id": chunk_id,
                "document_id": doc_id,
                "workspace_id": workspace_id,
                "chunk_index": chunk_index,
                "page_number": p["page"],
                "token_count": token_count,
                "content": c,
            })
            chunk_index += 1

    vectors = embed_texts([chunk["content"] for chunk in all_chunks])

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO documents (
                id, workspace_id, notebook_id, file_name, file_type,
                file_size, file_path, content_hash, total_pages, total_chunks, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id, workspace_id, notebook_id, safe_name, ext,
                file_size, str(saved_path), content_hash, total_pages, len(all_chunks), "indexed",
            ),
        )

        for c in all_chunks:
            cursor.execute(
                """
                INSERT INTO document_chunks (
                    id, document_id, workspace_id, chunk_index, page_number, token_count, content
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    c["id"], c["document_id"], c["workspace_id"],
                    c["chunk_index"], c["page_number"], c["token_count"], c["content"],
                ),
            )

            # Đánh chỉ mục Full-Text Search (FTS5)
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
            "INSERT INTO user_activities (id, workspace_id, activity_type, message) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), workspace_id, "document", f"Đã tải lên và lập chỉ mục tài liệu '{safe_name}'"),
        )
        cursor.execute(
            "UPDATE workspaces SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (workspace_id,),
        )

        conn.commit()
    except Exception:
        saved_path.unlink(missing_ok=True)
        conn = get_db_connection()
        try:
            conn.execute("UPDATE documents SET status = ? WHERE id = ?", ("failed", doc_id))
            conn.commit()
        finally:
            conn.close()
        raise
    conn.close()

    return {
        "document_id": doc_id,
        "file_name": safe_name,
        "file_type": ext,
        "total_pages": total_pages,
        "total_chunks": len(all_chunks),
        "dense_indexed": bool(vectors),
        "status": "indexed",
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
        conn.execute(
            "DELETE FROM chunk_embeddings WHERE chunk_id IN "
            "(SELECT id FROM document_chunks WHERE document_id = ?)",
            (document_id,),
        )
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
