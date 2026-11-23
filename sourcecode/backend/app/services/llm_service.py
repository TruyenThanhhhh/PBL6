import json
import httpx
import re
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator, Awaitable, Callable
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


_MAX_RAG_CONTEXT_TOKENS = 2200
_MAX_RAG_HISTORY_TOKENS = 550


def _resolve_llm_runtime_budget() -> tuple[int, int, int, int]:
    """Lấy ngân sách token & tham số Ollama theo hồ sơ phần cứng hiện hành."""
    try:
        from app.services.hardware_profile_service import get_active_profile_config

        cfg = get_active_profile_config()
        return (
            int(cfg.get("max_context_tokens") or _MAX_RAG_CONTEXT_TOKENS),
            int(cfg.get("max_history_tokens") or _MAX_RAG_HISTORY_TOKENS),
            int(cfg.get("num_ctx") or 4096),
            int(cfg.get("num_predict") or 2048),
        )
    except Exception:
        return _MAX_RAG_CONTEXT_TOKENS, _MAX_RAG_HISTORY_TOKENS, 4096, 2048


async def warmup_ollama_model(model_name: Optional[str] = None) -> bool:
    """Làm nóng model Ollama vào bộ nhớ (keep_alive=30m) bằng prompt rỗng để loại bỏ độ trễ lần hỏi đầu."""
    status = await check_ollama_status()
    if not status.get("running"):
        return False
    chosen = resolve_available_chat_model(
        model_name or DEFAULT_LLM_MODEL,
        status.get("available_models", []),
    )
    if not chosen:
        return False
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=5.0)) as client:
            resp = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={"model": chosen, "prompt": "", "stream": False, "keep_alive": "30m"},
            )
            return resp.status_code == 200
    except Exception:
        logger.debug("Ollama warm-up skipped/failed for %s", chosen)
        return False


def _estimate_tokens(text: str) -> int:
    """Ước lượng an toàn số token cho ngữ liệu pha trộn tiếng Việt / Nhật (CJK) / tiếng Anh."""
    if not text:
        return 0
    non_ascii = sum(1 for ch in text if ord(ch) > 127)
    ascii_cnt = len(text) - non_ascii
    return max(1, int(non_ascii * 0.9 + ascii_cnt * 0.32))


def _build_bounded_history_messages(
    history: Optional[List[Dict[str, str]]],
    max_turns: int = 4,
    max_tokens: Optional[int] = None,
) -> List[Dict[str, str]]:
    """Giữ lịch sử hội thoại cô đọng trong ngân sách token để không đẩy [Tài liệu 1] ra khỏi cửa sổ ngữ cảnh."""
    if max_tokens is None:
        _, max_tokens, _, _ = _resolve_llm_runtime_budget()
    selected: List[Dict[str, str]] = []
    used_tokens = 0
    for turn in reversed((history or [])[-max_turns:]):
        role = turn.get("role")
        raw_content = turn.get("content")
        if role not in {"user", "assistant"} or not raw_content:
            continue
        content = raw_content
        if "---GỢI Ý TIẾP THEO---" in content:
            content = content.split("---GỢI Ý TIẾP THEO---")[0].rstrip()
        cap = 220 if max_tokens <= 300 else (320 if role == "user" else 480)
        trimmed = content[:cap].strip()
        if not trimmed:
            continue
        toks = _estimate_tokens(trimmed)
        if selected and used_tokens + toks > max_tokens:
            break
        selected.append({"role": role, "content": trimmed})
        used_tokens += toks
    selected.reverse()
    return selected


_TABULAR_STOPWORDS = {
    "là", "gì", "của", "từ", "trong", "file", "tệp", "tài", "liệu", "nghĩa",
    "cho", "tôi", "biết", "xem", "hãy", "nêu", "giải", "thích", "và", "với",
}


def _extract_tabular_match_excerpt(query: str, body: str, max_len: int = 220) -> Optional[str]:
    """Khi chunk dạng bảng Excel ('|') chứa nhiều từ, trích nhanh vùng quanh từ khóa khớp để LLM & UI thấy ngay."""
    if body.count("|") < 6 or not query:
        return None
    cjk_terms = re.findall(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+", query)
    word_terms = [
        w for w in re.sub(r"[^\w\s]", " ", query, flags=re.UNICODE).split()
        if len(w) >= 3 and w.lower() not in _TABULAR_STOPWORDS
    ]
    terms = cjk_terms + word_terms
    if not terms:
        return None

    body_lower = body.lower()
    best_pos = -1
    for term in terms:
        pos = body_lower.find(term.lower())
        if pos != -1 and (best_pos == -1 or pos < best_pos):
            best_pos = pos
    if best_pos == -1:
        return None

    raw_start = max(0, best_pos - 60)
    if raw_start > 0:
        pipe_idx = body.find("|", raw_start, best_pos)
        nl_idx = body.find("\n", raw_start, best_pos)
        snapped = max(pipe_idx, nl_idx)
        start = snapped + 1 if snapped != -1 else raw_start
    else:
        start = 0

    end = min(len(body), start + max_len)
    if end < len(body):
        next_nl = body.find("\n", best_pos, end)
        if next_nl != -1:
            end = next_nl
        else:
            last_pipe = body.rfind("|", best_pos, end)
            if last_pipe > best_pos + 10:
                end = last_pipe

    excerpt = body[start:end].strip(" |\n")
    return excerpt or None


_LAB_STEPS_CUE_RE = re.compile(
    r"\b(?:bài|chương|lab|bước|thực\s*hành|cách\s*làm|hướng\s*dẫn|quy\s*trình|step)\b",
    re.IGNORECASE | re.UNICODE,
)
_GLOBAL_SUMMARY_CUE_RE = re.compile(
    r"\b(?:tóm\s*tắt|tổng\s*hợp|toàn\s*bộ|các\s*bài|các\s*chương|liệt\s*kê|overview|summary)\b",
    re.IGNORECASE | re.UNICODE,
)


def _build_dynamic_system_prompt(
    query: str,
    has_local: bool,
    has_web: bool,
    image_base64: Optional[str] = None,
) -> str:
    """Tạo system prompt gọn nhẹ theo ngữ cảnh (Dynamic Prompt Slimming) để giảm thời gian prefill."""
    sections: List[str] = [
        "Bạn là Trợ lý Tri thức Cá nhân AI (Personal Knowledge AI) — chuyên gia phân tích chính xác, khách quan và dễ hiểu.\n\n"
        "## NGUYÊN TẮC CỐT LÕI:\n"
        "1. ĐỌC HIỂU SÂU & TRUNG THỰC: Tổng hợp mạch lạc từ nguồn được cung cấp; chỉ gắn nhãn trích dẫn [1], [2]... nếu nguồn đó THỰC SỰ đề cập nội dung tương ứng.\n"
        "2. KHI KHO TÀI LIỆU KHÔNG CÓ THÔNG TIN: Nói rõ 'Tài liệu trong kho tri thức của bạn không chứa thông tin về [chủ đề].' rồi mới giải đáp bằng kiến thức chuẩn xác của bạn (tuyệt đối không gắn nhãn trích dẫn giả)."
    ]

    if has_local and _LAB_STEPS_CUE_RE.search(query or ""):
        sections.append(
            "3. TRÌNH BÀY HƯỚNG DẪN / BÀI THỰC HÀNH: Nêu mục tiêu ngắn gọn, đánh số liên tục 'Bước 1:', 'Bước 2:'... đủ quy trình, nêu rõ thao tác/lệnh cụ thể và tuyệt đối không lặp lại nội dung giữa các bước."
        )
    if _GLOBAL_SUMMARY_CUE_RE.search(query or ""):
        sections.append(
            "- TỔNG HỢP TOÀN TÀI LIỆU: Liệt kê rõ ràng theo thứ tự từng phần/bài/chương kèm mục tiêu và ý chính."
        )
    if has_web:
        sections.append(
            "4. KHI DÙNG NGUỒN INTERNET: Tổng hợp tất cả nguồn web thành MỘT câu trả lời thống nhất hoàn chỉnh (không tách vụn '[1]: ... [2]: ...'); nêu trực tiếp số liệu nếu hỏi thời tiết/tỷ giá/quy trình."
        )
    if image_base64:
        sections.append(
            "- KHI CÓ ẢNH ĐÍNH KÈM: Đọc kỹ chữ/số/chi tiết trong ảnh và trả lời trực diện vào trọng tâm câu hỏi."
        )

    sections.append(
        "5. ĐỊNH DẠNG & GỢI Ý TIẾP THEO:\n"
        "   - Trả lời bằng tiếng Việt rõ ràng (Markdown + công thức KaTeX `$x$` / `$$x$$`), hiểu ngữ cảnh lịch sử hội thoại.\n"
        "   - Cuối câu trả lời LUÔN tạo đúng 3 gợi ý câu hỏi tiếp theo theo định dạng:\n"
        "---GỢI Ý TIẾP THEO---\n"
        "- [Gợi ý 1]\n"
        "- [Gợi ý 2]\n"
        "- [Gợi ý 3]"
    )
    return "\n\n".join(sections)


def _prepare_rag_prompts_and_citations(
    query: str,
    context_chunks: List[Dict[str, Any]],
    web_sources: Optional[List[Dict[str, Any]]] = None,
    image_base64: Optional[str] = None,
    max_context_tokens: Optional[int] = None,
) -> tuple[str, str, List[Dict[str, Any]]]:
    if max_context_tokens is None:
        max_context_tokens, _, _, _ = _resolve_llm_runtime_budget()
    context_text = ""
    citations: List[Dict[str, Any]] = []
    used_tokens = 0

    for chunk in context_chunks:
        ref_id = len(citations) + 1
        page_label = chunk.get("page_label") or (
            f"Trang {chunk['page_number']}" if chunk.get("page_number") is not None else ""
        )
        ver_num = int(chunk.get("version_number") or 1)
        eff_date = chunk.get("effective_date")
        meta_parts: List[str] = []
        if ver_num > 1:
            meta_parts.append(f"Phiên bản v{ver_num}")
        if eff_date:
            meta_parts.append(f"Hiệu lực: {eff_date}")
        if page_label:
            meta_parts.append(page_label)
        page_suffix = f" ({' · '.join(meta_parts)})" if meta_parts else ""
        header = f"\n--- [Tài liệu {ref_id}]: {chunk['document_name']}{page_suffix} ---\n"
        raw_body = str(chunk.get("content", ""))
        focused_excerpt = _extract_tabular_match_excerpt(query, raw_body)
        body = (
            f"[Khớp trực tiếp]: {focused_excerpt}\n{raw_body}"
            if focused_excerpt
            else raw_body
        )
        block = f"{header}{body}\n"
        block_tokens = _estimate_tokens(block)

        if citations and used_tokens + block_tokens > max_context_tokens:
            break
        if not citations and block_tokens > max_context_tokens:
            # Đảm bảo Tài liệu 1 luôn nằm gọn trong cửa sổ ngữ cảnh
            max_chars = max(800, int(max_context_tokens * 1.4))
            body = body[:max_chars]
            block = f"{header}{body}\n"
            block_tokens = _estimate_tokens(block)

        context_text += block
        used_tokens += block_tokens
        snippet_src = focused_excerpt if focused_excerpt else raw_body
        citations.append({
            "ref_id": ref_id,
            "source_type": "document",
            "document_id": chunk["document_id"],
            "document_name": chunk["document_name"],
            "page_number": chunk.get("page_number"),
            "page_label": page_label or None,
            "chunk_index": chunk.get("chunk_index"),
            "snippet": snippet_src[:200] + "..." if len(snippet_src) > 200 else snippet_src,
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

        snippet_text = str(source.get("snippet", ""))
        block = f"\n--- [Nguồn web {ref_id}]: {clean_title} ---\n{snippet_text}\n"
        block_tokens = _estimate_tokens(block)
        if citations and used_tokens + block_tokens > max_context_tokens:
            break

        context_text += block
        used_tokens += block_tokens
        citations.append({
            "ref_id": ref_id,
            "source_type": "web",
            "document_name": clean_title,
            "title": clean_title,
            "url": url,
            "snippet": snippet_text,
        })

    has_local = any(c["source_type"] == "document" for c in citations)
    has_web = any(c["source_type"] == "web" for c in citations)

    system_prompt = _build_dynamic_system_prompt(query, has_local, has_web, image_base64)

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
            "\nHãy tổng hợp các nguồn trên thành một bài giải đáp/hướng dẫn hoàn chỉnh, gắn nhãn trích dẫn [1], [2] tương ứng và kết thúc bằng 3 câu hỏi gợi ý dưới nhãn ---GỢI Ý TIẾP THEO---:"
        )
    elif has_local and not has_web:
        user_prompt = (
            f"Dưới đây là các tài liệu trong kho tri thức của người dùng:\n{context_text}\n"
            f"\nCâu hỏi/Yêu cầu của người dùng: {query}\n"
            "\nHãy đối chiếu tài liệu và trả lời trực diện, đầy đủ, gắn nhãn trích dẫn [1], [2]... và kết thúc bằng 3 câu hỏi gợi ý dưới nhãn ---GỢI Ý TIẾP THEO---:"
        )
    else:
        user_prompt = (
            f"Dưới đây là các nguồn tham khảo (tài liệu cá nhân và web):\n{context_text}\n"
            f"\nCâu hỏi/Yêu cầu của người dùng: {query}\n"
            "\nHãy trả lời trực tiếp, đầy đủ, gắn nhãn trích dẫn tương ứng [1], [2]... và kết thúc bằng 3 câu hỏi gợi ý dưới nhãn ---GỢI Ý TIẾP THEO---:"
        )
    if image_base64:
        user_prompt += (
            "\n\nẢnh được gửi kèm trực tiếp trong tin nhắn này. Hãy quan sát ảnh, đọc các tiêu đề/chữ/số "
            "quan trọng và trả lời đúng trọng tâm câu hỏi; không nói rằng ảnh chưa được gửi."
        )

    return system_prompt, user_prompt, citations


VISION_MODEL_PREFIXES = (
    "qwen3-vl",
    "qwen2.5vl",
    "qwen2-vl",
    "llama3.2-vision",
    "minicpm-v",
    "llava",
    "moondream",
)


def is_vision_model_tag(model_name: str) -> bool:
    low = (model_name or "").strip().lower()
    if not low:
        return False
    return low in {VISION_MODEL.lower(), VISION_MODEL_FALLBACK.lower()} or any(
        low.startswith(prefix) for prefix in VISION_MODEL_PREFIXES
    )


def resolve_available_vision_model(
    requested_model: str,
    available_models: List[str],
) -> Optional[str]:
    """Chọn model Vision thực sự hỗ trợ hình ảnh trong danh sách Ollama hiện có."""
    if not available_models:
        return None
    if requested_model and is_vision_model_tag(requested_model) and requested_model in available_models:
        return requested_model
    for candidate in (VISION_MODEL, VISION_MODEL_FALLBACK, "qwen2.5vl:3b", "llama3.2-vision:11b"):
        if candidate in available_models:
            return candidate
    for installed in available_models:
        if is_vision_model_tag(str(installed)):
            return str(installed)
    return None


def _resolve_model_for_chat(
    requested_model: str,
    ollama_status: Dict[str, Any],
    image_base64: Optional[str],
) -> tuple[str, bool]:
    """Xác định model Ollama khả dụng (kể cả fallback vision hoặc chat model đã cài)."""
    available = ollama_status.get("available_models") or []
    if not ollama_status.get("running"):
        return requested_model, False
    if image_base64:
        vision_chosen = resolve_available_vision_model(requested_model, available)
        if vision_chosen:
            return vision_chosen, True
        return requested_model, False
    resolved = resolve_available_chat_model(requested_model, available)
    if resolved:
        return resolved, True
    return requested_model, False


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
    model_name, model_available = _resolve_model_for_chat(model_name, ollama_status, image_base64)
    _, _, num_ctx, max_predict = _resolve_llm_runtime_budget()
    history_messages = _build_bounded_history_messages(history)

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
                        "options": {"num_predict": 256, "num_ctx": min(num_ctx, 2048)},
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
                        "num_predict": 512 if image_base64 else max_predict,
                        "temperature": 0.50,
                        "top_p": 0.9,
                        "repeat_penalty": 1.15,
                        "num_ctx": num_ctx,
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


async def _stream_ollama_chat(
    payload: Dict[str, Any],
    citations: List[Dict[str, Any]],
    model_name: str,
    engine_name: str,
    collector: Optional[Dict[str, Any]] = None,
    is_disconnected: Optional[Callable[[], Awaitable[bool]]] = None,
) -> AsyncGenerator[str, None]:
    """Stream phản hồi từ Ollama /api/chat và ngắt ngay nếu client đóng kết nối."""
    full_answer = ""
    timeout = httpx.Timeout(connect=15.0, read=OLLAMA_TIMEOUT, write=60.0, pool=60.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", f"{OLLAMA_BASE_URL}/api/chat", json=payload) as resp:
            if resp.status_code != 200:
                raise RuntimeError(f"Ollama stream status {resp.status_code}")

            yield f"data: {json.dumps({'stage': 'generating', 'stage_label': 'AI đang viết câu trả lời...'}, ensure_ascii=False)}\n\n"
            async for line in resp.aiter_lines():
                if is_disconnected and await is_disconnected():
                    logger.info("Client disconnected during Ollama stream; cancelling generation")
                    if collector is not None and full_answer:
                        collector["full_answer"] = full_answer
                        collector["citations"] = citations
                        collector["model_used"] = model_name
                        collector["engine"] = engine_name
                    return
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
                collector["engine"] = engine_name
            yield f"data: {json.dumps({'answer': full_answer, 'done': True}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"


async def stream_rag_answer(
    query: str,
    context_chunks: List[Dict[str, Any]],
    model_name: str = DEFAULT_LLM_MODEL,
    web_sources: Optional[List[Dict[str, Any]]] = None,
    history: Optional[List[Dict[str, str]]] = None,
    image_base64: Optional[str] = None,
    collector: Optional[Dict[str, Any]] = None,
    is_disconnected: Optional[Callable[[], Awaitable[bool]]] = None,
) -> AsyncGenerator[str, None]:
    """
    Sinh câu trả lời RAG dạng luồng (Server-Sent Events) theo thời gian thực từ Ollama cục bộ.
    """
    ollama_status = await check_ollama_status()
    model_name, model_available = _resolve_model_for_chat(model_name, ollama_status, image_base64)
    _, _, num_ctx, max_predict = _resolve_llm_runtime_budget()
    history_messages = _build_bounded_history_messages(history)

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
                "stage": "generating",
                "stage_label": "Đang phản hồi...",
            }
            yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"
            try:
                async for sse_line in _stream_ollama_chat(
                    payload={
                        "model": model_name,
                        "messages": [
                            {"role": "system", "content": chitchat_prompt},
                            *history_messages,
                            {"role": "user", "content": query},
                        ],
                        "stream": True,
                        "keep_alive": "30m",
                        "options": {"num_predict": 256, "num_ctx": min(num_ctx, 2048)},
                    },
                    citations=[],
                    model_name=model_name,
                    engine_name="conversational_llm",
                    collector=collector,
                    is_disconnected=is_disconnected,
                ):
                    yield sse_line
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
    stage_label = (
        f"Đã tìm thấy {len(citations)} nguồn liên quan — Đang chuẩn bị câu trả lời..."
        if citations
        else "Đang phân tích và tạo câu trả lời..."
    )
    initial_meta = {
        "citations": citations,
        "model_used": model_name if (ollama_status["running"] and model_available) else "direct_context_extractor",
        "engine": engine_name,
        "stage": "found_sources" if citations else "preparing",
        "stage_label": stage_label,
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

    if ollama_status["running"] and model_available:
        try:
            user_message: Dict[str, Any] = {"role": "user", "content": user_prompt}
            if image_base64:
                user_message["images"] = [image_base64]
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    *history_messages,
                    user_message,
                ],
                "stream": True,
                "keep_alive": "30m",
                "options": {
                    "num_predict": 512 if image_base64 else max_predict,
                    "temperature": 0.50,
                    "top_p": 0.9,
                    "repeat_penalty": 1.15,
                    "num_ctx": num_ctx,
                },
            }
            async for sse_line in _stream_ollama_chat(
                payload=payload,
                citations=citations,
                model_name=model_name,
                engine_name="ollama_local",
                collector=collector,
                is_disconnected=is_disconnected,
            ):
                yield sse_line
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
