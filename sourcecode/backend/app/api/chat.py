from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.services.retrieval_service import search_relevant_chunks, retrieval_service
from app.services.reranker_service import reranker_service
from app.services.llm_service import generate_rag_answer, check_ollama_status

router = APIRouter(prefix="/api/v1", tags=["Chat & RAG"])

class ChatQueryRequest(BaseModel):
    workspace_id: str = "default"
    query: str
    model: Optional[str] = "qwen2.5:3b"

class LegacyChatRequest(BaseModel):
    message: str
    workspace_id: Optional[str] = "default"

@router.get("/status")
async def get_system_status():
    ollama_info = await check_ollama_status()
    return {
        "status": "online",
        "pipeline": "Hybrid RAG (BGE-M3 Dense + FTS5 BM25 + RRF + BGE-Reranker-v2)",
        "database": "SQLite Local + FTS5",
        "ollama": ollama_info
    }

@router.post("/chat/query")
async def query_knowledge_base(req: ChatQueryRequest):
    """
    Endpoint chuẩn cho Frontend Web UI:
    Thực hiện Hybrid RAG -> Reranking -> Citations & Grounded LLM Response
    """
    try:
        # 1. Truy xuất Hybrid (Dense + Sparse + RRF) và Rerank
        relevant_chunks = search_relevant_chunks(workspace_id=req.workspace_id, query=req.query)
        
        # 2. Sinh câu trả lời qua Local LLM kèm Citations
        result = await generate_rag_answer(req.query, relevant_chunks, req.model)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý câu hỏi: {str(e)}")

@router.post("/chat")
async def simple_chat_endpoint(request: LegacyChatRequest):
    """
    Endpoint đơn giản hóa tương thích cả dạng { message: '...' }
    """
    try:
        relevant_chunks = search_relevant_chunks(workspace_id=request.workspace_id or "default", query=request.message)
        result = await generate_rag_answer(request.message, relevant_chunks)
        return {
            "response": result.get("answer", ""),
            "sources": result.get("citations", []),
            "model_used": result.get("model_used", "")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
