from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from app.services.retrieval_service import search_relevant_chunks
from app.services.llm_service import generate_rag_answer, check_ollama_status

router = APIRouter(prefix="/api/v1", tags=["Chat & RAG"])

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.retrieval_service import retrieval_service
from app.services.reranker_service import reranker_service
from app.services.llm_service import llm_service

router = APIRouter()

class ChatRequest(BaseModel):
    message: str

@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        # 1. Hybrid Search + RRF
        retrieved_docs = retrieval_service.hybrid_search(query=request.message, top_k=10)
        
        # 2. Re-ranking với Cross-Encoder
        reranked_docs = reranker_service.rerank(query=request.message, documents=retrieved_docs, top_k=3)
        
        # 3. Tạo Context cho LLM
        context = "\n---\n".join([d["content"] for d in reranked_docs])
        prompt = f"Sử dụng ngữ cảnh sau để trả lời câu hỏi:\nContext:\n{context}\n\nQuestion: {request.message}"
        
        # 4. Gọi LLM sinh câu trả lời
        response = llm_service.generate_response(prompt)
        
        return {
            "response": response,
            "sources": reranked_docs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
