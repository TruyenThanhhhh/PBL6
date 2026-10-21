import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from typing import List, Dict, Any
from app.database import get_db_connection
from app.services.document_service import process_and_index_document, reindex_document_embeddings
from app.config import UPLOAD_MAX_BYTES
from app.api.auth import get_current_user

router = APIRouter(prefix="/api/v1", tags=["Workspaces & Documents"])


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)


@router.post("/workspaces", status_code=201)
def create_workspace(req: WorkspaceCreateRequest, user: Dict[str, str] = Depends(get_current_user)):
    workspace_id = str(uuid.uuid4())
    conn = get_db_connection()
    conn.execute("INSERT INTO workspaces (id, name, description, owner_user_id) VALUES (?, ?, ?, ?)",
                 (workspace_id, req.name.strip(), req.description.strip(), user["id"]))
    conn.commit()
    conn.close()
    return {"workspace": {"id": workspace_id, "name": req.name.strip(), "description": req.description.strip()}}

@router.get("/workspaces")
def list_workspaces(user: Dict[str, str] = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM workspaces WHERE owner_user_id = ? ORDER BY created_at ASC", (user["id"],))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"workspaces": rows}

@router.get("/workspaces/{workspace_id}/documents")
def list_documents(workspace_id: str, user: Dict[str, str] = Depends(get_current_user)):
    conn = get_db_connection()
    owned = conn.execute("SELECT 1 FROM workspaces WHERE id = ? AND owner_user_id = ?",
                         (workspace_id, user["id"])).fetchone()
    if not owned:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy workspace")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM documents WHERE workspace_id = ? ORDER BY created_at DESC", (workspace_id,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"documents": rows}

@router.post("/workspaces/{workspace_id}/documents/upload")
async def upload_document(workspace_id: str, file: UploadFile = File(...),
                          user: Dict[str, str] = Depends(get_current_user)):
    conn = get_db_connection()
    exists = conn.execute("SELECT 1 FROM workspaces WHERE id = ? AND owner_user_id = ?",
                          (workspace_id, user["id"])).fetchone()
    conn.close()
    if not exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy workspace")

    content = await file.read(UPLOAD_MAX_BYTES + 1)
    if len(content) > UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"Tệp vượt quá giới hạn {UPLOAD_MAX_BYTES} bytes")
    if not content:
        raise HTTPException(status_code=400, detail="File tải lên không có dữ liệu")

    try:
        result = await run_in_threadpool(process_and_index_document, workspace_id, file.filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    return {"message": "Tài liệu đã được tải lên và lập chỉ mục thành công", "document": result}

@router.delete("/documents/{document_id}")
def delete_document(document_id: str, user: Dict[str, str] = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Xóa khỏi FTS
    cursor.execute("""SELECT d.file_path FROM documents d JOIN workspaces w ON w.id = d.workspace_id
                      WHERE d.id = ? AND w.owner_user_id = ?""", (document_id, user["id"]))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    file_path = row["file_path"]
    cursor.execute("DELETE FROM chunks_fts WHERE document_id = ?", (document_id,))
    # Xóa chunks
    cursor.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
    # Xóa document
    cursor.execute("DELETE FROM documents WHERE id = ?", (document_id,))
    
    conn.commit()
    conn.close()
    from pathlib import Path
    Path(file_path).unlink(missing_ok=True)
    return {"message": "Đã xóa tài liệu thành công"}


@router.get("/documents/{document_id}/chunks/{chunk_index}")
def get_document_chunk(document_id: str, chunk_index: int,
                       user: Dict[str, str] = Depends(get_current_user)):
    conn = get_db_connection()
    row = conn.execute("""
        SELECT c.id AS chunk_id, c.document_id, c.chunk_index, c.page_number, c.content,
               d.file_name AS document_name
        FROM document_chunks c JOIN documents d ON d.id = c.document_id
        JOIN workspaces w ON w.id = d.workspace_id
        WHERE c.document_id = ? AND c.chunk_index = ? AND w.owner_user_id = ?
    """, (document_id, chunk_index, user["id"])).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy đoạn trích dẫn")
    return {"citation": dict(row)}


@router.post("/documents/{document_id}/reindex-vectors")
async def reindex_document_vectors(document_id: str, user: Dict[str, str] = Depends(get_current_user)):
    conn = get_db_connection()
    owned = conn.execute("""SELECT 1 FROM documents d JOIN workspaces w ON w.id = d.workspace_id
                              WHERE d.id = ? AND w.owner_user_id = ?""",
                         (document_id, user["id"])).fetchone()
    conn.close()
    if not owned:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    try:
        return await run_in_threadpool(reindex_document_embeddings, document_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
