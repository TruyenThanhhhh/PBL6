from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
import base64
import binascii
from typing import Literal, Optional

from app.services.ai_router import answer_query
from app.services.llm_service import check_ollama_status
from app.services.web_search_service import search_web
from app.config import ENABLE_DENSE_RETRIEVAL, EMBEDDING_MODEL, WEB_SEARCH_ENABLED, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from app.api.auth import get_current_user
from app.database import get_db_connection

router = APIRouter(prefix="/api/v1", tags=["Chat & RAG"])

class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=3000)


class ChatQueryRequest(BaseModel):
    workspace_id: str = "default"
    query: str = Field(min_length=1, max_length=12000)
    model: Optional[str] = None
    web_search: bool = False
    top_k: int = Field(default=4, ge=1, le=20)
    selected_document_id: Optional[str] = Field(default=None, max_length=100)
    history: list[ChatTurn] = Field(default_factory=list, max_length=8)
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

@router.post("/chat/query")
async def query_knowledge_base(req: ChatQueryRequest, user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    owned = conn.execute("SELECT 1 FROM workspaces WHERE id = ? AND owner_user_id = ?",
                         (req.workspace_id, user["id"])).fetchone()
    if not owned:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy workspace")
    if req.selected_document_id:
        selected_document = conn.execute(
            "SELECT 1 FROM documents WHERE id = ? AND workspace_id = ?",
            (req.selected_document_id, req.workspace_id),
        ).fetchone()
        if not selected_document:
            conn.close()
            raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu được chọn trong kho này")
    conn.close()
    image_bytes = None
    if req.image_base64:
        if not req.image_mime_type:
            raise HTTPException(status_code=422, detail="Thiếu loại ảnh")
        try:
            image_bytes = base64.b64decode(req.image_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=422, detail="Ảnh gửi lên không hợp lệ") from exc
        if len(image_bytes) > 5 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Ảnh tối đa 5 MB")
    elif req.image_mime_type:
        raise HTTPException(status_code=422, detail="Thiếu dữ liệu ảnh")
    return await answer_query(req.workspace_id, req.query, req.model, req.web_search, req.top_k,
                              [turn.model_dump() for turn in req.history],
                              image_base64=req.image_base64,
                              selected_document_id=req.selected_document_id)


class WebSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=5, ge=1, le=10)


@router.post("/search/web")
async def web_search(req: WebSearchRequest, user: dict = Depends(get_current_user)):
    return {"results": await search_web(req.query, req.limit)}
