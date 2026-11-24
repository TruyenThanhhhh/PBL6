import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, UploadFile, File, Form, HTTPException, Depends
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.database import get_db_connection
from app.services.document_service import (
    build_document_guide,
    process_and_index_document,
    rebuild_document_from_source,
    reindex_document_embeddings,
)
from app.services.llm_service import decode_symbol_pua_text
from app.services.workspace_ai_service import (
    generate_and_apply_workspace_metadata,
    generate_unique_default_workspace_name,
    schedule_workspace_embedding,
    semantic_global_search,
    semantic_search_workspaces,
    upsert_workspace_embedding,
)
from app.config import DEFAULT_LLM_MODEL, UPLOAD_MAX_BYTES
from app.api.auth import get_current_user, get_current_user_optional

router = APIRouter(prefix="/api/v1", tags=["Workspaces & Documents"])
logger = logging.getLogger(__name__)


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=1000)
    category: str = Field(default="Chung", max_length=60)
    icon: str = Field(default="folder", max_length=40)


class WorkspaceUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=1000)
    category: Optional[str] = Field(default=None, max_length=60)
    icon: Optional[str] = Field(default=None, max_length=40)


class WorkspaceGenerateMetadataRequest(BaseModel):
    model: Optional[str] = None


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


class StudyArtifactUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    data: Optional[Any] = None


def _assert_workspace_owner(conn, workspace_id: str, user_id: str) -> None:
    owned = conn.execute(
        "SELECT 1 FROM workspaces WHERE id = ? AND owner_user_id = ?",
        (workspace_id, user_id),
    ).fetchone()
    if not owned:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy workspace")


def _fetch_workspace_with_counts(conn, workspace_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        """
        SELECT w.*,
               (SELECT COUNT(*) FROM documents d WHERE d.workspace_id = w.id) AS doc_count,
               (SELECT COUNT(*) FROM chat_sessions s WHERE s.workspace_id = w.id) AS conversation_count
        FROM workspaces w
        WHERE w.id = ?
        """,
        (workspace_id,),
    ).fetchone()
    return dict(row) if row else None


@router.post("/workspaces", status_code=201)
async def create_workspace(req: WorkspaceCreateRequest, user: Dict[str, Any] = Depends(get_current_user)):
    workspace_id = str(uuid.uuid4())
    conn = get_db_connection()
    try:
        ws_name = req.name.strip() or generate_unique_default_workspace_name(conn, user["id"])
        conn.execute(
            "INSERT INTO workspaces (id, name, description, category, icon, owner_user_id) VALUES (?, ?, ?, ?, ?, ?)",
            (workspace_id, ws_name, req.description.strip(), req.category.strip() or "Chung", req.icon.strip() or "folder", user["id"]),
        )
        conn.execute(
            "INSERT INTO user_activities (id, workspace_id, activity_type, message) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), workspace_id, "workspace", f"Tạo không gian làm việc '{ws_name}'"),
        )
        conn.commit()
        ws = _fetch_workspace_with_counts(conn, workspace_id)
    finally:
        conn.close()
    await run_in_threadpool(upsert_workspace_embedding, workspace_id)
    return {"workspace": ws}


@router.patch("/workspaces/{workspace_id}")
async def update_workspace(
    workspace_id: str,
    req: WorkspaceUpdateRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    conn = get_db_connection()
    try:
        _assert_workspace_owner(conn, workspace_id, user["id"])
        existing = conn.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
        new_name = req.name.strip() if req.name is not None else existing["name"]
        new_desc = req.description.strip() if req.description is not None else (existing["description"] or "")
        new_cat = req.category.strip() if req.category is not None else (existing["category"] or "Chung")
        new_icon = req.icon.strip() if req.icon is not None else (existing["icon"] or "folder")
        conn.execute(
            "UPDATE workspaces SET name = ?, description = ?, category = ?, icon = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_name, new_desc, new_cat, new_icon, workspace_id),
        )
        conn.commit()
        ws = _fetch_workspace_with_counts(conn, workspace_id)
    finally:
        conn.close()
    await run_in_threadpool(upsert_workspace_embedding, workspace_id)
    return {"workspace": ws}


@router.get("/workspaces")
def list_workspaces(user: Dict[str, Any] = Depends(get_current_user)):
    conn = get_db_connection()
    try:
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT w.*,
                       (SELECT COUNT(*) FROM documents d WHERE d.workspace_id = w.id) AS doc_count,
                       (SELECT COUNT(*) FROM chat_sessions s WHERE s.workspace_id = w.id) AS conversation_count
                FROM workspaces w
                WHERE w.owner_user_id = ?
                ORDER BY COALESCE(w.updated_at, w.created_at) DESC
                """,
                (user["id"],),
            ).fetchall()
        ]
        return {"workspaces": rows}
    finally:
        conn.close()


@router.get("/workspaces/search")
async def search_workspaces(
    q: str = "",
    limit: int = 30,
    user: Dict[str, Any] = Depends(get_current_user),
):
    bounded_limit = min(max(limit, 1), 100)
    return await run_in_threadpool(semantic_search_workspaces, user["id"], q, bounded_limit)


@router.get("/search")
async def search_all_knowledge(
    q: str = "",
    kind: str = "all",
    limit: int = 24,
    user: Dict[str, Any] = Depends(get_current_user),
):
    allowed_kinds = {"all", "workspace", "notebook", "document", "note", "conversation"}
    safe_kind = kind if kind in allowed_kinds else "all"
    bounded_limit = min(max(limit, 1), 60)
    return await run_in_threadpool(semantic_global_search, user["id"], q, safe_kind, bounded_limit)


@router.post("/workspaces/{workspace_id}/generate-metadata")
async def generate_workspace_metadata_endpoint(
    workspace_id: str,
    req: Optional[WorkspaceGenerateMetadataRequest] = Body(default=None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    conn = get_db_connection()
    _assert_workspace_owner(conn, workspace_id, user["id"])
    conn.close()
    model = (req.model if req and req.model else DEFAULT_LLM_MODEL)
    return await generate_and_apply_workspace_metadata(workspace_id, model=model)


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
async def create_notebook(
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
    await run_in_threadpool(upsert_workspace_embedding, workspace_id)
    return {"notebook": dict(row)}


@router.delete("/notebooks/{notebook_id}")
async def delete_notebook(notebook_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    conn = get_db_connection()
    owned = conn.execute(
        """SELECT n.workspace_id FROM notebooks n JOIN workspaces w ON w.id = n.workspace_id
           WHERE n.id = ? AND w.owner_user_id = ?""",
        (notebook_id, user["id"]),
    ).fetchone()
    if not owned:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy notebook")
    ws_id = owned["workspace_id"]
    conn.execute("DELETE FROM notebooks WHERE id = ?", (notebook_id,))
    conn.commit()
    conn.close()
    await run_in_threadpool(upsert_workspace_embedding, ws_id)
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
    defer_metadata: bool = Form(default=False),
    replace_document_id: Optional[str] = Form(default=None),
    effective_date: Optional[str] = Form(default=None),
    auto_version: bool = Form(default=False),
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
            process_and_index_document,
            workspace_id,
            file.filename,
            content,
            clean_notebook_id,
            replace_document_id,
            effective_date,
            auto_version,
        )
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Lỗi khi xử lý và lập chỉ mục tài liệu: %s", exc)
        raise HTTPException(status_code=500, detail=f"Lỗi khi xử lý tài liệu: {str(exc)}") from exc

    updated_workspace: Optional[Dict[str, Any]] = None
    metadata_source = "deferred"
    if defer_metadata:
        await run_in_threadpool(schedule_workspace_embedding, workspace_id)
    else:
        try:
            meta_res = await generate_and_apply_workspace_metadata(workspace_id)
            updated_workspace = meta_res.get("workspace")
            metadata_source = str(meta_res.get("source") or "ai")
        except Exception:
            logger.exception("Tự động tạo metadata workspace thất bại cho %s", workspace_id)
            metadata_source = "error"
            await run_in_threadpool(schedule_workspace_embedding, workspace_id)

    return {
        "message": "Tài liệu đã được tải lên và lập chỉ mục thành công",
        "document": result,
        "workspace": updated_workspace,
        "metadata_source": metadata_source,
    }


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor()

    row = cursor.execute(
        """SELECT d.file_path, d.file_name, d.workspace_id,
                  d.version_group_id, COALESCE(d.is_latest, 1) AS is_latest
           FROM documents d JOIN workspaces w ON w.id = d.workspace_id
           WHERE d.id = ? AND w.owner_user_id = ?""",
        (document_id, user["id"]),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    file_path = row["file_path"]
    ws_id = row["workspace_id"]
    vg_id = row["version_group_id"]
    was_latest = bool(row["is_latest"])

    cursor.execute("DELETE FROM chunks_fts WHERE document_id = ?", (document_id,))
    cursor.execute(
        "DELETE FROM chunk_embeddings WHERE chunk_id IN "
        "(SELECT id FROM document_chunks WHERE document_id = ?)",
        (document_id,),
    )
    cursor.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
    cursor.execute("DELETE FROM documents WHERE id = ?", (document_id,))

    if was_latest and vg_id:
        prev_row = cursor.execute(
            """
            SELECT id FROM documents
            WHERE workspace_id = ? AND version_group_id = ?
            ORDER BY COALESCE(version_number, 1) DESC, created_at DESC
            LIMIT 1
            """,
            (ws_id, vg_id),
        ).fetchone()
        if prev_row:
            cursor.execute(
                "UPDATE documents SET is_latest = 1, superseded_by = NULL WHERE id = ?",
                (prev_row["id"],),
            )

    conn.commit()
    conn.close()
    Path(file_path).unlink(missing_ok=True)
    try:
        from app.services.retrieval_service import invalidate_workspace_vector_cache
        invalidate_workspace_vector_cache(ws_id)
    except Exception:
        pass
    await run_in_threadpool(upsert_workspace_embedding, ws_id)
    return {"message": "Đã xóa tài liệu thành công"}


class DocumentDiffRequest(BaseModel):
    old_document_id: Optional[str] = None
    new_document_id: Optional[str] = None
    include_ai_summary: bool = True


@router.post("/workspaces/{workspace_id}/documents/diff")
async def diff_workspace_documents(
    workspace_id: str,
    req: DocumentDiffRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Đối chiếu điểm khác biệt giữa 2 phiên bản tài liệu (hoặc 2 bản gần nhất trong cùng nhóm)."""
    conn = get_db_connection()
    _assert_workspace_owner(conn, workspace_id, user["id"])
    conn.close()

    from app.services.document_diff_service import (
        compute_document_diff,
        format_diff_markdown,
        summarize_diff_with_llm,
    )

    diff_res = compute_document_diff(
        workspace_id=workspace_id,
        old_document_id=req.old_document_id,
        new_document_id=req.new_document_id,
    )
    if not diff_res.get("ok"):
        raise HTTPException(status_code=400, detail=diff_res.get("error") or "Không thể đối chiếu tài liệu")

    markdown = (
        await summarize_diff_with_llm(diff_res)
        if req.include_ai_summary
        else format_diff_markdown(diff_res)
    )
    return {**diff_res, "markdown": markdown}


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
    item = dict(row)
    item["content"] = decode_symbol_pua_text(item.get("content") or "")
    return {"citation": item}


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
    chunks = []
    for r in cursor.fetchall():
        item = dict(r)
        item["content"] = decode_symbol_pua_text(item.get("content") or "")
        chunks.append(item)

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


@router.post("/documents/{document_id}/rebuild")
async def rebuild_document(document_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Trích xuất lại văn bản sạch (PDF sort=True + giải mã ký tự toán học) và tái tạo chỉ mục cho tài liệu cũ."""
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
        return await run_in_threadpool(rebuild_document_from_source, document_id, False)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/documents/{document_id}/guide")
async def get_document_guide(
    document_id: str,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
):
    """Trả về Source Guide kiểu NotebookLM: tóm tắt cấu trúc, danh sách chủ đề và câu hỏi gợi ý."""
    conn = get_db_connection()
    row = conn.execute(
        """SELECT d.id, w.owner_user_id FROM documents d
           JOIN workspaces w ON w.id = d.workspace_id
           WHERE d.id = ?""",
        (document_id,),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    if user and row["owner_user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    try:
        return await run_in_threadpool(build_document_guide, document_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
async def create_note(
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
    await run_in_threadpool(upsert_workspace_embedding, workspace_id)
    return {"note": dict(row)}


@router.delete("/notes/{note_id}")
async def delete_note(note_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    conn = get_db_connection()
    owned = conn.execute(
        """SELECT n.workspace_id FROM notes n JOIN workspaces w ON w.id = n.workspace_id
           WHERE n.id = ? AND w.owner_user_id = ?""",
        (note_id, user["id"]),
    ).fetchone()
    if not owned:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy ghi chú")
    ws_id = owned["workspace_id"]
    conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    conn.commit()
    conn.close()
    await run_in_threadpool(upsert_workspace_embedding, ws_id)
    return {"message": "Đã xóa ghi chú"}


def _normalize_utc_timestamp(value: Optional[str]) -> str:
    """Chuẩn hóa timestamp SQLite ('YYYY-MM-DD HH:MM:SS') sang ISO-8601 UTC."""
    raw = (value or "").strip()
    if not raw:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if "T" not in raw and " " in raw:
        raw = raw.replace(" ", "T", 1)
    if not raw.endswith("Z") and "+" not in raw[10:] and "-" not in raw[10:]:
        raw = f"{raw}Z"
    return raw


@router.get("/workspaces/{workspace_id}/study-artifacts")
def list_study_artifacts(
    workspace_id: str,
    artifact_type: Optional[str] = None,
    user: Dict[str, Any] = Depends(get_current_user),
):
    conn = get_db_connection()
    _assert_workspace_owner(conn, workspace_id, user["id"])
    rows = []
    clean_type = (artifact_type or "").strip()
    if clean_type:
        cursor = conn.execute(
            """SELECT * FROM study_artifacts
               WHERE workspace_id = ? AND artifact_type = ?
               ORDER BY created_at DESC""",
            (workspace_id, clean_type),
        )
    else:
        cursor = conn.execute(
            "SELECT * FROM study_artifacts WHERE workspace_id = ? ORDER BY created_at DESC",
            (workspace_id,),
        )
    for row in cursor.fetchall():
        item = dict(row)
        item["created_at"] = _normalize_utc_timestamp(item.get("created_at"))
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
    clean_title = req.title.strip()
    clean_type = req.artifact_type.strip()
    if not clean_title or not clean_type:
        raise HTTPException(status_code=400, detail="Tiêu đề và loại học liệu không được để trống")

    conn = get_db_connection()
    _assert_workspace_owner(conn, workspace_id, user["id"])

    doc_id = req.document_id
    if doc_id:
        doc_exists = conn.execute(
            "SELECT 1 FROM documents WHERE id = ? AND workspace_id = ?",
            (doc_id, workspace_id),
        ).fetchone()
        if not doc_exists:
            doc_id = None

    artifact_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data_json = json.dumps(req.data, ensure_ascii=False)
    conn.execute(
        """INSERT INTO study_artifacts (id, workspace_id, document_id, artifact_type, title, data_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (artifact_id, workspace_id, doc_id, clean_type, clean_title, data_json, created_at),
    )
    conn.commit()
    conn.close()
    return {
        "artifact": {
            "id": artifact_id,
            "workspace_id": workspace_id,
            "document_id": doc_id,
            "artifact_type": clean_type,
            "title": clean_title,
            "data": req.data,
            "created_at": created_at,
        }
    }


@router.patch("/workspaces/{workspace_id}/study-artifacts/{artifact_id}")
def update_study_artifact(
    workspace_id: str,
    artifact_id: str,
    req: StudyArtifactUpdateRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    conn = get_db_connection()
    _assert_workspace_owner(conn, workspace_id, user["id"])
    row = conn.execute(
        "SELECT * FROM study_artifacts WHERE id = ? AND workspace_id = ?",
        (artifact_id, workspace_id),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Học liệu không tồn tại")

    next_title = req.title.strip() if req.title is not None else row["title"]
    if not next_title:
        conn.close()
        raise HTTPException(status_code=400, detail="Tiêu đề học liệu không được để trống")

    if req.data is not None:
        next_data = req.data
        next_data_json = json.dumps(req.data, ensure_ascii=False)
    else:
        next_data_json = row["data_json"]
        try:
            next_data = json.loads(next_data_json or "{}")
        except Exception:
            next_data = {}

    conn.execute(
        "UPDATE study_artifacts SET title = ?, data_json = ? WHERE id = ? AND workspace_id = ?",
        (next_title, next_data_json, artifact_id, workspace_id),
    )
    conn.commit()
    conn.close()
    return {
        "artifact": {
            "id": artifact_id,
            "workspace_id": workspace_id,
            "document_id": row["document_id"],
            "artifact_type": row["artifact_type"],
            "title": next_title,
            "data": next_data,
            "created_at": _normalize_utc_timestamp(row["created_at"]),
        }
    }


@router.delete("/workspaces/{workspace_id}/study-artifacts/{artifact_id}")
def delete_study_artifact(
    workspace_id: str,
    artifact_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    conn = get_db_connection()
    _assert_workspace_owner(conn, workspace_id, user["id"])
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM study_artifacts WHERE id = ? AND workspace_id = ?",
        (artifact_id, workspace_id),
    )
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Học liệu không tồn tại")
    conn.commit()
    conn.close()
    return {"message": "Đã xóa học liệu thành công", "id": artifact_id}


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
