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

_SUMMARY_QUERY_PATTERN = re.compile(
    r"tóm\s*tắt|tổng\s*hợp|nội\s*dung\s*chính|overview|summari[sz]e|summary|"
    r"liệt\s*kê\s+(?:tất\s+cả|các)|có\s+những\s+gì|gồm\s+những\s+gì",
    re.IGNORECASE,
)


def _answer_token_limit(query: str, image_base64: Optional[str]) -> int:
    if image_base64:
        return 512
    # Summaries should finish promptly and avoid spending time generating an
    # unnecessarily long answer. Leave the normal limit for detailed questions.
    return 900 if _SUMMARY_QUERY_PATTERN.search(query or "") else 2048


def is_conversational_query(query: str) -> bool:
    """
    Phát hiện các câu chào hỏi, giao tiếp xã giao thông thường không cần tra cứu tài liệu.
    Dùng regex nguyên từ (\b) để không match nhầm 'thi', 'nghi', 'nhiều' khi gặp 'hi'.
    """
    q = query.lower().strip()
    words = q.split()
    if len(words) > 5:
        return False

    # Loại trừ nếu chứa các từ khóa học tập / tra cứu / câu hỏi nghiệp vụ
    study_keywords = [
        "thi", "đề", "bài", "chương", "lab", "tài liệu", "sách", "giáo trình",
        "là gì", "thế nào", "cách", "hướng dẫn", "bao nhiêu", "mấy", "tại sao", "ở đâu"
    ]
    if any(re.search(rf"\b{re.escape(k)}\b", q) for k in study_keywords):
        return False

    standalone_greetings = [
        r"chào", r"chào bạn", r"hello", r"hi", r"alo", r"xin chào",
        r"bạn là ai", r"bạn có thể làm gì", r"giới thiệu bản thân",
        r"giúp tôi được gì", r"cảm ơn", r"thank you", r"thanks",
        r"tạm biệt", r"bye", r"good morning", r"good afternoon"
    ]
    pattern = rf"^\s*(?:{'|'.join(standalone_greetings)})\s*[!?.~]*$"
    return bool(re.match(pattern, q, re.IGNORECASE))


async def check_ollama_status() -> Dict[str, Any]:
    """
    Kiểm tra dịch vụ Ollama cục bộ có đang hoạt động hay không
    """
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                raw_names = [m.get("name") for m in models]
                model_names = list(raw_names)
                for name in raw_names:
                    if name and ":" in name:
                        model_names.append(name.split(":")[0])
                return {
                    "running": True,
                    "available_models": list(dict.fromkeys(model_names)),
                    "message": f"Ollama đang chạy cục bộ với {len(raw_names)} model(s)."
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
        page_label = chunk.get("page_label") or (
            f"Trang {chunk['page_number']}" if chunk.get("page_number") is not None else ""
        )
        page_suffix = f" ({page_label})" if page_label else ""
        context_text += (
            f"\n--- [Tài liệu {ref_id}]: {chunk['document_name']}{page_suffix} ---\n"
            f"{chunk['content']}\n"
        )
        citations.append({
            "ref_id": ref_id,
            "source_type": "document",
            "document_id": chunk["document_id"],
            "document_name": chunk["document_name"],
            "page_number": chunk.get("page_number"),
            "page_label": page_label or None,
            "chunk_index": chunk.get("chunk_index"),
            "snippet": chunk["content"][:200] + "..." if len(chunk["content"]) > 200 else chunk["content"]
        })

    for source in (web_sources or []):
        ref_id = len(citations) + 1
        raw_title = (source.get("title") or "").strip()
        url = (source.get("url") or "").strip()
        domain = ""
        if url:
            try:
                from urllib.parse import urlparse
                domain = urlparse(url).netloc.replace("www.", "")
            except Exception:
                domain = ""
        
        # Tạo tiêu đề nguồn web rõ ràng, tránh generic "Web" hay "Nguồn Web"
        if not raw_title or raw_title.lower() in {"web", "nguồn web"}:
            clean_title = domain or "Trang web tham khảo"
        elif domain and domain.lower() not in raw_title.lower():
            clean_title = f"{raw_title} ({domain})"
        else:
            clean_title = raw_title

        context_text += f"\n--- [Nguồn web {ref_id}]: {clean_title} ---\n{source.get('snippet', '')}\n"
        citations.append({
            "ref_id": ref_id,
            "source_type": "web",
            "document_name": clean_title,
            "title": clean_title,
            "url": url,
            "snippet": source.get("snippet", "")
        })

    has_local = bool(context_chunks)
    has_web = bool(web_sources)

    system_prompt = (
        "Bạn là Trợ lý Tri thức Cá nhân AI (Personal Knowledge AI) — một chuyên gia phân tích và người bạn đồng hành nghiên cứu thông thái, "
        "chính xác, khách quan và sư phạm theo tiêu chuẩn NotebookLM.\n\n"
        "## NGUYÊN TẮC TRẢ LỜI CỐT LÕI:\n"
        "1. ĐỌC HIỂU SÂU SẮC & TOÀN DIỆN: Đọc toàn bộ các nguồn tham khảo (tài liệu hoặc web) được cung cấp. "
        "Tổng hợp logic mạch lạc, giải thích nguyên nhân, mục đích và bản chất vấn đề; tuyệt đối không sao chép máy móc hay cắt xén thông tin.\n"
        "2. ĐỐI CHIẾU NGUỒN VÀ TRÁNH ẢO GIÁC (RẤT QUAN TRỌNG):\n"
        "   - Chỉ trích dẫn [Tài liệu 1], [Tài liệu 2]... nếu nội dung trong tài liệu đó THỰC SỰ đề cập đến câu hỏi của người dùng.\n"
        "   - Khi tra cứu tài liệu cá nhân mà kho tài liệu HOÀN TOÀN KHÔNG CHỨA THÔNG TIN liên quan: "
        "     Nói rõ ngay: 'Tài liệu trong kho tri thức của bạn không chứa thông tin về [chủ đề].' "
        "     Sau đó bạn hãy giải đáp bằng kiến thức chuẩn xác của bạn (không gắn nhãn trích dẫn tài liệu) để hỗ trợ người dùng tốt nhất.\n"
        "3. TRÌNH BÀY HƯỚNG DẪN / BÀI LAB / CÁC BƯỚC THỰC HÀNH (ĐẶC BIỆT CHÚ Ý):\n"
        "   - Khi người dùng hỏi về nội dung, hướng dẫn, cách làm hoặc các bước của một bài/chương/lab (ví dụ: 'bài 1 làm về gì', 'cách làm bài 1', 'hướng dẫn thực hành...'):\n"
        "     + Bắt đầu bằng mục tiêu tổng quan của bài thực hành.\n"
        "     + BẮT BUỘC ĐÁNH SỐ LIÊN TỤC: Dùng 'Bước 1:', 'Bước 2:', 'Bước 3:'... tăng dần đến bước cuối cùng có trong tài liệu. Tuyệt đối KHÔNG bỏ qua các bước đầu hoặc chỉ dừng ở bước 3 hay bước 4.\n"
        "     + Mỗi bước cần nêu rõ: Thao tác cụ thể (click đâu, nhập lệnh gì, thiết lập thông số nào) và lưu ý kỹ thuật nếu có.\n"
        "     + CHỐNG LẶP LẠI (ANTI-REPETITION): Tuyệt đối không lặp lại nguyên văn cùng một đoạn mô tả thao tác ở nhiều mục khác nhau. Mỗi bước phải mô tả một hành động mới nối tiếp quy trình.\n"
        "4. KHI SỬ DỤNG NGUỒN INTERNET ([Nguồn web 1], [Nguồn web 2]...):\n"
        "   - VỚI CÂU HỎI THỜI TIẾT / NHIỆT ĐỘ: Trả lời trực tiếp các số liệu cụ thể từ nguồn: nhiệt độ (°C), độ ẩm (%), tình trạng trời, gió và dự báo; tuyệt đối không bảo người dùng tự truy cập trang web.\n"
        "   - VỚI CÂU HỎI CÁCH LÀM / CÔNG THỨC / KỸ THUẬT TỪ WEB (ví dụ: cách làm bánh, nấu ăn, lập trình...):\n"
        "     + Phải tổng hợp toàn bộ các nguồn web thành MỘT BÀI HƯỚNG DẪN HOÀN CHỈNH, DUY NHẤT: Bắt đầu từ Nguyên liệu/Chuẩn bị -> Các bước thực hiện chi tiết từ Bước 1 đến hết -> Lưu ý & Bí quyết thành công.\n"
        "     + TUYỆT ĐỐI KHÔNG chia câu trả lời thành các phần rời rạc theo từng nguồn như '[1]: ... rồi [2]: ...' hoặc lặp lại '(4): ...', '(5): ...' với nội dung vắn tắt trùng lặp!\n"
        "   - VỚI CÂU HỎI TRI THỨC / ĐỊNH LÝ / CÔNG THỨC (ví dụ: hằng đẳng thức, định lý toán học): Trình bày đầy đủ toàn bộ các công thức/định lý một cách chính xác và rõ ràng.\n"
        "5. CÂU HỎI TỔNG HỢP / TÓM TẮT TOÀN BỘ TÀI LIỆU: Liệt kê rõ ràng và đầy đủ từng bài/chương theo thứ tự trong tài liệu, mỗi mục kèm mô tả súc tích về mục tiêu và nội dung chính.\n"
        "6. ĐỊNH DẠNG & TRÍCH DẪN:\n"
        "   - Trả lời bằng tiếng Việt tự nhiên, chuẩn mực, định dạng Markdown rõ ràng (tiêu đề, danh sách, in đậm, bảng biểu nếu cần so sánh).\n"
        "   - Công thức toán/khoa học hiển thị bằng KaTeX chuẩn: inline `$x$` hoặc display `$$x$$`.\n"
        "   - Gắn nhãn trích dẫn [1], [2]... hoặc [Tài liệu 1], [Nguồn web 1]... ngay sau các ý có thông tin từ nguồn tương ứng.\n"
        "7. NỐI TIẾP HỘI THOẠI: Sử dụng lịch sử hội thoại để hiểu câu hỏi nối tiếp (ví dụ: 'các bước tiếp theo', 'chi tiết hơn', 'giải thích thêm').\n"
        "8. GỢI Ý CÂU HỎI TIẾP THEO (CHUẨN NOTEBOOKLM):\n"
        "   - Ở CUỐI CÙNG của câu trả lời, hãy LUÔN LUÔN tạo đúng 3 gợi ý câu hỏi tiếp theo sâu sắc, kích thích tìm hiểu hoặc thực hành dựa trên nội dung vừa trả lời.\n"
        "   - Định dạng bắt buộc ở cuối câu trả lời:\n"
        "---GỢI Ý TIẾP THEO---\n"
        "- [Gợi ý câu hỏi hoặc bước đào sâu 1]\n"
        "- [Gợi ý câu hỏi hoặc bước đào sâu 2]\n"
        "- [Gợi ý câu hỏi hoặc bước đào sâu 3]\n"
    )

    if not has_local and not has_web:
        user_prompt = (
            f"Câu hỏi của người dùng: {query}\n\n"
            "LƯU Ý ĐẶC BIỆT: Tài liệu trong kho tri thức của người dùng KHÔNG chứa thông tin về câu hỏi này.\n"
            "1. Hãy thông báo rõ ràng cho người dùng biết điều đó (ví dụ: 'Tài liệu trong kho tri thức của bạn không chứa thông tin về...').\n"
            "2. Sau đó, giải đáp câu hỏi của người dùng bằng kiến thức chuẩn xác, đầy đủ của bạn.\n"
            "3. TUYỆT ĐỐI KHÔNG gắn bất kỳ nhãn trích dẫn tài liệu nào như [1], [2], [Tài liệu 1].\n"
            "4. Kết thúc câu trả lời bằng 3 câu hỏi gợi ý tiếp theo dưới nhãn ---GỢI Ý TIẾP THEO---:"
        )
    elif has_web and not has_local:
        user_prompt = (
            f"Dưới đây là các kết quả tìm kiếm trên Internet:\n{context_text}\n"
            f"\nCâu hỏi/Yêu cầu của người dùng: {query}\n"
            "\nHãy tổng hợp các nguồn trên thành một bài giải đáp/hướng dẫn hoàn chỉnh, chi tiết từng bước, có chiều sâu (tuyệt đối KHÔNG tóm tắt riêng rẽ từng nguồn), gắn nhãn trích dẫn [1], [2] tương ứng, và kết thúc bằng 3 câu hỏi gợi ý tiếp theo dưới nhãn ---GỢI Ý TIẾP THEO---:"
        )
    elif has_local and not has_web:
        user_prompt = (
            f"Dưới đây là các tài liệu trong kho tri thức của người dùng:\n{context_text}\n"
            f"\nCâu hỏi/Yêu cầu của người dùng: {query}\n"
            "\nHãy kiểm tra độ phù hợp của tài liệu và trả lời đầy đủ, chi tiết từng bước (nếu là bài thực hành/lab), gắn nhãn trích dẫn [1], [2]..., và kết thúc bằng 3 câu hỏi gợi ý tiếp theo dưới nhãn ---GỢI Ý TIẾP THEO---:"
        )
    else:
        user_prompt = (
            f"Dưới đây là các nguồn tham khảo (tài liệu cá nhân và web):\n{context_text}\n"
            f"\nCâu hỏi/Yêu cầu của người dùng: {query}\n"
            "\nHãy trả lời trực tiếp, đầy đủ từng bước, gắn nhãn trích dẫn tương ứng [1], [2]..., và kết thúc bằng 3 câu hỏi gợi ý tiếp theo dưới nhãn ---GỢI Ý TIẾP THEO---:"
        )
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
    history_messages = []
    for turn in (history or [])[-8:]:
        if turn.get("role") in {"user", "assistant"} and turn.get("content"):
            content = turn["content"]
            if "---GỢI Ý TIẾP THEO---" in content:
                content = content.split("---GỢI Ý TIẾP THEO---")[0].rstrip()
            history_messages.append({"role": turn["role"], "content": content[:2000]})

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
                timeout = httpx.Timeout(connect=15.0, read=OLLAMA_TIMEOUT, write=60.0, pool=60.0)
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
                    "options": {
                        "num_predict": _answer_token_limit(query, image_base64),
                        "temperature": 0.50,
                        "top_p": 0.9,
                        "repeat_penalty": 1.15,
                        "num_ctx": 4096,
                    },
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

    history_messages = []
    for turn in (history or [])[-8:]:
        if turn.get("role") in {"user", "assistant"} and turn.get("content"):
            content = turn["content"]
            if "---GỢI Ý TIẾP THEO---" in content:
                content = content.split("---GỢI Ý TIẾP THEO---")[0].rstrip()
            history_messages.append({"role": turn["role"], "content": content[:2000]})

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
                timeout = httpx.Timeout(connect=15.0, read=OLLAMA_TIMEOUT, write=60.0, pool=60.0)
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
            timeout = httpx.Timeout(connect=15.0, read=OLLAMA_TIMEOUT, write=60.0, pool=60.0)
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
                    "options": {
                        "num_predict": _answer_token_limit(query, image_base64),
                        "temperature": 0.50,
                        "top_p": 0.9,
                        "repeat_penalty": 1.15,
                        "num_ctx": 4096,
                    },
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


def resolve_available_chat_model(
    requested_model: str,
    available_models: List[str],
) -> Optional[str]:
    """Chọn model chat khả dụng trong Ollama (ưu tiên model được yêu cầu)."""
    if not available_models:
        return None
    if requested_model and requested_model in available_models:
        return requested_model

    tagged = [m for m in available_models if ":" in m and "embed" not in m.lower()]
    text_only = [m for m in tagged if "-vl" not in m.lower() and "vl:" not in m.lower()]
    if text_only:
        return text_only[0]
    if tagged:
        return tagged[0]
    non_embed = [m for m in available_models if "embed" not in m.lower()]
    return non_embed[0] if non_embed else None


def parse_json_response(raw: str) -> Any:
    """Bóc tách JSON từ phản hồi LLM, kể cả khi bị bọc bởi markdown code fence."""
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    if not text:
        raise ValueError("Phản hồi AI rỗng")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        starts = [idx for idx in (text.find("{"), text.find("[")) if idx != -1]
        if not starts:
            raise
        start = min(starts)
        end = max(text.rfind("}"), text.rfind("]"))
        if end <= start:
            raise
        return json.loads(text[start : end + 1])


async def call_ollama_json(
    system_prompt: str,
    user_prompt: str,
    model: str = DEFAULT_LLM_MODEL,
    num_predict: int = 256,
    num_ctx: int = 4096,
    temperature: float = 0.35,
    timeout_sec: float = 45.0,
) -> Dict[str, Any]:
    """Gọi Ollama /api/chat ở chế độ JSON và trả về dict kết quả có kiểm soát lỗi."""
    ollama_status = await check_ollama_status()
    if not ollama_status["running"]:
        return {"ok": False, "error": "ollama_offline", "data": None, "model_used": None}

    chosen_model = resolve_available_chat_model(model, ollama_status["available_models"])
    if not chosen_model:
        return {"ok": False, "error": "model_unavailable", "data": None, "model_used": None}

    payload: Dict[str, Any] = {
        "model": chosen_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "format": "json",
        "keep_alive": "30m",
        "options": {
            "temperature": temperature,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
            "num_predict": num_predict,
            "num_ctx": num_ctx,
        },
    }

    try:
        timeout = httpx.Timeout(timeout_sec, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
            resp.raise_for_status()
            raw_content = resp.json().get("message", {}).get("content", "").strip()
            parsed = parse_json_response(raw_content)
            return {"ok": True, "data": parsed, "model_used": chosen_model, "error": None}
    except Exception as exc:
        logger.warning("Ollama JSON call failed (%s): %s", chosen_model, exc)
        return {"ok": False, "error": str(exc), "data": None, "model_used": chosen_model}
