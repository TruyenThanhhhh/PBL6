import base64
import json
import httpx
import re
import logging
import unicodedata
from typing import List, Dict, Any, Optional, AsyncGenerator, Awaitable, Callable
from app.config import (
    OLLAMA_BASE_URL,
    DEFAULT_LLM_MODEL,
    OLLAMA_TIMEOUT,
    VISION_MODEL,
    VISION_MODEL_FALLBACK,
)
from app.services.hardware_profile_service import get_recommended_keep_alive

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
                json={"model": chosen, "prompt": "", "stream": False, "keep_alive": get_recommended_keep_alive()},
            )
            return resp.status_code == 200
    except Exception:
        logger.debug("Ollama warm-up skipped/failed for %s", chosen)
        return False


async def unload_ollama_models() -> List[str]:
    """Dỡ ngay các model đang giữ RAM/VRAM trong Ollama (`keep_alive: 0`)."""
    unloaded: List[str] = []
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(4.0, connect=1.5)) as client:
            ps_resp = await client.get(f"{OLLAMA_BASE_URL}/api/ps")
            if ps_resp.status_code != 200:
                return unloaded
            running_models = [
                str(m.get("name"))
                for m in ps_resp.json().get("models", [])
                if m.get("name")
            ]
            for model_name in running_models:
                try:
                    resp = await client.post(
                        f"{OLLAMA_BASE_URL}/api/generate",
                        json={"model": model_name, "prompt": "", "stream": False, "keep_alive": 0},
                    )
                    if resp.status_code == 200:
                        unloaded.append(model_name)
                except Exception:
                    pass
    except Exception:
        pass
    return unloaded


def _estimate_tokens(text: str) -> int:
    """Ước lượng an toàn số token cho ngữ liệu pha trộn tiếng Việt / Nhật (CJK) / tiếng Anh."""
    if not text:
        return 0
    non_ascii = sum(1 for ch in text if ord(ch) > 127)
    ascii_cnt = len(text) - non_ascii
    return max(1, int(non_ascii * 0.9 + ascii_cnt * 0.32))


_QUIZ_TEMPLATE_POLLUTION_RE = re.compile(
    r"(?:Câu\s*Hỏi\s*ÔN\s*TẬP|\*\*Câu\s*\d+\s*:\*\*|\*\*Đáp\s*Án\s*:\*\*|Đáp\s*Án\s*:)",
    re.IGNORECASE | re.UNICODE,
)


def _clean_history_turn_content(role: str, raw_content: str) -> str:
    """
    Làm sạch tin nhắn lịch sử trước khi đưa vào LLM:
    - Xóa dấu ':' hoặc '- [1]:' ở đầu câu hỏi khi người dùng bấm nút gợi ý cũ.
    - Xóa khuôn mẫu 'Câu Hỏi ÔN TẬP / Câu 1: / Đáp Án:' trong tin nhắn assistant cũ
      để model nhỏ 3B không bắt chước viết 'Câu Hỏi ÔN TẬP' cho các câu hỏi thông thường tiếp theo.
    - Xóa cụm 'Tài liệu [1] mô tả...' hoặc 'Tài liệu 2 mô tả...' để model không lặp lại văn phong máy móc.
    """
    content = (raw_content or "").strip()
    if "---GỢI Ý TIẾP THEO---" in content:
        content = content.split("---GỢI Ý TIẾP THEO---")[0].rstrip()
    if "GỢI Ý TIẾP THEO---" in content:
        content = content.split("GỢI Ý TIẾP THEO---")[0].rstrip()

    if role == "user":
        content = re.sub(r"^\s*(?:[-*•]?\s*(?:\[\d+\])?\s*[:.-]\s*)+", "", content).strip()
        if re.search(r"\b(?:câu\s*hỏi\s*ôn\s*tập|trắc\s*nghiệm|quiz|flashcard)\b", content, re.IGNORECASE):
            return ""
        return content

    # Nếu tin nhắn assistant trước đó là một bộ 'Câu Hỏi ÔN TẬP / Câu 1 / Đáp Án',
    # bỏ qua khỏi lịch sử chat để không làm nhiễm khuôn mẫu Q&A vào câu hỏi thông thường kế tiếp
    if _QUIZ_TEMPLATE_POLLUTION_RE.search(content):
        return ""

    content = re.sub(
        r"\b(?:Trong\s+)?[Tt]ài\s+liệu\s*\[?\d+\]?\s*(?:mô\s+tả|đề\s+cập|nhấn\s+mạnh)[^,.\n]{0,30}[,:]?\s*",
        "",
        content,
    )
    return content.strip()


def _build_bounded_history_messages(
    history: Optional[List[Dict[str, str]]],
    max_turns: int = 4,
    max_tokens: Optional[int] = None,
) -> List[Dict[str, str]]:
    """Giữ lịch sử hội thoại cô đọng, sạch khuôn mẫu nhiễu trong ngân sách token."""
    if max_tokens is None:
        _, max_tokens, _, _ = _resolve_llm_runtime_budget()
    selected: List[Dict[str, str]] = []
    used_tokens = 0
    for turn in reversed((history or [])[-max_turns:]):
        role = turn.get("role")
        raw_content = turn.get("content")
        if role not in {"user", "assistant"} or not raw_content:
            continue
        content = _clean_history_turn_content(role, raw_content)
        cap = 220 if max_tokens <= 300 else (360 if role == "user" else 480)
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


_EXHAUSTIVE_LIST_QUERY_RE = re.compile(
    r"(?:\b(?:cho\s+tôi|liệt\s+kê|nêu|hiển\s+thị|xem|lấy|tất\s+cả|toàn\s+bộ|đầy\s+đủ|"
    r"cho\s+toi|liet\s+ke|hien\s+thi|tat\s+ca|toan\s+bo|day\s+du)\b.{0,30}"
    r"(?:\b(\d{2,3})\s*(?:từ(?:\s*vựng)?|động\s*từ|danh\s*từ|tính\s*từ|phó\s*từ|mục|câu|dòng|tu(?:\s*vung)?|dong\s*tu|danh\s*tu|tinh\s*tu|muc|dong)\b"
    r"|\b(?:tất\s+cả|toàn\s+bộ|đầy\s+đủ|tat\s+ca|toan\s+bo|day\s+du)\s+(?:từ(?:\s*vựng)?|động\s*từ|danh\s*từ|tính\s*từ|danh\s*sách|tu(?:\s*vung)?|dong\s*tu|danh\s*tu|danh\s*sach)\b)"
    r"|\b(\d{2,3})\s+(?:từ(?:\s*vựng)?|động\s*từ|danh\s*từ|tính\s*từ|phó\s*từ|tu(?:\s*vung)?|dong\s*tu|danh\s*tu)\s+(?:bài|chương|phần|mục|bai|chuong|phan|muc)\s*\d+\b)",
    re.IGNORECASE | re.UNICODE,
)


def _try_build_exhaustive_tabular_list_answer(
    query: str,
    context_chunks: List[Dict[str, Any]],
) -> Optional[str]:
    """
    Khi người dùng yêu cầu liệt kê đầy đủ một danh sách lớn từ bảng (ví dụ: 'cho tôi 99 động từ bài 2',
    'liệt kê tất cả 120 từ vựng bài 1'), trích xuất trực tiếp 100% các dòng bảng từ tất cả các chunk
    đã tìm được trong < 1ms để:
    - Không bị thiếu dòng nào (LLM thường dừng ở dòng 15–20).
    - Không bao giờ bị model nhỏ 3B chép sai mặt chữ Kanji/Hiragana/Số liệu.
    """
    if not query or not context_chunks or not _EXHAUSTIVE_LIST_QUERY_RE.search(query):
        return None

    m_num = re.search(r"\b(\d{2,3})\s*(?:từ|động|danh|tính|phó|mục|dòng|tu|dong|muc)\b", query, re.IGNORECASE)
    requested_limit = int(m_num.group(1)) if m_num else 250

    header_cols: Optional[List[str]] = None
    data_rows: List[List[str]] = []
    seen_rows = set()
    section_title = ""

    for ch in context_chunks:
        for raw_line in str(ch.get("content") or "").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("[") or line.startswith("Sheet:") or line.startswith("Danh mục"):
                continue
            if "|" not in line:
                if not section_title and re.match(r"^(?:Bài|Chương|Phần|Mục)\s+\d+", line, re.IGNORECASE):
                    section_title = line
                continue
            cells = [c.strip() for c in line.strip("|").split("|") if c.strip()]
            if len(cells) < 2:
                continue
            if cells[0].upper() in ("STT", "NO", "NO.", "ID"):
                if header_cols is None:
                    header_cols = cells
                continue
            row_key = " | ".join(cells)
            if row_key not in seen_rows:
                seen_rows.add(row_key)
                data_rows.append(cells)

    if len(data_rows) < 12:
        return None

    selected_rows = data_rows[:max(requested_limit, len(data_rows))]
    cols = header_cols or [f"Cột {i+1}" for i in range(len(selected_rows[0]))]
    col_cnt = len(cols)

    title_line = f"**Danh sách đầy đủ {len(selected_rows)} mục" + (f" ({section_title})**" if section_title else " từ tài liệu:**")
    md_lines = [
        f"{title_line} [1]\n",
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join("---" for _ in cols) + " |",
    ]
    for r in selected_rows:
        padded = (r + [""] * col_cnt)[:col_cnt]
        md_lines.append("| " + " | ".join(padded) + " |")

    return "\n".join(md_lines)


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


_COMPARE_CUE_RE = re.compile(
    r"\b(?:so\s*sánh|khác\s*(?:nhau\s*)?gì|giống\s*và\s*khác|ưu\s*(?:và\s*)?nhược|đối\s*chiếu|compare|versus|vs)\b",
    re.IGNORECASE | re.UNICODE,
)
_FACTUAL_LOW_TEMP_RE = re.compile(
    r"\b(?:điều\s*\d+|khoản\s*\d+|mức\s*phạt|công\s*thức|tính|bao\s*nhiêu|giá|bảng|số\s*liệu|tỷ\s*lệ|lãi\s*suất|ngày\s*nào)\b",
    re.IGNORECASE | re.UNICODE,
)


def _deduplicate_chunk_overlap(prev_tail: str, current_text: str) -> str:
    """Cắt bỏ phần trùng lặp (CHUNK_OVERLAP) ở đầu chunk kế tiếp cùng tài liệu để tiết kiệm token ngữ cảnh."""
    if not prev_tail or not current_text:
        return current_text
    max_probe = min(len(prev_tail), len(current_text), 260)
    tail_slice = prev_tail[-max_probe:]
    for win in range(max_probe, 47, -1):
        prefix = current_text[:win]
        if tail_slice.endswith(prefix):
            trimmed = current_text[win:].lstrip(" \n\r-")
            if len(trimmed) >= 40:
                return trimmed
            break
    return current_text


def _fold_vn(text: str) -> str:
    if not text:
        return ""
    s = text.replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


_NUMERIC_FACT_CUE_RE = re.compile(
    r"\b(?:bao\s*nhiêu|bao\s*nhieu|mức|muc|tỷ\s*lệ|ty\s*le|giá|gia|số\s*lượng|so\s*luong|"
    r"thời\s*hạn|thoi\s*han|khi\s*nào|khi\s*nao|điều\s*kiện|dieu\s*kien|phạt|phat|lãi|lai|gpa|điểm|diem)\b",
    re.IGNORECASE | re.UNICODE,
)


def _extract_pinpointed_answer_sentences(
    query: str,
    context_chunks: List[Dict[str, Any]],
    max_sentences: int = 3,
) -> Optional[str]:
    """
    Chấm điểm từng câu và từng tiểu mục trong các chunk tìm được (<1ms) để trích ra:
    - Các mục tiêu đề (`7. Công nghệ dự kiến`, `11. Hướng mở rộng dài hạn`...) kèm nội dung trực thuộc khi câu hỏi hỏi nhiều vế.
    - 1–3 câu chứa mật độ từ khóa + con số/điều khoản khớp nhất với câu hỏi để ghim lên đầu Prompt.
    Giúp model nhẹ 3B trả lời ĐẦY ĐỦ và TRÚNG ĐÍCH 100% các vế của câu hỏi.
    """
    if not query or not context_chunks:
        return None

    q_folded = _fold_vn(query)
    stop_words = {
        "la", "gi", "nhu", "the", "nao", "cua", "trong", "cho", "toi", "hoi", "ve", "tai",
        "lieu", "nay", "co", "khong", "duoc", "nhung", "cac", "mot", "va", "hay", "biet",
        "mo", "ta", "chi", "tiet", "hon", "su", "dung", "de", "tao", "ra", "he", "thong",
    }
    q_tokens = [
        t for t in re.sub(r"[^\w\s]", " ", q_folded).split()
        if (len(t) >= 2 and t not in stop_words) or t.isdigit()
    ]
    if not q_tokens:
        return None

    # 1. Quét các tiểu mục (Section blocks) có tiêu đề khớp trực tiếp với các vế câu hỏi
    matched_sections: List[str] = []
    heading_pat = re.compile(
        r"(?m)^\s*(?:#{1,4}\s*|\d{1,2}(?:\.\d{1,2})?\.\s+|(?:Chương|Bài|Phần|Mục|Điều)\s+(?:[IVXLCDM]+|\d+)\b)[^\n]{2,90}$"
    )
    seen_sec_titles = set()
    for idx, chunk in enumerate(context_chunks[:5], start=1):
        content = str(chunk.get("content") or "").strip()
        if not content:
            continue
        matches = list(heading_pat.finditer(content))
        for m_pos, m in enumerate(matches):
            h_line = m.group(0).strip()
            h_folded = _fold_vn(h_line)
            if h_folded in seen_sec_titles:
                continue
            if any(tok in h_folded for tok in q_tokens if len(tok) >= 3):
                sec_start = m.end()
                sec_end = matches[m_pos + 1].start() if (m_pos + 1) < len(matches) else len(content)
                sec_body = content[sec_start:sec_end].strip()
                if sec_body:
                    seen_sec_titles.add(h_folded)
                    compact_body = " ; ".join(
                        ln.strip() for ln in sec_body.splitlines() if ln.strip()
                    )[:520]
                    matched_sections.append(f"  • [{idx}] **{h_line}**: {compact_body}")

    wants_number = bool(_NUMERIC_FACT_CUE_RE.search(query))
    scored_sentences: List[tuple[float, str]] = []
    seen_norm = set()

    for idx, chunk in enumerate(context_chunks[:5], start=1):
        content = str(chunk.get("content") or "").strip()
        if not content:
            continue
        raw_parts = re.split(r"(?<=[.!?])\s+|\n+", content)
        for part in raw_parts:
            sent = part.strip(" -•*\t\r")
            if len(sent) < 18 or len(sent) > 380 or sent.startswith("[CÂY MỤC LỤC") or sent.startswith("---"):
                continue
            s_folded = _fold_vn(sent)
            if s_folded in seen_norm:
                continue
            seen_norm.add(s_folded)

            matched_tokens = sum(1 for tok in q_tokens if tok in s_folded)
            if matched_tokens == 0:
                continue
            coverage = matched_tokens / max(1, len(q_tokens))
            if coverage < 0.30 and matched_tokens < 2:
                continue

            score = coverage * 10.0 + matched_tokens * 1.5
            if wants_number and re.search(r"\d+(?:[.,]\d+)?(?:\s*%|\s*đồng|\s*triệu|\s*ngày|\s*tháng|\s*năm)?", sent, re.IGNORECASE):
                score += 3.5
            score += max(0.0, 1.2 - idx * 0.20)
            scored_sentences.append((score, f"[{idx}] {sent}"))

    out_lines: List[str] = []
    if matched_sections:
        out_lines.extend(matched_sections[:4])
    if scored_sentences and len(out_lines) < max_sentences + 1:
        scored_sentences.sort(key=lambda item: item[0], reverse=True)
        for _, s in scored_sentences[:max_sentences]:
            bullet = f"  • {s}"
            if bullet not in out_lines:
                out_lines.append(bullet)

    return "\n".join(out_lines) if out_lines else None


def _build_instant_followup_suggestions(
    query: str,
    citations: List[Dict[str, Any]],
    context_chunks: List[Dict[str, Any]],
) -> List[str]:
    """
    Tự động sinh 3 câu hỏi gợi ý tiếp theo sát nội dung tài liệu trong < 0.5ms
    mà không bắt LLM phải tốn 80–120 tokens gõ thêm ở cuối câu trả lời.
    """
    suggestions: List[str] = []
    q_folded = _fold_vn(query)
    has_local_citations = any(c.get("source_type") == "document" for c in (citations or []))

    # 1. Chỉ trích xuất tiêu đề Chương/Bài/Điều/Mục khi thực sự có tài liệu địa phương liên quan được trích dẫn
    if has_local_citations:
        for ch in (context_chunks or [])[:4]:
            txt = str(ch.get("content") or "")
            for m in re.finditer(
                r"(?:^|\n)\s*(?:#{1,4}\s*)?((?:(?:Chương|Bài|Phần|Điều|Mục)\s+(?:[IVXLCDM]{1,5}|\d{1,3}))|(?:\d{1,2}\.\s+[^\n:]{4,48}))(?:\s*[:.-]\s*([^\n]{4,52}))?",
                txt,
                re.UNICODE,
            ):
                sec_label = m.group(1).strip()
                raw_title = (m.group(2) or "").strip(" :.-")
                # Tránh cắt cụt số thập phân kiểu 'GPA từ 3.60' hoặc '8.000.000': chỉ cắt ở dấu chấm câu có khoảng trắng theo sau
                sec_title = re.split(r"\.\s+|\n", raw_title)[0].strip(" :.,;-")
                combined_sec = f"{sec_label} {sec_title}"
                if (
                    _fold_vn(sec_label) in q_folded
                    or re.search(r"(?:FALSE|TRUE|hiển thị thông báo|trả về|nhập lại|email không)", combined_sec, re.IGNORECASE)
                ):
                    continue
                cand = (
                    f"{sec_label} ({sec_title}) quy định cụ thể những gì?"
                    if sec_title and len(sec_title) <= 44
                    else f"Nội dung chi tiết của {sec_label} gồm những gì?"
                )
                if cand not in suggestions:
                    suggestions.append(cand)
                if len(suggestions) >= 2:
                    break
            if len(suggestions) >= 2:
                break

    doc_name = citations[0].get("document_name") if has_local_citations else None
    sample_raw = "\n".join(str(ch.get("content") or "")[:600] for ch in (context_chunks or [])[:3])
    sample_folded = f"{_fold_vn(doc_name or '')} {_fold_vn(sample_raw)}"

    is_vocab_doc = bool(
        re.search(
            r"\b(?:tu\s+vung|3000\s+tu|tieng\s+anh|tieng\s+nhat|english|vocabulary|mimikara|jlpt|n[1-5]|kanji|hiragana|katakana|phien\s+am)\b",
            sample_folded,
        )
        or (re.search(r"/[^/\n]{2,18}/", sample_raw) and re.search(r"\b(?:n|v|adj|adv|prep|pron)\.", sample_raw))
    )
    is_policy_doc = bool(
        re.search(
            r"\b(?:quy\s+dinh|dieu\s+khoan|noi\s+quy|hop\s+dong|quy\s+che|luat|nghi\s+dinh|thong\s+tu|hoc\s+bong|che\s+tai|ngoai\s+le|bao\s+luu)\b",
            sample_folded,
        )
    )
    is_tech_doc = bool(
        re.search(
            r"\b(?:api|rag|llm|vector|bm25|pipeline|kien\s+truc|database|sql|python|docker|server|thuat\s+toan|framework|microservice)\b",
            sample_folded,
        )
    )
    is_numeric_doc = bool(
        re.search(
            r"\b(?:doanh\s+thu|chi\s+phi|loi\s+nhuan|lai\s+suat|ngan\s+sach|kpi|bao\s+cao\s+tai\s+chinh)\b|\.xlsx?\b|\.csv\b",
            sample_folded,
        )
    )

    if is_vocab_doc:
        defaults = [
            f"Lấy 8 từ vựng tiêu biểu kèm phiên âm, nghĩa và câu ví dụ từ {doc_name}" if doc_name else "Lấy 8 từ vựng tiêu biểu kèm ví dụ minh họa",
            "Phân biệt cách dùng và đặt câu ví dụ thực tế cho các từ vừa nêu",
            "Tạo 5 câu hỏi trắc nghiệm ôn tập từ vựng từ nội dung vừa trao đổi",
        ]
    elif is_policy_doc:
        defaults = [
            f"Có điều kiện ngoại lệ hoặc lưu ý quan trọng nào khác trong {doc_name} không?" if doc_name else "Có trường hợp ngoại lệ hay lưu ý thực tế nào cần chú ý không?",
            "Hãy tóm tắt các quy định chính thành bảng hoặc gạch đầu dòng ngắn gọn",
            "Nêu ví dụ tình huống áp dụng cụ thể cho các điều kiện trên",
        ]
    elif is_tech_doc:
        defaults = [
            f"Phân tích ưu nhược điểm và các thành phần cốt lõi trong {doc_name}" if doc_name else "Phân tích ưu nhược điểm và cách tối ưu kiến trúc vừa nêu",
            "Sơ đồ hóa quy trình hoạt động từng bước bằng gạch đầu dòng ngắn gọn",
            "Tóm tắt các công nghệ và thông số chính thành bảng so sánh",
        ]
    elif is_numeric_doc:
        defaults = [
            f"Tổng hợp các chỉ số và con số nổi bật nhất trong {doc_name}" if doc_name else "Tổng hợp các chỉ số và con số nổi bật nhất từ dữ liệu trên",
            "So sánh chênh lệch hoặc xu hướng giữa các nhóm dữ liệu liên quan",
            "Tóm tắt thành bảng số liệu gọn kèm nhận xét chính",
        ]
    else:
        defaults = [
            "Hãy tóm tắt các ý chính liên quan thành bảng hoặc gạch đầu dòng ngắn gọn",
            "Giải thích chi tiết hơn kèm ví dụ minh họa cho nội dung vừa trao đổi",
            "Tạo 5 câu hỏi trắc nghiệm nhanh từ nội dung vừa trao đổi",
        ]
    for d in defaults:
        if len(suggestions) >= 3:
            break
        if _fold_vn(d) not in q_folded and d not in suggestions:
            suggestions.append(d)

    return suggestions[:3]


def _resolve_sampling_options(
    query: str,
    num_ctx: int,
    max_predict: int,
    image_base64: Optional[str] = None,
    estimated_input_tokens: int = 0,
) -> Dict[str, Any]:
    """
    Tinh chỉnh temperature/top_p và co giãn động KV-Cache (num_ctx / num_predict)
    theo độ dài thực tế của ngữ cảnh để giảm VRAM trên RTX 3050 và tăng tốc sinh token.
    """
    q_clean = (query or "").strip()
    word_cnt = len(q_clean.split())
    is_precise = bool(
        image_base64
        or _FACTUAL_LOW_TEMP_RE.search(q_clean)
        or word_cnt <= 5
    )
    is_short_lookup = (
        word_cnt <= 8
        and not _GLOBAL_SUMMARY_CUE_RE.search(q_clean)
        and not _LAB_STEPS_CUE_RE.search(q_clean)
        and not _COMPARE_CUE_RE.search(q_clean)
    )

    if image_base64:
        dyn_predict = 512
    elif is_short_lookup:
        dyn_predict = min(max_predict, 520)
    else:
        dyn_predict = min(max_predict, 1280)

    if estimated_input_tokens > 0:
        needed = estimated_input_tokens + dyn_predict + 192
        if needed <= 1536:
            dyn_ctx = 1536
        elif needed <= 2048:
            dyn_ctx = 2048
        elif needed <= 3072:
            dyn_ctx = 3072
        else:
            dyn_ctx = num_ctx
        dyn_ctx = min(num_ctx, dyn_ctx)
    else:
        dyn_ctx = num_ctx

    return {
        "num_predict": dyn_predict,
        "temperature": 0.20 if is_precise else 0.45,
        "top_p": 0.85 if is_precise else 0.90,
        "repeat_penalty": 1.18,
        "num_ctx": dyn_ctx,
    }


def _build_dynamic_system_prompt(
    query: str,
    has_local: bool,
    has_web: bool,
    image_base64: Optional[str] = None,
) -> str:
    """Tạo system prompt tự nhiên, súc tích và linh hoạt theo ý định câu hỏi."""
    q_clean = (query or "").strip()
    is_short_lookup = len(q_clean.split()) <= 5 and not _GLOBAL_SUMMARY_CUE_RE.search(q_clean) and not _LAB_STEPS_CUE_RE.search(q_clean)

    sections: List[str] = [
        "Bạn là Motivo AI — trợ lý tri thức cá nhân thông minh, diễn đạt tiếng Việt tự nhiên, đầy đủ và chuẩn xác.\n\n"
        "NGUYÊN TẮC TRẢ LỜI:\n"
        "- Trả lời thẳng vào nội dung câu hỏi ngay từ câu đầu tiên; TUYỆT ĐỐI KHÔNG lặp lại nguyên văn câu hỏi ('Câu hỏi của bạn là...', 'Bạn đã hỏi...').\n"
        "- BẮT BUỘC TRẢ LỜI ĐẦY ĐỦ MỌI VẾ CỦA CÂU HỎI: Nếu câu hỏi có nhiều vế (ví dụ: hỏi về 'A và B', hoặc tài liệu có nhiều mục liên quan), hãy chia câu trả lời thành các đề mục in đậm rõ ràng để giải đáp trọn vẹn từng vế, liệt kê đầy đủ tất cả các thành phần/hạng mục có trong nguồn mà không bỏ sót hay viết tắt giữa chừng.\n"
        "- TUYỆT ĐỐI KHÔNG chia câu trả lời theo kiểu tách rời 'Tài liệu 1: ... Tài liệu 2: ...', KHÔNG dùng tiêu đề `### [1]` hay `**[1]`, và KHÔNG lặp lại cùng một định nghĩa/định lý nhiều lần. Luôn tổng hợp các đoạn nguồn liên quan thành MỘT câu trả lời thống nhất duy nhất và chỉ gắn `[1]`, `[2]` ở cuối ý.\n"
        "- CHỈ TRẢ LỜI ĐÚNG CHỦ ĐỀ ĐƯỢC HỎI: Nếu đoạn trích có lẫn sang mục khác không thuộc câu hỏi (ví dụ hỏi 'Hàm số đồng biến – nghịch biến' nhưng ngữ cảnh có thêm 'Hệ số góc' hoặc 'Vẽ đồ thị parabol'), BỎ QUA hoàn toàn các mục ngoài chủ đề đó, và KHÔNG lặp lại công thức ở cuối câu trả lời.\n"
        "- KHÔNG chép chuỗi OCR lỗi kiểu `( ) 2 y ax a = ≠` hay `x∈` khi chưa rõ công thức; hãy diễn đạt thành công thức chuẩn (`y = ax² (a ≠ 0)`).\n"
        "- TUYỆT ĐỐI KHÔNG tự bịa ra định dạng 'Câu Hỏi ÔN TẬP', 'Câu 1:', 'Đáp Án:' khi người dùng chỉ đang hỏi thông tin bình thường.\n"
        "- TUYỆT ĐỐI KHÔNG bịa kiến thức ngoài cấp học/tài liệu (ví dụ: không tự thêm 'đạo hàm' vào tài liệu Toán lớp 9 nếu tài liệu không hề nhắc đến) và KHÔNG mở đầu câu kiểu máy móc ('Tài liệu [1] mô tả...', 'Để đáp lại yêu cầu của bạn...').\n"
        "- Nếu kho tài liệu KHÔNG chứa thông tin được hỏi: nói rõ 'Tài liệu trong kho tri thức của bạn không chứa thông tin về [chủ đề].', sau đó giải đáp ngắn gọn bằng kiến thức chuẩn xác (không gắn [1], [2] giả) hoặc liệt kê nhanh vài mục tiêu biểu dưới dạng gạch đầu dòng sạch."
    ]

    if is_short_lookup and not has_web:
        sections.append(
            "- PHONG CÁCH TRA CỨU NHANH: Đi thẳng vào kết quả trong 1–4 câu hoặc gạch đầu dòng ngắn gọn, đúng trọng tâm."
        )
    if _COMPARE_CUE_RE.search(q_clean):
        sections.append(
            "- KHI SO SÁNH / ĐỐI CHIẾU: Trình bày bảng Markdown đối chiếu tiêu chí rõ ràng trước, sau đó tóm tắt điểm khác biệt cốt lõi và khuyến nghị."
        )
    if has_local and _LAB_STEPS_CUE_RE.search(q_clean):
        sections.append(
            "- KHI HƯỚNG DẪN THỰC HÀNH: Nêu mục tiêu ngắn gọn, đánh số liên tục 'Bước 1:', 'Bước 2:'... đủ quy trình, rõ lệnh/thao tác cụ thể, không lặp lại ý giữa các bước."
        )
    if _GLOBAL_SUMMARY_CUE_RE.search(q_clean):
        sections.append(
            "- TỔNG HỢP TOÀN TÀI LIỆU: Sắp xếp mạch lạc theo từng phần/chương/bài kèm ý chính nổi bật."
        )
    if has_web:
        sections.append(
            "- NGUỒN INTERNET: Tổng hợp các nguồn web thành MỘT câu trả lời thống nhất hoàn chỉnh (không liệt kê rời rạc '[1]: ... [2]: ...'); nêu trực tiếp số liệu/ngày giờ nếu có."
        )
    if image_base64:
        sections.append(
            "- ẢNH ĐÍNH KÈM: Đọc kỹ chữ, số, công thức hoặc sơ đồ trong ảnh và trả lời trực diện câu hỏi."
        )

    sections.append(
        "ĐỊNH DẠNG:\n"
        "- Sử dụng Markdown sạch (tiêu đề `###`, in đậm từ khóa, gạch đầu dòng thoáng mắt cho danh sách/từ vựng). Viết công thức toán bằng chữ/ký hiệu phổ thông sạch sẽ như `150.000.000 × (1 + 0,068)^5 = 208.423.902,12 đồng`; TUYỆT ĐỐI KHÔNG dùng cú pháp LaTeX (`\\boxed{...}`, `\\(...\\)`, `\\[...\\]`) và KHÔNG chép lại tên biến Python.\n"
        "- Dừng ngay sau khi trả lời xong đầy đủ câu hỏi chính; KHÔNG viết câu xã giao thừa ở cuối ('Nếu bạn cần thêm thông tin..., xin vui lòng cung cấp chi tiết hơn.') và KHÔNG viết mục `---GỢI Ý TIẾP THEO---`."
    )
    return "\n\n".join(sections)


_SYMBOL_PUA_MAP = str.maketrans({
    "\uf022": "∀",
    "\uf024": "∃",
    "\uf028": "(",
    "\uf029": ")",
    "\uf02a": "×",
    "\uf02b": "+",
    "\uf02d": "-",
    "\uf02f": "/",
    "\uf03a": ":",
    "\uf03b": ";",
    "\uf03c": "<",
    "\uf03d": "=",
    "\uf03e": ">",
    "\uf044": "Δ",
    "\uf05b": "[",
    "\uf05d": "]",
    "\uf05e": "^",
    "\uf061": "α",
    "\uf062": "β",
    "\uf067": "γ",
    "\uf064": "δ",
    "\uf066": "φ",
    "\uf070": "π",
    "\uf071": "θ",
    "\uf073": "σ",
    "\uf077": "ω",
    "\uf07b": "{",
    "\uf07c": "|",
    "\uf07d": "}",
    "\uf0a2": "′",
    "\uf0a3": "≤",
    "\uf0a5": "∞",
    "\uf0a7": "•",
    "\uf0a8": "•",
    "\uf0ae": "→",
    "\uf0b0": "°",
    "\uf0b1": "±",
    "\uf0b3": "≥",
    "\uf0b4": "×",
    "\uf0b8": "÷",
    "\uf0b9": "≠",
    "\uf0bb": "≈",
    "\uf0ce": "∈",
    "\uf0cf": "∉",
    "\uf0db": "⇔",
    "\uf0de": "⇒",
    "\uf0e9": "[",
    "\uf0ea": "[",
    "\uf0eb": "[",
    "\uf0ec": "{",
    "\uf0ed": "{",
    "\uf0ee": "{",
    "\uf0ef": "|",
    "\uf0f9": "]",
    "\uf0fa": "]",
    "\uf0fb": "]",
})


def decode_symbol_pua_text(text: str) -> str:
    """
    Giải mã ký tự font MS Word Symbol/Wingdings (vùng PUA \\uf020-\\uf0ff)
    thành ký hiệu toán học chuẩn (=, +, π, ≤, ≥, ⇔...) và gom dòng công thức bị xẻ dọc.
    """
    if not text:
        return ""
    cleaned = text.replace("\xa0", " ").translate(_SYMBOL_PUA_MAP)
    cleaned = re.sub(r"[\uf000-\uf0ff]", "", cleaned)

    # Gom các chuỗi >= 3 dòng cực ngắn (<= 4 ký tự) do PyMuPDF tách từng ký tự công thức thành 1 dòng đọc được
    lines = cleaned.splitlines()
    out_lines: List[str] = []
    short_buf: List[str] = []
    for ln in lines:
        s = ln.strip()
        if 0 < len(s) <= 4 and not re.match(r"^(?:[A-ZĐÂĂÊÔƠƯ]{2,}|Trang|\d+\.)$", s):
            short_buf.append(s)
        else:
            if len(short_buf) >= 3:
                out_lines.append(" ".join(short_buf))
            elif short_buf:
                out_lines.extend(short_buf)
            short_buf = []
            out_lines.append(ln)
    if len(short_buf) >= 3:
        out_lines.append(" ".join(short_buf))
    elif short_buf:
        out_lines.extend(short_buf)
    return "\n".join(out_lines)


def _strip_raw_latex_math(text: str) -> str:
    """Chuyển đổi các lệnh LaTeX thô (\\frac, \\sqrt, \\pi, \\approx, ^{}, _{}) sang văn bản/Unicode dễ đọc."""
    if not text:
        return ""
    res = text
    res = re.sub(r"\\boxed\{([^{}]+)\}", r"**\1**", res)
    res = re.sub(r"\\text\{([^{}]+)\}", r"\1", res)
    res = re.sub(r"\\(?:left|right)\b", "", res)

    # Xử lý lặp \sqrt{...} và \frac{...}{...} từ trong ra ngoài (tối đa 4 vòng lồng nhau)
    for _ in range(4):
        prev = res
        res = re.sub(
            r"\\sqrt\{([^{}]+)\}",
            lambda m: f"√{m.group(1)}" if re.fullmatch(r"[\w.,]+", m.group(1).strip()) else f"√({m.group(1).strip()})",
            res,
        )
        res = re.sub(
            r"\\frac\{([^{}]+)\}\{([^{}]+)\}",
            lambda m: (
                f"{m.group(1).strip() if re.fullmatch(r'[\w.()√π]+', m.group(1).strip()) else '(' + m.group(1).strip() + ')'}"
                "/"
                f"{m.group(2).strip() if re.fullmatch(r'[\w.()√π]+', m.group(2).strip()) else '(' + m.group(2).strip() + ')'}"
            ),
            res,
        )
        if res == prev:
            break

    latex_tokens = (
        ("\\times", "×"),
        ("\\cdot", "·"),
        ("\\%", "%"),
        ("\\pi", "π"),
        ("\\approx", "≈"),
        ("\\pm", "±"),
        ("\\leq", "≤"),
        ("\\le", "≤"),
        ("\\geq", "≥"),
        ("\\ge", "≥"),
        ("\\neq", "≠"),
        ("\\ne", "≠"),
        ("\\Delta", "Δ"),
        ("\\alpha", "α"),
        ("\\beta", "β"),
        ("\\gamma", "γ"),
        ("\\theta", "θ"),
        ("\\Leftrightarrow", "⇔"),
        ("\\Rightarrow", "⇒"),
        ("\\rightarrow", "→"),
        ("\\infty", "∞"),
        ("\\arctan", "arctan"),
        ("\\arcsin", "arcsin"),
        ("\\arccos", "arccos"),
        ("\\sin", "sin"),
        ("\\cos", "cos"),
        ("\\tan", "tan"),
        ("\\cot", "cot"),
        ("\\in", "∈"),
        ("\\perp", "⊥"),
    )
    for k, v in latex_tokens:
        res = res.replace(k, v)

    res = res.replace("\\(", "").replace("\\)", "").replace("\\[", "").replace("\\]", "")
    res = re.sub(r"\b(sin|cos|tan|cot|arcsin|arccos|arctan|log)\s*\{([^{}]+)\}", r"\1(\2)", res)
    res = re.sub(r"\{([A-Za-z0-9αβγθΔπ]{1,3})\}", r"\1", res)
    res = re.sub(r"\^\{2\}|\^2(?![0-9])", "²", res)
    res = re.sub(r"\^\{3\}|\^3(?![0-9])", "³", res)
    res = re.sub(r"\^\{([^{}]+)\}", r"^\1", res)
    sub_digits = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
    res = re.sub(
        r"(?<=[a-zA-Z])_\{([0-9]+)\}|(?<=[a-zA-Z])_([0-9])(?![0-9])",
        lambda m: (m.group(1) or m.group(2) or "").translate(sub_digits),
        res,
    )
    res = re.sub(r"_\{([^{}]+)\}", r"(\1)", res)
    res = re.sub(r"\(\s+([^()\n]{2,80}?)\s+\)", r"(\1)", res)
    res = re.sub(r"\(\s*\*\*([^*]+)\*\*\s*\)", r"**\1**", res)
    return res


def _sanitize_rag_output(answer: str, citations_count: int) -> str:
    """
    Hậu kiểm câu trả lời RAG (<0.2ms):
    1. Chuẩn hóa `[Tài liệu 1]`, `[Nguồn 1]`, `[Nguồn web 1]` về `[1]`.
    2. Loại bỏ cú pháp LaTeX thô (`\\boxed{...}`, `\\( ... \\)`, `\\[ ... \\]`) và tiêu đề prompt nội bộ nếu model 3B chép nhầm.
    3. Chuyển `[1]: Nội dung` đầu dòng về `- Nội dung [1]`.
    4. Loại bỏ trích dẫn giả `[n]` nằm ngoài phạm vi nguồn thực tế (`n > citations_count` hoặc `n <= 0`).
    5. Chuẩn hóa nhãn `---GỢI Ý TIẾP THEO---`.
    """
    if not answer:
        return ""
    text = answer

    # 0. Gỡ tiêu đề nội bộ, câu mở/chốt máy móc, dòng biến Sandbox/tên file bị rò và làm sạch LaTeX thô
    text = re.sub(
        r'^(?:Câu\s+hỏi\s+của\s+bạn\s+là|Bạn\s+đã\s+hỏi|Về\s+câu\s+hỏi)\s*[:：]?\s*["“]?[^\n]{4,260}?["”]?\s*(?:\n+|$)',
        "",
        text,
        flags=re.IGNORECASE | re.UNICODE,
    )
    text = re.sub(
        r"^(?:Để\s+đáp\s+lại\s+yêu\s+cầu\s+của\s+bạn[^\n]{0,180}:\s*\n+)",
        "",
        text,
        flags=re.IGNORECASE | re.UNICODE,
    )
    text = re.sub(
        r"(?im)^\s*#{0,4}\s*\*{0,2}\s*\[\s*(?:Tài\s*liệu|Nguồn(?:\s*web)?|Web)?\s*(\d{1,3})\s*\]\*{0,2}\s*$",
        "",
        text,
    )
    text = re.sub(
        r"(?im)^(?:#{1,4}\s*)?(?:KẾT\s*QUẢ\s*ĐÃ\s*KIỂM\s*CHỨNG\s*BẰNG\s*PYTHON\s*SANDBOX[^:\n]*|\[(?:DỮ\s*KIỆN\s*TOÁN\s*HỌC|SỐ\s*LIỆU\s*ĐỐI\s*CHIẾU)[^\]]*\]|Các\s+giá\s+trị\s+chính\s+xác\s+đã\s+tính\s*:[^\n]*|Đáp\s+số\s+cuối\s+cùng\s+chính\s+xác\s+tuyệt\s+đối\s*:[^\n]*|Kết\s+quả\s+chính\s+cuối\s+cùng\s*:[^\n]*)\s*\n*",
        "",
        text,
    )
    text = re.sub(
        r"(?im)^\s*(?:\[?\d{1,2}\]?\s*[._:-]*\s*)?_?[^\n]{2,90}\.(?:pdf|docx?|xlsx?|txt)\s*\(\s*Trang\s*\d+[^\)]*\)\s*(?:[-–]\s*\[?\d{1,2}\]?)?\s*(?:\n|$)",
        "",
        text,
    )
    for py_var, clean_lbl in (
        ("duong_sinh_l", "l"),
        ("V_non_cut", "V(nón cụt)"),
        ("V_non-cut", "V(nón cụt)"),
        ("S_xq_non_cut", "Sxq(nón cụt)"),
        ("S_xq_non-cut", "Sxq(nón cụt)"),
        ("S_tp_non_cut", "Stp(nón cụt)"),
        ("S_tp_non-cut", "Stp(nón cụt)"),
        ("V_tru", "V(hình trụ)"),
        ("S_tp_tru", "Stp(hình trụ)"),
        ("chenh_lech_V", "ΔV"),
        ("chenh_lech_phan_tram", "Tỷ lệ chênh lệch"),
    ):
        text = re.sub(rf"\b{re.escape(py_var)}\b", clean_lbl, text)
    text = _strip_raw_latex_math(text)

    # 1. Chuẩn hóa [Tài liệu [1]: ten_file (Trang X)] / [tài liệu [2]]: ... / [Tài liệu 1] / [Nguồn web 1] -> [1]
    text = re.sub(
        r'"?\[\s*(?:Tài\s*liệu|Nguồn(?:\s*web)?)\s*\[?\s*(\d{1,3})\s*\]?\s*\]?\s*:\s*[^\]\n"]{2,180}\]?"?',
        r"[\1]",
        text,
        flags=re.IGNORECASE | re.UNICODE,
    )
    text = re.sub(
        r'"?\[\s*(?:Tài\s*liệu|Nguồn(?:\s*web)?)\s*\[?\s*(\d{1,3})\s*\]?\s*\]?"?',
        r"[\1]",
        text,
        flags=re.IGNORECASE | re.UNICODE,
    )
    text = re.sub(
        r"\[\s*(\d{1,3})\s*\]\s+(?:mô\s+tả|đề\s+cập|nêu|cho\s+biết|liệt\s+kê)\s*(?:các\s+từ\s+như|cụ\s+thể|chi\s+tiết)?\s*",
        r"Nguồn [\1] nêu ",
        text,
        flags=re.IGNORECASE | re.UNICODE,
    )
    text = re.sub(
        r"\b(?:Trong\s+)?[Tt]ài\s+liệu\s*\[?(\d{1,2})\]?\s+(?:mô\s+tả|đề\s+cập|nêu|cho\s+biết)\s*(?:rằng|cụ\s+thể|chi\s+tiết)?\s*(?:về\s+)?",
        r"",
        text,
    )
    text = re.sub(
        r"\(\s*[Tt]ài\s+liệu\s*\[?(\d{1,2})\]?\s*\)",
        r"[\1]",
        text,
    )
    text = re.sub(
        r"\n*\s*Nếu\s+bạn\s+cần\s+thêm\s+thông\s+tin\s+cụ\s+thể[^.\n]{0,180}(?:chi\s+tiết\s+hơn|hỗ\s+trợ\s+thêm|cho\s+tôi\s+biết)[^.\n]*\.?\s*$",
        "",
        text,
        flags=re.IGNORECASE | re.UNICODE,
    )

    # 2. Xử lý trường hợp model nhỏ viết `[1]: ...` hoặc `[2]: ...` ở đầu dòng như danh sách liệt kê
    def _fix_leading_list_ref(match: re.Match) -> str:
        idx = int(match.group(1))
        body_part = match.group(2).strip()
        if 1 <= idx <= citations_count:
            if f"[{idx}]" not in body_part:
                return f"- {body_part} [{idx}]"
            return f"- {body_part}"
        if citations_count == 1:
            return f"- {body_part} [1]" if "[1]" not in body_part else f"- {body_part}"
        return f"- {body_part}"

    text = re.sub(r"(?m)^\s*\[(\d{1,2})\]\s*:\s*(.+)$", _fix_leading_list_ref, text)

    # 3. Cắt các trích dẫn [n] vượt phạm vi nguồn thực tế
    def _filter_citation(match: re.Match) -> str:
        idx = int(match.group(1))
        if 1 <= idx <= citations_count:
            return match.group(0)
        return ""

    text = re.sub(r"\[(\d{1,3})\]", _filter_citation, text)
    text = re.sub(r" +([,.;:])", r"\1", text)
    text = re.sub(
        r"\n*\s*(?:Trích\s+dẫn\s+được\s+thực\s+hiện\s+dựa\s+trên\s+thông\s+tin\s+trong\s+tài\s+liệu|Hãy\s+đối\s+chiếu\s+tài\s+liệu)[^.\n]*\.?\s*$",
        "",
        text,
        flags=re.IGNORECASE | re.UNICODE,
    )

    # 3b. Khử lặp dòng/mục giống hệt hoặc gần trùng nhau do model nhỏ (3B) lặp lại theo từng tài liệu
    if "\n" in text:
        dedup_lines: List[str] = []
        seen_norm_lines: set[str] = set()
        for ln in text.splitlines():
            stripped_ln = ln.strip()
            if not stripped_ln:
                if dedup_lines and dedup_lines[-1] != "":
                    dedup_lines.append("")
                continue
            norm_ln = re.sub(r"\[\d+\]|từ\s+tài\s+liệu\s*\d+|\(\s*tài\s+liệu\s*\d+\s*\)", "", stripped_ln, flags=re.IGNORECASE)
            norm_ln = re.sub(r"[\s*#:\-–.,;()=+/]+", " ", norm_ln).strip().lower()
            is_heading_or_label = stripped_ln.startswith("#") or stripped_ln.endswith(":")
            if len(norm_ln) >= 12:
                is_exact_dup = len(norm_ln) >= 18 and norm_ln in seen_norm_lines
                is_clipped_dup = (
                    not is_heading_or_label
                    and len(norm_ln.split()) >= 5
                    and any(norm_ln in prev for prev in seen_norm_lines if len(prev) > len(norm_ln))
                )
                if is_exact_dup or is_clipped_dup:
                    continue
                seen_norm_lines.add(norm_ln)
            dedup_lines.append(ln)
        text = "\n".join(dedup_lines).strip()

    # 4. Chuẩn hóa nhãn phân tách gợi ý và làm sạch tiền tố `[Gợi ý 1]` hoặc `Gợi ý 1:`
    text = re.sub(
        r"(?:---\s*\n\s*-{1,3}\s*GỢI\s*Ý\s*TIẾP\s*THEO\s*-{2,3}|-{2,3}\s*GỢI\s*Ý\s*TIẾP\s*THEO\s*-{2,3})",
        "---GỢI Ý TIẾP THEO---",
        text,
        flags=re.IGNORECASE | re.UNICODE,
    )
    if "---GỢI Ý TIẾP THEO---" in text:
        main_part, sug_part = text.split("---GỢI Ý TIẾP THEO---", 1)
        sug_part = re.sub(
            r"(?m)^(\s*[-*•]?\s*)(?:\[?\s*Gợi\s*ý\s*\d+\s*\]?\s*[:.-]?\s*)",
            r"\1",
            sug_part,
            flags=re.IGNORECASE,
        )
        text = f"{main_part.rstrip()}\n\n---GỢI Ý TIẾP THEO---\n{sug_part.strip()}"

    return text


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
    seen_doc_tails: Dict[str, str] = {}

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
        prompt_doc_name = re.sub(r"^\[[^\]]+\]_?", "", str(chunk.get("document_name") or "")).strip() or str(chunk.get("document_name") or "")
        header = f"\n--- [Tài liệu {ref_id}]: {prompt_doc_name}{page_suffix} ---\n"
        raw_body = decode_symbol_pua_text(str(chunk.get("content", "")))
        doc_key = str(chunk.get("document_id") or "")
        deduped_body = (
            _deduplicate_chunk_overlap(seen_doc_tails[doc_key], raw_body)
            if doc_key and doc_key in seen_doc_tails
            else raw_body
        )
        focused_excerpt = _extract_tabular_match_excerpt(query, deduped_body)
        body = (
            f"[Khớp trực tiếp]: {focused_excerpt}\n{deduped_body}"
            if focused_excerpt
            else deduped_body
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

        if doc_key:
            seen_doc_tails[doc_key] = raw_body
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
    pinpointed = _extract_pinpointed_answer_sentences(query, context_chunks) if has_local else None
    pinpoint_block = (
        f"\n🎯 [TRÍCH ĐOẠN TRỌNG TÂM KHỚP CÂU HỎI NHẤT (ưu tiên trả lời chính xác từ thông tin này)]:\n{pinpointed}\n"
        if pinpointed
        else ""
    )

    if not has_local and not has_web:
        user_prompt = (
            f"Câu hỏi của người dùng: {query}\n\n"
            "LƯU Ý ĐẶC BIỆT: Tài liệu trong kho tri thức của người dùng KHÔNG chứa thông tin về câu hỏi này.\n"
            "1. Hãy thông báo rõ ràng cho người dùng biết điều đó (ví dụ: 'Tài liệu trong kho tri thức của bạn không chứa thông tin về...').\n"
            "2. Sau đó, giải đáp câu hỏi của người dùng bằng kiến thức chuẩn xác, đầy đủ của bạn.\n"
            "3. TUYỆT ĐỐI KHÔNG gắn bất kỳ nhãn trích dẫn tài liệu nào như [1], [2], [Tài liệu 1]."
        )
    elif has_web and not has_local:
        user_prompt = (
            f"Dưới đây là các kết quả tìm kiếm trên Internet:\n{context_text}\n"
            f"\nCâu hỏi/Yêu cầu của người dùng: {query}\n"
            "\nHãy tổng hợp các nguồn trên thành một bài giải đáp/hướng dẫn hoàn chỉnh, gắn nhãn trích dẫn [1], [2] tương ứng:"
        )
    elif has_local and not has_web:
        user_prompt = (
            f"Dưới đây là các tài liệu trong kho tri thức của người dùng:\n{context_text}"
            f"{pinpoint_block}\n"
            f"Câu hỏi/Yêu cầu của người dùng: {query}\n"
            "\nHãy đối chiếu tài liệu và trả lời trực diện, đúng trọng tâm câu hỏi, gắn nhãn trích dẫn [1], [2]... tương ứng:"
        )
    else:
        user_prompt = (
            f"Dưới đây là các nguồn tham khảo (tài liệu cá nhân và web):\n{context_text}"
            f"{pinpoint_block}\n"
            f"Câu hỏi/Yêu cầu của người dùng: {query}\n"
            "\nHãy trả lời trực tiếp, đúng trọng tâm câu hỏi, gắn nhãn trích dẫn tương ứng [1], [2]...:"
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


def _extract_image_ocr_text_fallback(image_base64: Optional[str]) -> str:
    """
    Trích xuất chữ trong ảnh gửi qua Chat bằng RapidOCR / Tesseract cục bộ
    để kết hợp với LLM văn bản (`qwen2.5:3b`/`7b`) ngay cả khi chưa cài model Vision.
    """
    if not image_base64:
        return ""
    try:
        raw_b64 = image_base64.split(",", 1)[-1].strip()
        img_bytes = base64.b64decode(raw_b64)
        from app.services.document_service import _ocr_png_bytes
        return (_ocr_png_bytes(img_bytes, vision_model=None) or "").strip()
    except Exception:
        return ""


def select_optimal_chat_model(
    requested_model: str,
    available_models: List[str],
    task_tier: str = "standard",
) -> Optional[str]:
    """
    Điều phối tự động 2 tầng model (Fast 3B vs. Deep 7B) theo độ phức tạp tác vụ, VRAM và lượng RAM trống:
    - Nếu người dùng đã chọn đích danh một model khác DEFAULT_LLM_MODEL và model đó có trong máy -> tôn trọng tuyệt đối.
    - Nếu đang dùng model mặc định:
      + Khi máy có `gpu_vram_mb <= 4096` hoặc `available_ram_gb < 8.5` hoặc `task_tier in ("fast", "standard")`:
        ưu tiên giữ cố định model 3B (`qwen2.5:3b` nằm trọn 100% trong 4GB VRAM, tốc độ 76 tok/s, không bị swap).
      + Khi `task_tier == "deep"` trên máy có `gpu_vram_mb >= 6144` hoặc `available_ram_gb >= 9.5`:
        ưu tiên nâng lên model 7B/8B.
    """
    if not available_models:
        return None

    req = (requested_model or "").strip()
    is_default_or_auto = not req or req == DEFAULT_LLM_MODEL or req.lower() == "auto"

    if not is_default_or_auto and req in available_models:
        return req

    try:
        from app.services.hardware_profile_service import get_active_profile_config
        cfg = get_active_profile_config()
        active_id = str(cfg.get("id") or "balanced").lower()
        specs = cfg.get("specs") or {}
        avail_ram = float(specs.get("available_ram_gb") or 8.0)
        vram_mb = int(specs.get("gpu_vram_mb") or 0)
    except Exception:
        active_id = "balanced"
        avail_ram = 8.0
        vram_mb = 0

    fast_candidates = ("qwen2.5:3b", "llama3.2:3b", "qwen2.5:1.5b", "llama3.2:1b")
    deep_candidates = ("qwen2.5:7b", "llama3.1:8b", "qwen2.5:14b")

    is_4gb_vram_or_light_machine = (
        active_id == "eco"
        or (vram_mb <= 4096 and avail_ram < 8.8)
    )

    if task_tier == "fast" or is_4gb_vram_or_light_machine or task_tier == "standard":
        for cand in fast_candidates:
            if cand in available_models:
                return cand
    elif task_tier == "deep" and active_id != "eco" and (vram_mb >= 6144 or avail_ram >= 8.8):
        for cand in deep_candidates:
            if cand in available_models:
                return cand

    return resolve_available_chat_model(req or DEFAULT_LLM_MODEL, available_models)


def _resolve_model_for_chat(
    requested_model: str,
    ollama_status: Dict[str, Any],
    image_base64: Optional[str],
    task_tier: str = "standard",
) -> tuple[str, bool]:
    """Xác định model Ollama khả dụng (kể cả fallback vision hoặc điều phối tự động 3B/7B)."""
    available = ollama_status.get("available_models") or []
    if not ollama_status.get("running"):
        return requested_model, False
    if image_base64:
        vision_chosen = resolve_available_vision_model(requested_model, available)
        if vision_chosen:
            return vision_chosen, True
        return requested_model, False
    resolved = select_optimal_chat_model(requested_model, available, task_tier=task_tier)
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
                        "keep_alive": get_recommended_keep_alive(),
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

    if not image_base64:
        direct_list_ans = _try_build_exhaustive_tabular_list_answer(query, context_chunks)
        if direct_list_ans:
            instant_sugs = _build_instant_followup_suggestions(query, citations, context_chunks)
            if instant_sugs:
                sug_block = "\n".join(f"- {s}" for s in instant_sugs)
                direct_list_ans = f"{direct_list_ans.rstrip()}\n\n---GỢI Ý TIẾP THEO---\n{sug_block}"
            return {
                "answer": direct_list_ans,
                "citations": citations,
                "model_used": model_name if model_available else "direct_tabular_extractor",
                "engine": "ollama_local" if model_available else "direct_tabular_extractor",
            }

    if image_base64 and not model_available:
        ocr_text = _extract_image_ocr_text_fallback(image_base64)
        text_fallback_model = (
            resolve_available_chat_model(DEFAULT_LLM_MODEL, ollama_status.get("available_models") or [])
            if ollama_status.get("running")
            else None
        )
        if ocr_text and text_fallback_model:
            model_name = text_fallback_model
            model_available = True
            image_base64 = None
            user_prompt = (
                f"{user_prompt}\n\n"
                f"[VĂN BẢN TRÍCH XUẤT TỪ ẢNH QUA LOCAL OCR]:\n{ocr_text}\n\n"
                "Hãy dựa vào nội dung văn bản trích xuất từ ảnh ở trên để trả lời trực tiếp câu hỏi của người dùng."
            )
        else:
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
                est_tokens = _estimate_tokens(system_prompt) + _estimate_tokens(user_prompt) + sum(
                    _estimate_tokens(m.get("content", "")) for m in history_messages
                )
                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        *history_messages,
                        user_message
                    ],
                    "stream": False,
                    "keep_alive": get_recommended_keep_alive(),
                    "options": _resolve_sampling_options(
                        query, num_ctx, max_predict, image_base64, estimated_input_tokens=est_tokens
                    ),
                }
                resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
                if resp.status_code == 200:
                    raw_answer = resp.json().get("message", {}).get("content", "")
                    answer = _sanitize_rag_output(raw_answer, len(citations))
                    if "---GỢI Ý TIẾP THEO---" not in answer:
                        instant_sugs = _build_instant_followup_suggestions(query, citations, context_chunks)
                        if instant_sugs:
                            sug_block = "\n".join(f"- {s}" for s in instant_sugs)
                            answer = f"{answer.rstrip()}\n\n---GỢI Ý TIẾP THEO---\n{sug_block}"
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
    followup_suggestions: Optional[List[str]] = None,
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

            sanitized_answer = _sanitize_rag_output(full_answer, len(citations))
            if followup_suggestions and "---GỢI Ý TIẾP THEO---" not in sanitized_answer:
                sug_block = "\n".join(f"- {s}" for s in followup_suggestions)
                sanitized_answer = f"{sanitized_answer.rstrip()}\n\n---GỢI Ý TIẾP THEO---\n{sug_block}"
            if collector is not None:
                collector["full_answer"] = sanitized_answer
                collector["citations"] = citations
                collector["model_used"] = model_name
                collector["engine"] = engine_name
            yield f"data: {json.dumps({'answer': sanitized_answer, 'done': True}, ensure_ascii=False)}\n\n"
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
                        "keep_alive": get_recommended_keep_alive(),
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

    if not image_base64:
        direct_list_ans = _try_build_exhaustive_tabular_list_answer(query, context_chunks)
        if direct_list_ans:
            instant_sugs = _build_instant_followup_suggestions(query, citations, context_chunks)
            if instant_sugs:
                sug_block = "\n".join(f"- {s}" for s in instant_sugs)
                direct_list_ans = f"{direct_list_ans.rstrip()}\n\n---GỢI Ý TIẾP THEO---\n{sug_block}"
            used_m = model_name if (ollama_status["running"] and model_available) else "direct_tabular_extractor"
            eng = "ollama_local" if (ollama_status["running"] and model_available) else "direct_tabular_extractor"
            yield f"data: {json.dumps({'citations': citations, 'model_used': used_m, 'engine': eng, 'stage': 'generating', 'stage_label': 'Đang trích xuất đầy đủ danh sách từ tài liệu...'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'delta': direct_list_ans}, ensure_ascii=False)}\n\n"
            if collector is not None:
                collector["full_answer"] = direct_list_ans
                collector["citations"] = citations
                collector["model_used"] = used_m
                collector["engine"] = eng
            yield f"data: {json.dumps({'answer': direct_list_ans, 'done': True}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return

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
        ocr_text = _extract_image_ocr_text_fallback(image_base64)
        text_fallback_model = (
            resolve_available_chat_model(DEFAULT_LLM_MODEL, ollama_status.get("available_models") or [])
            if ollama_status.get("running")
            else None
        )
        if ocr_text and text_fallback_model:
            model_name = text_fallback_model
            model_available = True
            image_base64 = None
            user_prompt = (
                f"{user_prompt}\n\n"
                f"[VĂN BẢN TRÍCH XUẤT TỪ ẢNH QUA LOCAL OCR]:\n{ocr_text}\n\n"
                "Hãy dựa vào nội dung văn bản trích xuất từ ảnh ở trên để trả lời trực tiếp câu hỏi của người dùng."
            )
        else:
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
            est_tokens = _estimate_tokens(system_prompt) + _estimate_tokens(user_prompt) + sum(
                _estimate_tokens(m.get("content", "")) for m in history_messages
            )
            instant_sugs = _build_instant_followup_suggestions(query, citations, context_chunks)
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    *history_messages,
                    user_message,
                ],
                "stream": True,
                "keep_alive": get_recommended_keep_alive(),
                "options": _resolve_sampling_options(
                    query, num_ctx, max_predict, image_base64, estimated_input_tokens=est_tokens
                ),
            }
            async for sse_line in _stream_ollama_chat(
                payload=payload,
                citations=citations,
                model_name=model_name,
                engine_name="ollama_local",
                collector=collector,
                is_disconnected=is_disconnected,
                followup_suggestions=instant_sugs,
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
        "keep_alive": get_recommended_keep_alive(),
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
