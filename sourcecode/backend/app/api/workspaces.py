import os
import logging
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import List, Dict, Any
from app.database import get_db_connection
from app.services.document_service import process_and_index_document
from app.config import UPLOAD_DIR

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Workspaces & Documents"])

# --- Workspace Endpoints ---

@router.get("/workspaces")
def list_workspaces():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM workspaces ORDER BY created_at ASC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"workspaces": rows}

@router.post("/workspaces")
def create_workspace(name: str, description: str = ""):
    """Tạo workspace mới"""
    import uuid
    workspace_id = str(uuid.uuid4())
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO workspaces (id, name, description) VALUES (?, ?, ?)",
        (workspace_id, name, description)
    )
    conn.commit()
    conn.close()
    return {"workspace_id": workspace_id, "name": name, "description": description}

@router.delete("/workspaces/{workspace_id}")
def delete_workspace(workspace_id: str):
    """Xóa workspace (CASCADE xóa toàn bộ documents và chunks liên quan)"""
    if workspace_id == "default":
        raise HTTPException(status_code=400, detail="Không thể xóa workspace mặc định")
    conn = get_db_connection()
    cursor = conn.cursor()
    # Lấy danh sách file path cần xóa
    cursor.execute("SELECT file_path FROM documents WHERE workspace_id = ?", (workspace_id,))
    file_paths = [row["file_path"] for row in cursor.fetchall()]
    # Xóa FTS index
    cursor.execute("DELETE FROM chunks_fts WHERE workspace_id = ?", (workspace_id,))
    # Xóa workspace (CASCADE xóa documents, chunks, embeddings)
    cursor.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
    conn.commit()
    conn.close()
    # Xóa file vật lý
    for fp in file_paths:
        try:
            if fp and Path(fp).exists():
                os.remove(fp)
        except Exception as e:
            logger.warning(f"Không thể xóa file {fp}: {e}")
    return {"message": f"Đã xóa workspace '{workspace_id}' và toàn bộ tài liệu liên quan"}

# --- Document Endpoints ---

@router.get("/workspaces/{workspace_id}/documents")
def list_documents(workspace_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM documents WHERE workspace_id = ? ORDER BY created_at DESC", (workspace_id,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"documents": rows}

@router.post("/workspaces/{workspace_id}/documents/upload")
async def upload_document(workspace_id: str, file: UploadFile = File(...)):
    """Upload và lập chỉ mục tài liệu vào workspace"""
    # Validate file type
    ALLOWED_EXTENSIONS = {"pdf", "docx", "pptx", "ppt", "txt", "md", "csv", "json"}
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Định dạng file không hỗ trợ: .{ext}. Chỉ chấp nhận: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File tải lên không có dữ liệu")

    result = process_and_index_document(workspace_id, file.filename, content)
    return {"message": "Tài liệu đã được tải lên và lập chỉ mục thành công", "document": result}

@router.delete("/documents/{document_id}")
def delete_document(document_id: str):
    """Xóa tài liệu khỏi CSDL và xóa file vật lý"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Lấy file path trước khi xóa
    cursor.execute("SELECT file_path FROM documents WHERE id = ?", (document_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")

    file_path = row["file_path"]

    # Xóa khỏi FTS
    cursor.execute("DELETE FROM chunks_fts WHERE document_id = ?", (document_id,))
    # Xóa embeddings
    cursor.execute("DELETE FROM chunk_embeddings WHERE document_id = ?", (document_id,))
    # Xóa chunks
    cursor.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
    # Xóa document record
    cursor.execute("DELETE FROM documents WHERE id = ?", (document_id,))

    conn.commit()
    conn.close()

    # Xóa file vật lý nếu tồn tại
    try:
        if file_path and Path(file_path).exists():
            os.remove(file_path)
            logger.info(f"Đã xóa file vật lý: {file_path}")
    except Exception as e:
        logger.warning(f"Không thể xóa file vật lý {file_path}: {e}")

    return {"message": "Đã xóa tài liệu thành công"}
