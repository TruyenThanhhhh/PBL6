import httpx
import re
from typing import List, Dict, Any, Optional
from app.config import OLLAMA_BASE_URL, DEFAULT_LLM_MODEL

def is_conversational_query(query: str) -> bool:
    """
    Phát hiện các câu chào hỏi, giao tiếp xã giao thông thường không cần tra cứu tài liệu
    """
    q = query.lower().strip()
    greetings = [
        "chào", "hello", "hi", "alo", "xin chào", "bạn là ai", "bạn có thể làm gì",
        "giới thiệu bản thân", "giúp tôi được gì", "cảm ơn", "thank you", "tạm biệt", "bye"
    ]
    if len(q.split()) <= 4:
        for g in greetings:
            if g in q:
                return True
    return False

async def check_ollama_status() -> Dict[str, Any]:
    """
    Kiểm tra dịch vụ Ollama cục bộ có đang hoạt động hay không
    """
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                model_names = [m.get("name") for m in models]
                return {
                    "running": True,
                    "available_models": model_names,
                    "message": f"Ollama đang chạy cục bộ với {len(model_names)} model(s)."
                }
    except Exception:
        pass
        
    return {
        "running": False,
        "available_models": [],
        "message": "Ollama chưa được bật trên máy (cần cài đặt hoặc gõ `ollama serve`)."
    }

async def generate_rag_answer(
    query: str,
    context_chunks: List[Dict[str, Any]],
    model_name: str = DEFAULT_LLM_MODEL
) -> Dict[str, Any]:
    """
    Tạo câu trả lời thông minh: trò chuyện tự nhiên, tổng hợp ý nghĩa sâu sắc, kèm trích dẫn
    """
    ollama_status = await check_ollama_status()
    
    # 1. Nếu là câu chào hỏi, trò chuyện thông thường -> Trả lời thân thiện tự nhiên
    if is_conversational_query(query):
        chitchat_prompt = (
            "Bạn là Personal AI Knowledge Assistant - Trợ lý tri thức cá nhân thông minh, thân thiện và am hiểu sâu sắc. "
            "Hãy chào hỏi và trò chuyện với người dùng một cách ấm áp, tự nhiên bằng tiếng Việt. "
            "Giới thiệu ngắn gọn rằng bạn có thể giúp người dùng đọc hiểu tài liệu, tổng hợp ý nghĩa, giải thích kiến thức "
            "và tạo các công cụ học tập như quiz, tóm tắt."
        )
        if ollama_status["running"]:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json={
                        "model": model_name,
                        "messages": [
                            {"role": "system", "content": chitchat_prompt},
                            {"role": "user", "content": query}
                        ],
                        "stream": False
                    })
                    if resp.status_code == 200:
                        ans = resp.json().get("message", {}).get("content", "")
                        return {
                            "answer": ans,
                            "citations": [],
                            "model_used": model_name,
                            "engine": "conversational_llm"
                        }
            except Exception as e:
                print(f"Lỗi chat xã giao: {e}")

    # 2. Xây dựng Context và Citations
    context_text = ""
    citations = []
    
    for i, chunk in enumerate(context_chunks):
        ref_id = i + 1
        context_text += f"\n--- [Tài liệu {ref_id}]: {chunk['document_name']} (Trang {chunk['page_number']}) ---\n{chunk['content']}\n"
        citations.append({
            "ref_id": ref_id,
            "document_id": chunk["document_id"],
            "document_name": chunk["document_name"],
            "page_number": chunk["page_number"],
            "chunk_index": chunk["chunk_index"],
            "snippet": chunk["content"][:200] + "..." if len(chunk["content"]) > 200 else chunk["content"]
        })

    # 3. System Prompt NÂNG CAO: Vừa tổng hợp ý nghĩa, vừa đàm thoại mượt mà, vừa trích dẫn chính xác
    system_prompt = (
        "Bạn là Trợ lý Tri thức Cá nhân AI (Personal AI Knowledge Platform). "
        "Người dùng đang tham khảo các tài liệu trong kho tri thức của họ.\n\n"
        "HƯỚNG DẪN TRẢ LỜI QUAN TRỌNG:\n"
        "1. KHÔNG chỉ chép lại các câu chữ nguyên văn một cách máy móc. Hãy ĐỌC HIỂU BẢN CHẤT, "
        "PHÂN TÍCH, TỔNG HỢP và LIÊN KẾT CÁC Ý NGHĨA lại với nhau để đưa ra câu trả lời toàn diện, sâu sắc và dễ hiểu nhất.\n"
        "2. Giải thích rõ ràng nguyên nhân, mục đích và ý nghĩa đằng sau các nội dung được đề cập.\n"
        "3. Sử dụng giọng điệu tự nhiên, lịch sự, đóng vai trò như một người bạn đồng hành nghiên cứu thông thái.\n"
        "4. Cuối các ý quan trọng bắt nguồn từ tài liệu, hãy gắn thẻ trích dẫn [Tài liệu X] (ví dụ: [Tài liệu 1]) để người dùng có thể kiểm chứng nguồn gốc.\n"
        "5. Nếu tài liệu chưa đề cập đủ, bạn có thể phân tích thêm dựa trên kiến thức logic tổng quát nhưng cần nêu rõ đó là phần phân tích mở rộng."
    )
    
    user_prompt = f"Dưới đây là các đoạn thông tin tham khảo từ tài liệu của tôi:\n{context_text}\n\nCâu hỏi/Yêu cầu của tôi: {query}\n\nHãy tổng hợp và trả lời chi tiết:"

    if ollama_status["running"]:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "stream": False
                }
                resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
                if resp.status_code == 200:
                    answer = resp.json().get("message", {}).get("content", "")
                    return {
                        "answer": answer,
                        "citations": citations,
                        "model_used": model_name,
                        "engine": "ollama_local"
                    }
        except Exception as e:
            print(f"Lỗi khi gọi Ollama API: {e}")

    # Fallback nếu Ollama lỗi
    fallback_answer = (
        f"Pipeline đã tìm thấy **{len(context_chunks)} đoạn bằng chứng liên quan** trong tài liệu của bạn.\n\n"
    )
    for c in citations:
        fallback_answer += f"- **[{c['document_name']} - Trang {c['page_number']}]:** {c['snippet']}\n"
        
    return {
        "answer": fallback_answer,
        "citations": citations,
        "model_used": "direct_context_extractor",
        "engine": "fallback_pipeline"
    }
