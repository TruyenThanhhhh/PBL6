from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import List, Dict, Any
from app.database import get_db_connection
from app.services.document_service import process_and_index_document

router = APIRouter(prefix="/api/v1", tags=["Workspaces & Documents"])

@router.get("/workspaces")
def list_workspaces():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM workspaces ORDER BY created_at ASC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"workspaces": rows}

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
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File tải lên không có dữ liệu")
        
    result = process_and_index_document(workspace_id, file.filename, content)
    return {"message": "Tài liệu đã được tải lên và lập chỉ mục thành công", "document": result}

@router.delete("/documents/{document_id}")
def delete_document(document_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Xóa khỏi FTS
    cursor.execute("DELETE FROM chunks_fts WHERE document_id = ?", (document_id,))
    # Xóa chunks
    cursor.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
    # Xóa document
    cursor.execute("DELETE FROM documents WHERE id = ?", (document_id,))
    
    conn.commit()
    conn.close()
    return {"message": "Đã xóa tài liệu thành công"}
