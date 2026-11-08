import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.database import get_db_connection
from app.services.document_service import (
    process_and_index_document_async,
    reindex_document_embeddings,
)
from app.config import UPLOAD_MAX_BYTES
from app.api.auth import get_current_user, get_current_user_optional

router = APIRouter(prefix="/api/v1", tags=["Workspaces & Documents"])
logger = logging.getLogger(__name__)


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    category: str = Field(default="Chung", max_length=60)
    icon: str = Field(default="folder", max_length=40)


class NotebookCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)


class NoteCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=50000)
    notebook_id: Optional[str] = None
    document_id: Optional[str] = None


class StudyArtifactCreateRequest(BaseModel):
    artifact_type: str = Field(min_length=2, max_length=40)
    title: str = Field(min_length=1, max_length=200)
    document_id: Optional[str] = None
    data: Any


def _assert_workspace_owner(conn, workspace_id: str, user_id: str) -> None:
    owned = conn.execute(
        "SELECT 1 FROM workspaces WHERE id = ? AND owner_user_id = ?",
        (workspace_id, user_id),
    ).fetchone()
    if not owned:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy workspace")


@router.post("/workspaces", status_code=201)
def create_workspace(req: WorkspaceCreateRequest, user: Dict[str, Any] = Depends(get_current_user)):
    workspace_id = str(uuid.uuid4())
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO workspaces (id, name, description, category, icon, owner_user_id) VALUES (?, ?, ?, ?, ?, ?)",
        (workspace_id, req.name.strip(), req.description.strip(), req.category.strip(), req.icon.strip(), user["id"]),
    )
    conn.execute(
        "INSERT INTO user_activities (id, workspace_id, activity_type, message) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), workspace_id, "workspace", f"Tạo không gian làm việc '{req.name.strip()}'"),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
    conn.close()
    return {"workspace": dict(row)}


@router.patch("/workspaces/{workspace_id}")
def update_workspace(
    workspace_id: str,
    req: WorkspaceCreateRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    conn = get_db_connection()
    _assert_workspace_owner(conn, workspace_id, user["id"])
    conn.execute(
        "UPDATE workspaces SET name = ?, description = ?, category = ?, icon = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (req.name.strip(), req.description.strip(), req.category.strip(), req.icon.strip(), workspace_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
    conn.close()
    return {"workspace": dict(row)}


@router.get("/workspaces")
def list_workspaces(user: Dict[str, Any] = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM workspaces WHERE owner_user_id = ? ORDER BY created_at ASC",
        (user["id"],),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"workspaces": rows}


@router.delete("/workspaces/{workspace_id}")
def delete_workspace(workspace_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Xóa workspace (CASCADE xóa toàn bộ documents, notebooks, notes, chunks liên quan)"""
    if workspace_id == "default":
        raise HTTPException(status_code=400, detail="Không thể xóa workspace mặc định")
    conn = get_db_connection()
    cursor = conn.cursor()
    _assert_workspace_owner(conn, workspace_id, user["id"])
    cursor.execute("SELECT file_path FROM documents WHERE workspace_id = ?", (workspace_id,))
    file_paths = [row["file_path"] for row in cursor.fetchall()]
    cursor.execute("DELETE FROM chunks_fts WHERE workspace_id = ?", (workspace_id,))
    cursor.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
    conn.commit()
    conn.close()
    for fp in file_paths:
        try:
            if fp:
                Path(fp).unlink(missing_ok=True)
        except Exception as e:
            logger.warning("Không thể xóa file %s: %s", fp, e)
    return {"message": f"Đã xóa workspace '{workspace_id}' và toàn bộ tài liệu liên quan"}


# --- Notebook Endpoints ---

@router.get("/workspaces/{workspace_id}/notebooks")
def list_notebooks(workspace_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    conn = get_db_connection()
    _assert_workspace_owner(conn, workspace_id, user["id"])
    rows = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM notebooks WHERE workspace_id = ? ORDER BY created_at DESC",
            (workspace_id,),
        ).fetchall()
    ]
    conn.close()
    return {"notebooks": rows}


@router.post("/workspaces/{workspace_id}/notebooks", status_code=201)
def create_notebook(
    workspace_id: str,
    req: NotebookCreateRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    conn = get_db_connection()
    _assert_workspace_owner(conn, workspace_id, user["id"])
    notebook_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO notebooks (id, workspace_id, name, description) VALUES (?, ?, ?, ?)",
        (notebook_id, workspace_id, req.name.strip(), req.description.strip()),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM notebooks WHERE id = ?", (notebook_id,)).fetchone()
    conn.close()
    return {"notebook": dict(row)}


@router.delete("/notebooks/{notebook_id}")
def delete_notebook(notebook_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    conn = get_db_connection()
    owned = conn.execute(
        """SELECT 1 FROM notebooks n JOIN workspaces w ON w.id = n.workspace_id
           WHERE n.id = ? AND w.owner_user_id = ?""",
        (notebook_id, user["id"]),
    ).fetchone()
    if not owned:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy notebook")
    conn.execute("DELETE FROM notebooks WHERE id = ?", (notebook_id,))
    conn.commit()
    conn.close()
    return {"message": "Đã xóa notebook"}


# --- Document Endpoints ---

@router.get("/workspaces/{workspace_id}/documents")
def list_documents(workspace_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    conn = get_db_connection()
    _assert_workspace_owner(conn, workspace_id, user["id"])
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM documents WHERE workspace_id = ? ORDER BY created_at DESC", (workspace_id,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"documents": rows}


@router.post("/workspaces/{workspace_id}/documents/upload")
async def upload_document(
    workspace_id: str,
    file: UploadFile = File(...),
    notebook_id: Optional[str] = Form(default=None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    conn = get_db_connection()
    _assert_workspace_owner(conn, workspace_id, user["id"])
    conn.close()

    content = await file.read(UPLOAD_MAX_BYTES + 1)
    if len(content) > UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"Tệp vượt quá giới hạn {UPLOAD_MAX_BYTES} bytes")
    if not content:
        raise HTTPException(status_code=400, detail="File tải lên không có dữ liệu")

    try:
        clean_notebook_id = notebook_id.strip() if notebook_id and notebook_id.strip() else None
        result = await run_in_threadpool(
            process_and_index_document, workspace_id, file.filename, content, clean_notebook_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Lỗi khi xử lý và lập chỉ mục tài liệu: %s", exc)
        raise HTTPException(status_code=500, detail=f"Lỗi khi xử lý tài liệu: {str(exc)}") from exc
    return {"message": "Tài liệu đã được tải lên và lập chỉ mục thành công", "document": result}


@router.delete("/documents/{document_id}")
def delete_document(document_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor()

    row = cursor.execute(
        """SELECT d.file_path, d.file_name, d.workspace_id
           FROM documents d JOIN workspaces w ON w.id = d.workspace_id
           WHERE d.id = ? AND w.owner_user_id = ?""",
        (document_id, user["id"]),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    file_path = row["file_path"]

    cursor.execute("DELETE FROM chunks_fts WHERE document_id = ?", (document_id,))
    cursor.execute(
        "DELETE FROM chunk_embeddings WHERE chunk_id IN "
        "(SELECT id FROM document_chunks WHERE document_id = ?)",
        (document_id,),
    )
    cursor.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
    cursor.execute("DELETE FROM documents WHERE id = ?", (document_id,))

    conn.commit()
    conn.close()
    Path(file_path).unlink(missing_ok=True)
    return {"message": "Đã xóa tài liệu thành công"}


@router.get("/documents/{document_id}/chunks/{chunk_index}")
def get_document_chunk(
    document_id: str,
    chunk_index: int,
    user: Dict[str, Any] = Depends(get_current_user),
):
    conn = get_db_connection()
    row = conn.execute(
        """
        SELECT c.id AS chunk_id, c.document_id, c.chunk_index, c.page_number, c.content,
               d.file_name AS document_name
        FROM document_chunks c JOIN documents d ON d.id = c.document_id
        JOIN workspaces w ON w.id = d.workspace_id
        WHERE c.document_id = ? AND c.chunk_index = ? AND w.owner_user_id = ?
        """,
        (document_id, chunk_index, user["id"]),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy đoạn trích dẫn")
    return {"citation": dict(row)}


@router.get("/documents/{document_id}")
def get_document_detail(
    document_id: str,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
):
    conn = get_db_connection()
    row = conn.execute(
        """
        SELECT d.*, w.name AS workspace_name, w.owner_user_id
        FROM documents d
        JOIN workspaces w ON w.id = d.workspace_id
        WHERE d.id = ?
        """,
        (document_id,),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    if user and row["owner_user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    doc = dict(row)
    doc.pop("owner_user_id", None)
    return {"document": doc}


@router.get("/documents/{document_id}/chunks")
def get_document_chunks(
    document_id: str,
    page: Optional[int] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
):
    conn = get_db_connection()
    doc_row = conn.execute(
        """
        SELECT d.*, w.name AS workspace_name, w.owner_user_id
        FROM documents d
        JOIN workspaces w ON w.id = d.workspace_id
        WHERE d.id = ?
        """,
        (document_id,),
    ).fetchone()
    if not doc_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    if user and doc_row["owner_user_id"] != user["id"]:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")

    query = """
        SELECT id, document_id, workspace_id, chunk_index, page_number, token_count, content, created_at
        FROM document_chunks
        WHERE document_id = ?
    """
    params = [document_id]
    if page is not None and page > 0:
        query += " AND page_number = ?"
        params.append(page)

    query += " ORDER BY chunk_index ASC"

    if limit is not None and limit > 0:
        query += " LIMIT ?"
        params.append(limit)
        if offset is not None and offset >= 0:
            query += " OFFSET ?"
            params.append(offset)

    cursor = conn.cursor()
    cursor.execute(query, tuple(params))
    chunks = [dict(r) for r in cursor.fetchall()]

    count_row = conn.execute(
        "SELECT COUNT(*) AS total FROM document_chunks WHERE document_id = ?",
        (document_id,),
    ).fetchone()
    total_chunks = count_row["total"] if count_row else len(chunks)
    conn.close()

    doc_data = dict(doc_row)
    doc_data.pop("owner_user_id", None)
    doc_data["total_chunks"] = total_chunks

    return {
        "document": doc_data,
        "chunks": chunks,
        "total": len(chunks),
        "total_chunks": total_chunks,
    }


@router.post("/documents/{document_id}/reindex-vectors")
async def reindex_document_vectors(document_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    conn = get_db_connection()
    owned = conn.execute(
        """SELECT 1 FROM documents d JOIN workspaces w ON w.id = d.workspace_id
           WHERE d.id = ? AND w.owner_user_id = ?""",
        (document_id, user["id"]),
    ).fetchone()
    conn.close()
    if not owned:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    try:
        return await run_in_threadpool(reindex_document_embeddings, document_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# --- Notes & Study Artifacts & Activities Endpoints ---

@router.get("/workspaces/{workspace_id}/notes")
def list_notes(workspace_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    conn = get_db_connection()
    _assert_workspace_owner(conn, workspace_id, user["id"])
    rows = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM notes WHERE workspace_id = ? ORDER BY updated_at DESC",
            (workspace_id,),
        ).fetchall()
    ]
    conn.close()
    return {"notes": rows}


@router.post("/workspaces/{workspace_id}/notes", status_code=201)
def create_note(
    workspace_id: str,
    req: NoteCreateRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    conn = get_db_connection()
    _assert_workspace_owner(conn, workspace_id, user["id"])
    note_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO notes (id, workspace_id, notebook_id, document_id, title, content) VALUES (?, ?, ?, ?, ?, ?)",
        (note_id, workspace_id, req.notebook_id, req.document_id, req.title.strip(), req.content.strip()),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    conn.close()
    return {"note": dict(row)}


@router.delete("/notes/{note_id}")
def delete_note(note_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    conn = get_db_connection()
    owned = conn.execute(
        """SELECT 1 FROM notes n JOIN workspaces w ON w.id = n.workspace_id
           WHERE n.id = ? AND w.owner_user_id = ?""",
        (note_id, user["id"]),
    ).fetchone()
    if not owned:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy ghi chú")
    conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    conn.commit()
    conn.close()
    return {"message": "Đã xóa ghi chú"}


@router.get("/workspaces/{workspace_id}/study-artifacts")
def list_study_artifacts(workspace_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    conn = get_db_connection()
    _assert_workspace_owner(conn, workspace_id, user["id"])
    rows = []
    for row in conn.execute(
        "SELECT * FROM study_artifacts WHERE workspace_id = ? ORDER BY created_at DESC",
        (workspace_id,),
    ).fetchall():
        item = dict(row)
        try:
            item["data"] = json.loads(item.pop("data_json", "{}"))
        except Exception:
            item["data"] = {}
        rows.append(item)
    conn.close()
    return {"artifacts": rows}


@router.post("/workspaces/{workspace_id}/study-artifacts", status_code=201)
def create_study_artifact(
    workspace_id: str,
    req: StudyArtifactCreateRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    conn = get_db_connection()
    _assert_workspace_owner(conn, workspace_id, user["id"])
    artifact_id = str(uuid.uuid4())
    data_json = json.dumps(req.data, ensure_ascii=False)
    conn.execute(
        """INSERT INTO study_artifacts (id, workspace_id, document_id, artifact_type, title, data_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (artifact_id, workspace_id, req.document_id, req.artifact_type.strip(), req.title.strip(), data_json),
    )
    conn.commit()
    conn.close()
    return {
        "artifact": {
            "id": artifact_id,
            "workspace_id": workspace_id,
            "document_id": req.document_id,
            "artifact_type": req.artifact_type.strip(),
            "title": req.title.strip(),
            "data": req.data,
        }
    }


@router.get("/workspaces/{workspace_id}/activities")
def list_activities(workspace_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    conn = get_db_connection()
    _assert_workspace_owner(conn, workspace_id, user["id"])
    rows = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM user_activities WHERE workspace_id = ? ORDER BY created_at DESC LIMIT 30",
            (workspace_id,),
        ).fetchall()
    ]
    conn.close()
    return {"activities": rows}
