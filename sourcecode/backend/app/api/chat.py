import base64
import binascii
import json
import logging
import uuid
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from app.api.auth import get_current_user
from app.config import (
    DEFAULT_LLM_MODEL,
    EMBEDDING_MODEL,
    ENABLE_DENSE_RETRIEVAL,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    WEB_SEARCH_ENABLED,
)
from app.database import get_db_connection
from app.services.ai_router import answer_query, stream_query
from app.services.llm_service import check_ollama_status
from app.services.web_search_service import search_web

router = APIRouter(prefix="/api/v1", tags=["Chat, Streaming & Conversations"])
logger = logging.getLogger(__name__)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)


class ChatQueryRequest(BaseModel):
    workspace_id: str = "default"
    conversation_id: Optional[str] = None
    query: str = Field(min_length=1, max_length=12000)
    model: Optional[str] = None
    mode: Optional[Literal["auto", "local", "web", "hybrid"]] = "auto"
    web_search: bool = False
    top_k: int = Field(default=4, ge=1, le=20)
    selected_document_id: Optional[str] = Field(default=None, max_length=100)
    document_ids: Optional[List[str]] = None
    history: list[ChatTurn] = Field(default_factory=list, max_length=12)
    image_base64: Optional[str] = Field(default=None, max_length=7_000_000)
    image_mime_type: Optional[Literal["image/png", "image/jpeg", "image/webp"]] = None

    @model_validator(mode="after")
    def validate_image_payload(self):
        if self.image_base64:
            if not self.image_mime_type:
                raise ValueError("Thiếu loại ảnh")
            try:
                raw = base64.b64decode(self.image_base64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError("Ảnh gửi lên không hợp lệ") from exc
            if len(raw) > 5 * 1024 * 1024:
                raise ValueError("Ảnh tối đa 5 MB")
        elif self.image_mime_type:
            raise ValueError("Thiếu dữ liệu ảnh")
        return self


class ChatStreamRequest(BaseModel):
    workspace_id: str = "default"
    conversation_id: Optional[str] = None
    notebook_id: Optional[str] = None
    document_ids: Optional[List[str]] = None
    selected_document_id: Optional[str] = None
    query: str = Field(min_length=1, max_length=12000)
    model: Optional[str] = None
    mode: Optional[Literal["auto", "local", "web", "hybrid"]] = "auto"
    top_k: int = Field(default=4, ge=1, le=20)
    history: list[ChatTurn] = Field(default_factory=list, max_length=12)
    image_base64: Optional[str] = None
    image_mime_type: Optional[Literal["image/png", "image/jpeg", "image/webp"]] = None


class ConversationCreateRequest(BaseModel):
    title: str = Field(default="Cuộc trò chuyện mới", min_length=1, max_length=200)
    notebook_id: Optional[str] = None
    mode: str = "auto"
    model_name: Optional[str] = DEFAULT_LLM_MODEL


class ConversationUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    notebook_id: Optional[str] = None
    mode: Optional[str] = None


class MessageCreateRequest(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)
    citations: Optional[List[Dict[str, Any]]] = None
    mode_used: Optional[str] = None


def _assert_workspace_ownership(conn, workspace_id: str, user_id: str) -> None:
    owned = conn.execute(
        "SELECT 1 FROM workspaces WHERE id = ? AND owner_user_id = ?",
        (workspace_id, user_id),
    ).fetchone()
    if not owned:
        raise HTTPException(status_code=404, detail="Không tìm thấy workspace")


def _ensure_conversation_record(
    conn,
    conversation_id: str,
    workspace_id: str,
    title: str,
    mode: str,
    model_name: str,
    notebook_id: Optional[str] = None,
) -> None:
    row = conn.execute("SELECT id FROM chat_sessions WHERE id = ?", (conversation_id,)).fetchone()
    if not row:
        conn.execute(
            """
            INSERT INTO chat_sessions (id, workspace_id, notebook_id, title, mode, model_name)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (conversation_id, workspace_id, notebook_id, title[:200], mode, model_name or DEFAULT_LLM_MODEL),
        )


@router.get("/status")
async def get_system_status():
    ollama_info = await check_ollama_status()
    return {
        "status": "online",
        "database": "SQLite FTS5 Local",
        "ollama": ollama_info,
        "dense_retrieval": {"enabled": ENABLE_DENSE_RETRIEVAL, "model": EMBEDDING_MODEL},
        "web_search_enabled": WEB_SEARCH_ENABLED,
        "google_auth_enabled": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
    }


# =============================================================================
# 1. CHAT STREAMING & SYNCHRONOUS QUERY
# =============================================================================

@router.post("/chat/stream")
async def stream_chat_knowledge_base(
    req: ChatStreamRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Endpoint sinh phản hồi RAG dạng luồng (Server-Sent Events) theo thời gian thực.
    Đồng thời tự động lưu phiên hội thoại và tin nhắn vào cơ sở dữ liệu SQLite.
    """
    conn = get_db_connection()
    try:
        _assert_workspace_ownership(conn, req.workspace_id, user["id"])
        conv_id = req.conversation_id or str(uuid.uuid4())
        _ensure_conversation_record(
            conn,
            conv_id,
            req.workspace_id,
            req.query[:60],
            req.mode or "auto",
            req.model or DEFAULT_LLM_MODEL,
            req.notebook_id,
        )

        user_msg_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO chat_messages (id, session_id, sender, content, mode_used)
            VALUES (?, ?, 'user', ?, ?)
            """,
            (user_msg_id, conv_id, req.query, req.mode or "auto"),
        )
        conn.commit()
    finally:
        conn.close()

    collector: Dict[str, Any] = {
        "full_answer": "",
        "citations": [],
        "model_used": req.model or DEFAULT_LLM_MODEL,
        "engine": "ollama_local",
    }

    async def sse_event_stream():
        try:
            async for chunk in stream_query(
                workspace_id=req.workspace_id,
                query=req.query,
                model=req.model,
                mode=req.mode or "auto",
                include_web=(req.mode in ["web", "hybrid"]),
                top_k=req.top_k,
                history=[turn.model_dump() for turn in req.history],
                image_base64=req.image_base64,
                selected_document_id=req.selected_document_id,
                document_ids=req.document_ids,
                collector=collector,
            ):
                yield chunk
        finally:
            full_ans = collector.get("full_answer", "")
            citations = collector.get("citations", [])
            asst_model = collector.get("model_used", req.model or DEFAULT_LLM_MODEL)
            if full_ans:
                db = get_db_connection()
                try:
                    asst_msg_id = str(uuid.uuid4())
                    db.execute(
                        """
                        INSERT INTO chat_messages (id, session_id, sender, content, citations_json, mode_used)
                        VALUES (?, ?, 'assistant', ?, ?, ?)
                        """,
                        (asst_msg_id, conv_id, full_ans, json.dumps(citations, ensure_ascii=False), req.mode or "auto"),
                    )
                    db.execute(
                        """
                        UPDATE chat_sessions
                        SET updated_at = CURRENT_TIMESTAMP,
                            title = CASE WHEN title = 'Cuộc trò chuyện mới' THEN ? ELSE title END
                        WHERE id = ?
                        """,
                        (req.query[:60], conv_id),
                    )
                    db.commit()
                except Exception:
                    logger.exception("Failed to persist streamed assistant message")
                finally:
                    db.close()

    return StreamingResponse(
        sse_event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/query")
async def query_knowledge_base(
    req: ChatQueryRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Endpoint truy vấn RAG đồng bộ (không streaming), hỗ trợ đa nguồn và đa phương thức.
    """
    conn = get_db_connection()
    try:
        _assert_workspace_ownership(conn, req.workspace_id, user["id"])
        conv_id = req.conversation_id
        if conv_id:
            _ensure_conversation_record(
                conn,
                conv_id,
                req.workspace_id,
                req.query[:60],
                req.mode or "auto",
                req.model or DEFAULT_LLM_MODEL,
            )
            user_msg_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO chat_messages (id, session_id, sender, content, mode_used)
                VALUES (?, ?, 'user', ?, ?)
                """,
                (user_msg_id, conv_id, req.query, req.mode or "auto"),
            )
            conn.commit()
    finally:
        conn.close()

    result = await answer_query(
        workspace_id=req.workspace_id,
        query=req.query,
        model=req.model,
        include_web=(req.web_search or req.mode in ["web", "hybrid"]),
        top_k=req.top_k,
        history=[turn.model_dump() for turn in req.history],
        image_base64=req.image_base64,
        selected_document_id=req.selected_document_id,
        document_ids=req.document_ids,
        mode=req.mode or "auto",
    )

    if req.conversation_id and result.get("answer"):
        conn = get_db_connection()
        try:
            asst_msg_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO chat_messages (id, session_id, sender, content, citations_json, mode_used)
                VALUES (?, ?, 'assistant', ?, ?, ?)
                """,
                (
                    asst_msg_id,
                    req.conversation_id,
                    result["answer"],
                    json.dumps(result.get("citations", []), ensure_ascii=False),
                    req.mode or "auto",
                ),
            )
            conn.execute(
                """
                UPDATE chat_sessions
                SET updated_at = CURRENT_TIMESTAMP,
                    title = CASE WHEN title = 'Cuộc trò chuyện mới' THEN ? ELSE title END
                WHERE id = ?
                """,
                (req.query[:60], req.conversation_id),
            )
            conn.commit()
        finally:
            conn.close()

    return result


class WebSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=5, ge=1, le=10)


@router.post("/search/web")
async def web_search(req: WebSearchRequest, user: Dict[str, Any] = Depends(get_current_user)):
    return {"results": await search_web(req.query, req.limit)}


# =============================================================================
# 2. CRUD QUẢN LÝ LỊCH SỬ HỘI THOẠI & TIN NHẮN (CONVERSATIONS)
# =============================================================================

@router.get("/workspaces/{workspace_id}/conversations")
def list_conversations(
    workspace_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Lấy danh sách tất cả các phiên hỏi đáp trong Workspace hiện tại.
    """
    conn = get_db_connection()
    try:
        _assert_workspace_ownership(conn, workspace_id, user["id"])
        rows = conn.execute(
            """
            SELECT s.id, s.workspace_id, s.notebook_id, s.title, s.mode, s.model_name,
                   s.created_at, s.updated_at,
                   (SELECT COUNT(*) FROM chat_messages m WHERE m.session_id = s.id) AS message_count,
                   (SELECT m.content FROM chat_messages m WHERE m.session_id = s.id ORDER BY m.created_at DESC LIMIT 1) AS last_message
            FROM chat_sessions s
            WHERE s.workspace_id = ?
            ORDER BY s.updated_at DESC
            """,
            (workspace_id,),
        ).fetchall()

        conversations = []
        for r in rows:
            conversations.append({
                "id": r["id"],
                "workspaceId": r["workspace_id"],
                "notebookId": r["notebook_id"],
                "title": r["title"],
                "mode": r["mode"],
                "modelName": r["model_name"],
                "createdAt": r["created_at"],
                "updatedAt": r["updated_at"],
                "messageCount": r["message_count"] or 0,
                "lastMessage": (r["last_message"] or "")[:100],
            })
        return {"conversations": conversations}
    finally:
        conn.close()


@router.post("/workspaces/{workspace_id}/conversations", status_code=201)
def create_conversation(
    workspace_id: str,
    req: ConversationCreateRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Khởi tạo một cuộc trò chuyện mới trong Workspace.
    """
    conn = get_db_connection()
    try:
        _assert_workspace_ownership(conn, workspace_id, user["id"])
        conv_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO chat_sessions (id, workspace_id, notebook_id, title, mode, model_name)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (conv_id, workspace_id, req.notebook_id, req.title.strip(), req.mode, req.model_name or DEFAULT_LLM_MODEL),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (conv_id,)).fetchone()
        return {
            "conversation": {
                "id": row["id"],
                "workspaceId": row["workspace_id"],
                "notebookId": row["notebook_id"],
                "title": row["title"],
                "mode": row["mode"],
                "modelName": row["model_name"],
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
                "messages": [],
            }
        }
    finally:
        conn.close()


@router.get("/conversations/{conversation_id}")
def get_conversation_details(
    conversation_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    conn = get_db_connection()
    try:
        row = conn.execute(
            """
            SELECT s.*
            FROM chat_sessions s
            JOIN workspaces w ON w.id = s.workspace_id
            WHERE s.id = ? AND w.owner_user_id = ?
            """,
            (conversation_id, user["id"]),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy cuộc trò chuyện")
        return {
            "conversation": {
                "id": row["id"],
                "workspaceId": row["workspace_id"],
                "notebookId": row["notebook_id"],
                "title": row["title"],
                "mode": row["mode"],
                "modelName": row["model_name"],
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
            }
        }
    finally:
        conn.close()


@router.get("/conversations/{conversation_id}/messages")
def get_conversation_messages(
    conversation_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Lấy toàn bộ lịch sử tin nhắn và trích dẫn bằng chứng của một cuộc trò chuyện.
    """
    conn = get_db_connection()
    try:
        session = conn.execute(
            """
            SELECT s.id
            FROM chat_sessions s
            JOIN workspaces w ON w.id = s.workspace_id
            WHERE s.id = ? AND w.owner_user_id = ?
            """,
            (conversation_id, user["id"]),
        ).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Không tìm thấy cuộc trò chuyện")

        rows = conn.execute(
            """
            SELECT id, sender, content, citations_json, mode_used, latency_seconds, created_at
            FROM chat_messages
            WHERE session_id = ?
            ORDER BY created_at ASC
            """,
            (conversation_id,),
        ).fetchall()

        messages = []
        for r in rows:
            try:
                citations = json.loads(r["citations_json"]) if r["citations_json"] else []
            except Exception:
                citations = []
            formatted_citations = []
            for idx, c in enumerate(citations):
                formatted_citations.append({
                    "refId": c.get("ref_id", idx + 1),
                    "documentId": c.get("document_id"),
                    "documentName": c.get("document_name") or c.get("title") or "Tài liệu",
                    "pageNumber": c.get("page_number"),
                    "chunkIndex": c.get("chunk_index"),
                    "snippet": c.get("snippet", ""),
                    "sourceKind": "local" if c.get("document_id") else "web",
                    "url": c.get("url"),
                })

            messages.append({
                "id": r["id"],
                "role": r["sender"],
                "content": r["content"],
                "createdAt": r["created_at"],
                "citations": formatted_citations,
                "modeUsed": r["mode_used"] or "auto",
                "streaming": False,
            })

        return {"messages": messages}
    finally:
        conn.close()


@router.post("/conversations/{conversation_id}/messages", status_code=201)
def add_conversation_message(
    conversation_id: str,
    req: MessageCreateRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Lưu một tin nhắn mới vào cuộc trò chuyện.
    """
    conn = get_db_connection()
    try:
        session = conn.execute(
            """
            SELECT s.id
            FROM chat_sessions s
            JOIN workspaces w ON w.id = s.workspace_id
            WHERE s.id = ? AND w.owner_user_id = ?
            """,
            (conversation_id, user["id"]),
        ).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Không tìm thấy cuộc trò chuyện")

        msg_id = str(uuid.uuid4())
        citations_json = json.dumps(req.citations or [], ensure_ascii=False) if req.citations else None
        conn.execute(
            """
            INSERT INTO chat_messages (id, session_id, sender, content, citations_json, mode_used)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (msg_id, conversation_id, req.role, req.content, citations_json, req.mode_used),
        )
        conn.execute(
            "UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (conversation_id,),
        )
        conn.commit()
        return {"message_id": msg_id, "status": "saved"}
    finally:
        conn.close()


@router.patch("/conversations/{conversation_id}")
def update_conversation(
    conversation_id: str,
    req: ConversationUpdateRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Đổi tên hoặc cập nhật metadata của cuộc trò chuyện.
    """
    conn = get_db_connection()
    try:
        session = conn.execute(
            """
            SELECT s.id, s.title, s.mode
            FROM chat_sessions s
            JOIN workspaces w ON w.id = s.workspace_id
            WHERE s.id = ? AND w.owner_user_id = ?
            """,
            (conversation_id, user["id"]),
        ).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Không tìm thấy cuộc trò chuyện")

        new_title = req.title.strip() if req.title is not None else session["title"]
        new_mode = req.mode if req.mode is not None else session["mode"]
        conn.execute(
            """
            UPDATE chat_sessions
            SET title = ?, mode = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_title, new_mode, conversation_id),
        )
        conn.commit()
        return {"message": "Đã cập nhật cuộc trò chuyện", "title": new_title}
    finally:
        conn.close()


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Xóa toàn bộ cuộc trò chuyện và lịch sử tin nhắn liên quan.
    """
    conn = get_db_connection()
    try:
        session = conn.execute(
            """
            SELECT s.id, s.title
            FROM chat_sessions s
            JOIN workspaces w ON w.id = s.workspace_id
            WHERE s.id = ? AND w.owner_user_id = ?
            """,
            (conversation_id, user["id"]),
        ).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Không tìm thấy cuộc trò chuyện")

        conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (conversation_id,))
        conn.execute("DELETE FROM chat_sessions WHERE id = ?", (conversation_id,))
        conn.commit()
        return {"message": f"Đã xóa cuộc trò chuyện '{session['title']}'"}
    finally:
        conn.close()


@router.delete("/conversations/{conversation_id}/messages")
def clear_conversation_messages(
    conversation_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Xóa sạch lịch sử tin nhắn bên trong một cuộc trò chuyện mà giữ nguyên phiên hội thoại.
    """
    conn = get_db_connection()
    try:
        session = conn.execute(
            """
            SELECT s.id
            FROM chat_sessions s
            JOIN workspaces w ON w.id = s.workspace_id
            WHERE s.id = ? AND w.owner_user_id = ?
            """,
            (conversation_id, user["id"]),
        ).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Không tìm thấy cuộc trò chuyện")

        conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (conversation_id,))
        conn.commit()
        return {"message": "Đã xóa sạch lịch sử tin nhắn của cuộc trò chuyện"}
    finally:
        conn.close()
