from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from app.services.retrieval_service import search_relevant_chunks
from app.services.llm_service import generate_rag_answer, check_ollama_status

router = APIRouter(prefix="/api/v1", tags=["Chat & RAG"])

class ChatQueryRequest(BaseModel):
    workspace_id: str = "default"
    query: str
    model: Optional[str] = "qwen2.5:3b"

@router.get("/status")
async def get_system_status():
    ollama_info = await check_ollama_status()
    return {
        "status": "online",
        "database": "SQLite FTS5 Local",
        "ollama": ollama_info
    }

@router.post("/chat/query")
async def query_knowledge_base(req: ChatQueryRequest):
    # 1. Truy xuất các đoạn văn bản liên quan nhất từ CSDL cục bộ
    relevant_chunks = search_relevant_chunks(req.workspace_id, req.query)
    
    # 2. Sinh câu trả lời kèm bằng chứng trích dẫn (Citations)
    result = await generate_rag_answer(req.query, relevant_chunks, req.model)
    return result
