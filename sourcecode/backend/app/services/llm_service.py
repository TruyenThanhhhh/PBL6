import json
import httpx
import re
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator
from app.config import (
    OLLAMA_BASE_URL,
    DEFAULT_LLM_MODEL,
    OLLAMA_TIMEOUT,
    VISION_MODEL,
    VISION_MODEL_FALLBACK,
)

logger = logging.getLogger(__name__)


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


def _prepare_rag_prompts_and_citations(
    query: str,
    context_chunks: List[Dict[str, Any]],
    web_sources: Optional[List[Dict[str, Any]]] = None,
    image_base64: Optional[str] = None,
) -> tuple[str, str, List[Dict[str, Any]]]:
    context_text = ""
    citations: List[Dict[str, Any]] = []

    for i, chunk in enumerate(context_chunks):
        ref_id = i + 1
        context_text += (
            f"\n--- [Tài liệu {ref_id}]: {chunk['document_name']} (Trang {chunk['page_number']}) ---\n"
            f"{chunk['content']}\n"
        )
        citations.append({
            "ref_id": ref_id,
            "source_type": "document",
            "document_id": chunk["document_id"],
            "document_name": chunk["document_name"],
            "page_number": chunk["page_number"],
            "chunk_index": chunk["chunk_index"],
            "snippet": chunk["content"][:200] + "..." if len(chunk["content"]) > 200 else chunk["content"]
        })

    for source in (web_sources or []):
        ref_id = len(citations) + 1
        context_text += f"\n--- [Nguồn web {ref_id}]: {source.get('title', 'Web')} ---\n{source.get('snippet', '')}\n"
        citations.append({
            "ref_id": ref_id,
            "source_type": "web",
            "title": source.get("title"),
            "url": source.get("url"),
            "snippet": source.get("snippet", "")
        })

    system_prompt = (
        "Bạn là Trợ lý Tri thức Cá nhân AI (Personal AI Knowledge Platform). "
        "Người dùng đang tham khảo các tài liệu trong kho tri thức của họ.\n\n"
        "HƯỚNG DẪN TRẢ LỜI QUAN TRỌNG:\n"
        "1. KHÔNG chỉ chép lại các câu chữ nguyên văn một cách máy móc. Hãy ĐỌC HIỂU BẢN CHẤT, "
        "PHÂN TÍCH, TỔNG HỢP và LIÊN KẾT CÁC Ý NGHĨA lại với nhau để đưa ra câu trả lời toàn diện, sâu sắc và dễ hiểu nhất.\n"
        "2. Giải thích rõ ràng nguyên nhân, mục đích và ý nghĩa đằng sau các nội dung được đề cập.\n"
        "3. Sử dụng giọng điệu tự nhiên, lịch sự, đóng vai trò như một người bạn đồng hành nghiên cứu thông thái.\n"
        "4. Trả lời trực tiếp, súc tích bằng tiếng Việt, thường 2-6 câu hoặc gạch đầu dòng khi cần; không chép lại nguyên văn các đoạn tham khảo.\n"
        "5. Gắn nhãn trích dẫn vào ngay cuối ý được hỗ trợ, ví dụ [Tài liệu 1] hoặc [Web 2].\n"
        "6. Chỉ dùng nguồn được cung cấp làm căn cứ; nếu không đủ bằng chứng, nói rõ điều gì còn thiếu.\n"
        "7. Dùng lịch sử hội thoại để hiểu câu hỏi nối tiếp và giữ các yêu cầu còn hiệu lực của người dùng. "
        "Nếu yêu cầu trước đó và yêu cầu mới mâu thuẫn, ưu tiên yêu cầu mới nhất.\n"
        "8. Nếu người dùng gửi kèm ảnh, hãy trực tiếp đọc chữ, mô tả biểu đồ/giao diện hoặc phân tích nội dung nhìn thấy trong ảnh. "
        "Ảnh đính kèm đã được cung cấp; tuyệt đối không yêu cầu người dùng gửi lại ảnh."
    )

    user_prompt = f"Dưới đây là các nguồn tham khảo:\n{context_text}\n\nCâu hỏi/Yêu cầu của tôi: {query}\n\nHãy trả lời và gắn nhãn trích dẫn tương ứng:"
    if image_base64:
        user_prompt += (
            "\n\nẢnh được gửi kèm trực tiếp trong tin nhắn này. Hãy quan sát ảnh, đọc các tiêu đề/chữ/số "
            "quan trọng và trả lời đúng trọng tâm câu hỏi; không nói rằng ảnh chưa được gửi."
        )

    return system_prompt, user_prompt, citations


async def generate_rag_answer(
    query: str,
    context_chunks: List[Dict[str, Any]],
    model_name: str = DEFAULT_LLM_MODEL,
    web_sources: Optional[List[Dict[str, Any]]] = None,
    history: Optional[List[Dict[str, str]]] = None,
    image_base64: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Tạo câu trả lời thông minh đồng bộ: trò chuyện tự nhiên, tổng hợp ý nghĩa sâu sắc, kèm trích dẫn
    """
    ollama_status = await check_ollama_status()
    model_available = model_name in ollama_status["available_models"]
    if image_base64 and ollama_status["running"] and not model_available:
        for candidate in (VISION_MODEL_FALLBACK, "qwen2.5vl:3b"):
            if candidate in ollama_status["available_models"]:
                model_name = candidate
                model_available = True
                break
    history_messages = [
        {"role": turn["role"], "content": turn["content"][:3000]}
        for turn in (history or [])[-8:]
        if turn.get("role") in {"user", "assistant"} and turn.get("content")
    ]

    # 1. Chitchat
    if is_conversational_query(query) and not image_base64:
        chitchat_prompt = (
            "Bạn là Personal AI Knowledge Assistant - Trợ lý tri thức cá nhân thông minh, thân thiện và am hiểu sâu sắc. "
            "Hãy chào hỏi và trò chuyện với người dùng một cách ấm áp, tự nhiên bằng tiếng Việt. "
            "Giới thiệu ngắn gọn rằng bạn có thể giúp người dùng đọc hiểu tài liệu, tổng hợp ý nghĩa, giải thích kiến thức "
            "và tạo các công cụ học tập như quiz, tóm tắt."
        )
        if ollama_status["running"] and model_available:
            try:
                timeout = httpx.Timeout(OLLAMA_TIMEOUT, connect=10.0)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json={
                        "model": model_name,
                        "messages": [
                            {"role": "system", "content": chitchat_prompt},
                            *history_messages,
                            {"role": "user", "content": query}
                        ],
                        "stream": False,
                        "keep_alive": "30m",
                        "options": {"num_predict": 256}
                    })
                    if resp.status_code == 200:
                        ans = resp.json().get("message", {}).get("content", "")
                        return {
                            "answer": ans,
                            "citations": [],
                            "model_used": model_name,
                            "engine": "conversational_llm"
                        }
            except Exception:
                logger.exception("Conversational Ollama request failed")
        reason = "ollama_unavailable" if model_available else ("model_unavailable" if ollama_status["running"] else "ollama_offline")
        readiness = ("Ollama chưa có model sẵn sàng" if ollama_status["running"] and not model_available
                     else "Ollama hiện chưa sẵn sàng")
        return {
            "answer": f"Chào bạn! Mình là trợ lý tri thức cá nhân. Bạn có thể tải tài liệu lên, rồi hỏi mình về nội dung trong đó. {readiness} để tạo câu trả lời AI.",
            "citations": [],
            "model_used": "conversation_fallback",
            "engine": "fallback_pipeline",
            "fallback_reason": reason,
        }

    # 2. RAG Prompt & Citations
    system_prompt, user_prompt, citations = _prepare_rag_prompts_and_citations(
        query, context_chunks, web_sources, image_base64
    )

    if image_base64 and not model_available:
        missing_model_message = (
            "Ollama hiện chưa chạy. Hãy khởi động Ollama rồi gửi lại ảnh."
            if not ollama_status["running"]
            else f"Đã nhận ảnh, nhưng chưa cài model vision. Hãy chạy `ollama pull {VISION_MODEL}` rồi gửi lại ảnh."
        )
        return {
            "answer": missing_model_message,
            "citations": citations,
            "model_used": "none",
            "engine": "fallback_pipeline",
            "fallback_reason": "vision_model_unavailable",
        }

    if ollama_status["running"] and model_available:
        try:
            timeout = httpx.Timeout(180.0 if image_base64 else OLLAMA_TIMEOUT, connect=10.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                user_message: Dict[str, Any] = {"role": "user", "content": user_prompt}
                if image_base64:
                    user_message["images"] = [image_base64]
                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        *history_messages,
                        user_message
                    ],
                    "stream": False,
                    "keep_alive": "30m",
                    "options": {"num_predict": 384 if image_base64 else 512},
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
        except Exception:
            logger.exception("Ollama generation failed")

    # Fallback response
    if citations:
        if not ollama_status["running"]:
            reason = "Ollama hiện chưa chạy"
            fallback_reason = "ollama_offline"
        elif not model_available:
            reason = f"Model Ollama `{model_name}` chưa được cài"
            fallback_reason = "model_unavailable"
        else:
            reason = "Ollama hiện không phản hồi"
            fallback_reason = "ollama_unavailable"
        fallback_answer = (
            f"Mình tìm thấy **{len(context_chunks)} đoạn tài liệu liên quan**. "
            f"{reason}, nên mình chưa thể tổng hợp nội dung thành câu trả lời AI.\n\n"
            "Bạn có thể mở từng trích dẫn để xem đoạn gốc:"
        )
    else:
        fallback_answer = "Mình chưa tìm thấy đoạn tài liệu phù hợp. Hãy thử diễn đạt câu hỏi khác hoặc tải tài liệu vào kho tri thức."
        fallback_reason = "no_sources"

    return {
        "answer": fallback_answer,
        "citations": citations,
        "model_used": "direct_context_extractor",
        "engine": "fallback_pipeline",
        "fallback_reason": fallback_reason,
    }


async def stream_rag_answer(
    query: str,
    context_chunks: List[Dict[str, Any]],
    model_name: str = DEFAULT_LLM_MODEL,
    web_sources: Optional[List[Dict[str, Any]]] = None,
    history: Optional[List[Dict[str, str]]] = None,
    image_base64: Optional[str] = None,
    collector: Optional[Dict[str, Any]] = None,
) -> AsyncGenerator[str, None]:
    """
    Sinh câu trả lời RAG dạng luồng (Server-Sent Events) theo thời gian thực từ Ollama cục bộ.
    """
    ollama_status = await check_ollama_status()
    model_available = model_name in ollama_status["available_models"]
    if image_base64 and ollama_status["running"] and not model_available:
        for candidate in (VISION_MODEL_FALLBACK, "qwen2.5vl:3b"):
            if candidate in ollama_status["available_models"]:
                model_name = candidate
                model_available = True
                break

    history_messages = [
        {"role": turn["role"], "content": turn["content"][:3000]}
        for turn in (history or [])[-8:]
        if turn.get("role") in {"user", "assistant"} and turn.get("content")
    ]

    # 1. Chitchat stream
    if is_conversational_query(query) and not image_base64:
        chitchat_prompt = (
            "Bạn là Personal AI Knowledge Assistant - Trợ lý tri thức cá nhân thông minh, thân thiện và am hiểu sâu sắc. "
            "Hãy chào hỏi và trò chuyện với người dùng một cách ấm áp, tự nhiên bằng tiếng Việt. "
            "Giới thiệu ngắn gọn rằng bạn có thể giúp người dùng đọc hiểu tài liệu, tổng hợp ý nghĩa, giải thích kiến thức "
            "và tạo các công cụ học tập như quiz, tóm tắt."
        )
        if ollama_status["running"] and model_available:
            meta = {
                "citations": [],
                "model_used": model_name,
                "engine": "conversational_llm",
            }
            yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"
            full_text = ""
            try:
                timeout = httpx.Timeout(OLLAMA_TIMEOUT, connect=10.0)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    async with client.stream(
                        "POST",
                        f"{OLLAMA_BASE_URL}/api/chat",
                        json={
                            "model": model_name,
                            "messages": [
                                {"role": "system", "content": chitchat_prompt},
                                *history_messages,
                                {"role": "user", "content": query},
                            ],
                            "stream": True,
                            "keep_alive": "30m",
                            "options": {"num_predict": 256},
                        },
                    ) as resp:
                        if resp.status_code == 200:
                            async for line in resp.aiter_lines():
                                if not line:
                                    continue
                                try:
                                    chunk_data = json.loads(line)
                                    delta = chunk_data.get("message", {}).get("content", "")
                                    if delta:
                                        full_text += delta
                                        yield f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"
                                except Exception:
                                    continue
                            if collector is not None:
                                collector["full_answer"] = full_text
                                collector["citations"] = []
                                collector["model_used"] = model_name
                                collector["engine"] = "conversational_llm"
                            yield f"data: {json.dumps({'answer': full_text, 'done': True}, ensure_ascii=False)}\n\n"
                            yield "data: [DONE]\n\n"
                            return
            except Exception:
                logger.exception("Stream chitchat failed")

        fallback_chitchat = (
            "Chào bạn! Mình là trợ lý tri thức cá nhân. Bạn có thể tải tài liệu lên, "
            "rồi hỏi mình về nội dung trong đó. Mình luôn sẵn sàng đồng hành cùng bạn!"
        )
        yield f"data: {json.dumps({'citations': [], 'model_used': 'conversation_fallback', 'engine': 'fallback_pipeline'}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'delta': fallback_chitchat}, ensure_ascii=False)}\n\n"
        if collector is not None:
            collector["full_answer"] = fallback_chitchat
            collector["citations"] = []
            collector["model_used"] = "conversation_fallback"
            collector["engine"] = "fallback_pipeline"
        yield f"data: {json.dumps({'answer': fallback_chitchat, 'done': True}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
        return

    # 2. RAG stream
    system_prompt, user_prompt, citations = _prepare_rag_prompts_and_citations(
        query, context_chunks, web_sources, image_base64
    )

    engine_name = "ollama_local" if (ollama_status["running"] and model_available) else "fallback_pipeline"
    initial_meta = {
        "citations": citations,
        "model_used": model_name if (ollama_status["running"] and model_available) else "direct_context_extractor",
        "engine": engine_name,
    }
    yield f"data: {json.dumps(initial_meta, ensure_ascii=False)}\n\n"

    if image_base64 and not model_available:
        missing_msg = (
            "Ollama hiện chưa chạy. Hãy khởi động Ollama rồi gửi lại ảnh."
            if not ollama_status["running"]
            else f"Đã nhận ảnh, nhưng chưa cài model vision. Hãy chạy `ollama pull {VISION_MODEL}` rồi gửi lại ảnh."
        )
        yield f"data: {json.dumps({'delta': missing_msg}, ensure_ascii=False)}\n\n"
        if collector is not None:
            collector["full_answer"] = missing_msg
            collector["citations"] = citations
            collector["model_used"] = "none"
            collector["engine"] = "fallback_pipeline"
        yield f"data: {json.dumps({'answer': missing_msg, 'done': True}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
        return

    full_answer = ""
    if ollama_status["running"] and model_available:
        try:
            timeout = httpx.Timeout(180.0 if image_base64 else OLLAMA_TIMEOUT, connect=10.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                user_message: Dict[str, Any] = {"role": "user", "content": user_prompt}
                if image_base64:
                    user_message["images"] = [image_base64]
                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        *history_messages,
                        user_message
                    ],
                    "stream": True,
                    "keep_alive": "30m",
                    "options": {"num_predict": 384 if image_base64 else 512},
                }
                async with client.stream("POST", f"{OLLAMA_BASE_URL}/api/chat", json=payload) as resp:
                    if resp.status_code == 200:
                        async for line in resp.aiter_lines():
                            if not line:
                                continue
                            try:
                                chunk_data = json.loads(line)
                                delta = chunk_data.get("message", {}).get("content", "")
                                if delta:
                                    full_answer += delta
                                    yield f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"
                            except Exception:
                                continue
                        if collector is not None:
                            collector["full_answer"] = full_answer
                            collector["citations"] = citations
                            collector["model_used"] = model_name
                            collector["engine"] = "ollama_local"
                        yield f"data: {json.dumps({'answer': full_answer, 'done': True}, ensure_ascii=False)}\n\n"
                        yield "data: [DONE]\n\n"
                        return
        except Exception:
            logger.exception("Stream RAG generation failed")

    # Fallback khi Ollama không khả dụng
    if citations:
        fallback_answer = (
            f"Mình tìm thấy **{len(context_chunks)} đoạn tài liệu liên quan**. "
            "Hiện tại Ollama đang bận hoặc chưa chạy, bạn có thể xem các trích dẫn tài liệu ở cột bên phải."
        )
    else:
        fallback_answer = "Mình chưa tìm thấy đoạn tài liệu phù hợp trong kho tri thức của bạn."

    yield f"data: {json.dumps({'delta': fallback_answer}, ensure_ascii=False)}\n\n"
    if collector is not None:
        collector["full_answer"] = fallback_answer
        collector["citations"] = citations
        collector["model_used"] = "direct_context_extractor"
        collector["engine"] = "fallback_pipeline"
    yield f"data: {json.dumps({'answer': fallback_answer, 'done': True}, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"
