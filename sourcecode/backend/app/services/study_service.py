"""
Service AI chuyên trách sinh nội dung học tập: Tóm tắt, Quiz trắc nghiệm, Flashcards và Mindmap.
Sử dụng LLM cục bộ (Ollama) kết hợp nội dung tài liệu thực tế trong kho tri thức.
"""
import json
import logging
import os
import re
import time
from datetime import date, timedelta
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4
import httpx

from app.config import DEFAULT_LLM_MODEL, OLLAMA_BASE_URL, OLLAMA_TIMEOUT
from app.database import get_db_connection
from app.services.hardware_profile_service import get_active_profile_config, get_recommended_keep_alive
from app.services.llm_service import check_ollama_status, resolve_available_chat_model

logger = logging.getLogger(__name__)


def _resolve_document_ids(
    cursor: Any,
    workspace_id: str,
    document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
) -> List[str]:
    """Xác định danh sách tài liệu nguồn cần lấy ngữ cảnh."""
    if document_id:
        return [document_id]
    if document_ids:
        return list(dict.fromkeys([doc for doc in document_ids if doc]))

    rows = cursor.execute(
        """
        SELECT DISTINCT c.document_id
        FROM document_chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.workspace_id = ? AND COALESCE(d.is_latest, 1) = 1
        ORDER BY c.document_id
        """,
        (workspace_id,),
    ).fetchall()
    return [row["document_id"] for row in rows]


_GENERIC_FOCUS_TERMS = {
    "test",
    "quiz",
    "kiểm tra",
    "kiem tra",
    "bài kiểm tra",
    "bai kiem tra",
    "bài test",
    "bai test",
    "ôn tập",
    "on tap",
    "trắc nghiệm",
    "trac nghiem",
    "tổng hợp",
    "tong hop",
    "tất cả",
    "tat ca",
    "all",
    "demo",
    "nháp",
    "nhap",
    "đề thi",
    "de thi",
    "tóm tắt",
    "tom tat",
    "tóm tắt tài liệu",
    "tom tat tai lieu",
    "tóm tắt nội dung",
    "tom tat noi dung",
    "nội dung chính",
    "noi dung chinh",
    "ý chính",
    "y chinh",
    "tổng quan",
    "tong quan",
    "khái quát",
    "khai quat",
    "summary",
    "summarize",
}


def _is_generic_focus_prompt(focus_prompt: Optional[str]) -> bool:
    """Kiểm tra xem chuỗi chủ đề chỉ là nhãn/yêu cầu chung (vd: 'test', 'tóm tắt nội dung chính') hay chủ đề cụ thể."""
    clean = (focus_prompt or "").strip().lower()
    if not clean:
        return True
    if clean in _GENERIC_FOCUS_TERMS:
        return True
    if re.match(
        r"^(?:test|quiz|đề|de|bài|bai|kiểm tra|kiem tra|ôn tập|on tap|trắc nghiệm|trac nghiem)\s*#?\d*$",
        clean,
    ):
        return True
    if re.match(
        r"^(?:hãy\s+|xin\s+|vui\s+lòng\s+|giúp\s+mình\s+)?(?:tóm\s*tắt|tom\s*tat|tổng\s*hợp|tong\s*hop|tổng\s*quan|tong\s*quan|nội\s*dung\s*chính|noi\s*dung\s*chinh|ý\s*chính|y\s*chinh|khái\s*quát|khai\s*quat|summarize|summary)(?:\s+(?:nội\s*dung|noi\s*dung|chính|chinh|cốt\s*lõi|cot\s*loi|của|cua|trong|tài\s*liệu|tai\s*lieu|file|tệp|bài|bai|học|hoc|này|nay|đó|do|toàn\s*bộ|toan\s*bo|chi\s*tiết|chi\s*tiet|ngắn\s*gọn|ngan\s*gon))*[\.\!\?]*$",
        clean,
    ):
        return True
    if re.match(
        r"^(?:hãy\s+|xin\s+|vui\s+lòng\s+|giúp\s+mình\s+)?(?:đặt|tạo|sinh|làm)\s+\d*\s*(?:câu\s+hỏi|quiz|đề)\s+(?:ôn\s+tập|trắc\s+nghiệm|kiểm\s+tra)(?:\s+(?:từ|dựa\s+trên|về|của|trong|nội\s+dung|tài\s+liệu|file|tệp))*\s*[\"'“”]?[^\"'“”]{0,120}[\"'“”]?[\.\!\?]*$",
        clean,
    ):
        return True
    return False


_STUDY_BOILERPLATE_LINE_RE = re.compile(
    r"(?i)(?:"
    r"\bvndoc(?:\.com)?\b|"
    r"\btailieu\.vn\b|"
    r"\bvietjack\b|"
    r"\bloigiaihay\b|"
    r"\bhocmai\b|"
    r"\bdownload\.vn\b|"
    r"\bmegabook(?:\.vn)?\b|"
    r"^(?:\|\s*)?(?:website|hotline|fanpage|email|zalo|sđt|điện\s*thoại|liên\s*hệ|facebook|youtube|tiktok|instagram)\s*[:\|]|"
    r"https?://\S+|"
    r"\bwww\.[a-z0-9\-]+\.[a-z]{2,}\b|"
    r"\b[a-z0-9][a-z0-9\-]{2,}\.(?:com|vn|net|org|edu\.vn|gov\.vn)\b|"
    r"(?:\bhotline\b|\bđiện\s*thoại\b|\bsđt\b)[^\n]{0,20}\d{3,}|"
    r"\b0\d{2,3}[\s\.\-]\d{3}[\s\.\-]\d{2}[\s\.\-]?\d{2}\b|"
    r"chuyên\s+gia\s+sách\s+luyện\s+thi|"
    r"tải\s+tài\s+liệu\s*,\s*văn\s+bản\s+pháp\s+luật|"
    r"biểu\s+mẫu\s+miễn\s+phí|"
    r"chúc\s+(?:các\s+)?bạn\s+(?:học|ôn\s+tập|làm\s+bài)[^.!?\n]{0,60}(?:hiệu\s+quả|tốt|thành\s+công)|"
    r"mời\s+các\s+bạn\s+cùng\s+theo\s+dõi|"
    r"hy\s+vọng\s+(?:bài\s+viết|tài\s+liệu)\s+này\s+sẽ\s+mang\s+lại|"
    r"để\s+giúp\s+các\s+bạn\s+học\s+[^.!?\n]{0,60}xin\s+giới\s+thiệu|"
    r"^trang\s+\d+(?:\s*/\s*\d+)?$|"
    r"^page\s+\d+(?:\s+of\s+\d+)?$"
    r")"
)

_FOCUS_META_STOPWORDS = {
    "tóm", "tắt", "nội", "dung", "tài", "liệu", "trong", "của", "các", "những",
    "tạo", "sinh", "làm", "cho", "tôi", "mình", "giúp", "hãy", "vui", "lòng", "đặt",
    "câu", "hỏi", "quiz", "trắc", "nghiệm", "kiểm", "tra", "ôn", "tập", "bài",
    "đề", "thi", "từ", "vựng", "thuật", "ngữ", "khái", "niệm", "định", "nghĩa",
    "nghĩa", "tiếng", "anh", "việt", "nhật", "hàn", "trung", "về", "chủ", "đề",
    "phần", "mục", "theo", "dạng", "kiểu", "mức", "độ", "tình", "huống", "vận",
    "dụng", "thực", "tế", "dễ", "nhầm", "lẫn", "phân", "biệt", "bám", "sát",
    "tập", "trung", "vào", "chỉ", "ưu", "tiên", "sang", "cần", "muốn", "này",
    "file", "tệp", "trang", "pdf", "docx", "xlsx", "txt", "doc", "pptx",
}


def _is_boilerplate_study_line(line: str) -> bool:
    """Nhận diện dòng watermark/header/footer quảng cáo web không mang giá trị kiến thức."""
    clean = (line or "").strip()
    if not clean:
        return True
    if re.match(r"^(?:https?://|www\.)\S+$", clean, flags=re.IGNORECASE):
        return True
    if re.match(r"^(?:[-•*]\s*)?\[(?:trang|page)\s+\d+\]", clean, flags=re.IGNORECASE):
        return True
    if re.match(r"^\[CÂY\s+MỤC\s+LỤC\b", clean, flags=re.IGNORECASE):
        return True
    if re.search(r"(?i)danh\s+mục\s+\d+\s+chương\s*/\s*điều\s*/\s*mục\s+chính", clean):
        return True
    # Loại bỏ banner tên trung tâm / đơn vị biên soạn lặp đầu trang dạng "Tên A | Tên B & Tên C"
    if "|" in clean and "&" in clean and "/" not in clean and len(clean) < 110 and not re.search(r"\d{2,}", clean):
        return True
    if _STUDY_BOILERPLATE_RE_MATCH := _STUDY_BOILERPLATE_LINE_RE.search(clean):
        # Giữ lại nếu dòng rất dài và có chứa nhiều mệnh đề học thuật tách biệt, nhưng cắt phần câu rác ở mức câu
        if len(clean) < 220 and _STUDY_BOILERPLATE_RE_MATCH:
            return True
    return False


def _clean_study_chunk_text(text: str) -> str:
    """Loại bỏ dòng header/footer quảng cáo, lời chào/chúc sáo rỗng và lỗi font VNI cũ khỏi chunk trước khi đưa vào AI."""
    raw = (text or "").replace("ƣ", "ư").replace("Ƣ", "Ư").strip()
    if not raw:
        return ""
    cleaned_lines: List[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _is_boilerplate_study_line(stripped):
            continue
        # Nếu 1 dòng dài gộp nhiều câu mà câu đầu/cuối là quảng cáo VnDoc, lọc theo câu
        if _STUDY_BOILERPLATE_LINE_RE.search(stripped):
            kept_sents = [
                s.strip()
                for s in re.split(r"(?<=[\.\!\?])\s+", stripped)
                if s.strip() and not _STUDY_BOILERPLATE_LINE_RE.search(s)
            ]
            if not kept_sents:
                continue
            stripped = " ".join(kept_sents)
        cleaned_lines.append(stripped)
    return "\n".join(cleaned_lines).strip()


def _extract_requested_pages(focus_prompt: Optional[str]) -> List[int]:
    """Trích xuất danh sách số trang nếu người dùng chỉ định rõ (VD: 'trang 2', 'trang 2-4')."""
    if not focus_prompt:
        return []
    pages: set[int] = set()
    for m in re.finditer(r"(?i)\b(?:trang|page)\s*(\d{1,4})(?:\s*(?:-|–|đến|tới|to)\s*(\d{1,4}))?\b", focus_prompt):
        p1 = int(m.group(1))
        p2 = int(m.group(2)) if m.group(2) else p1
        if 1 <= p1 <= 2000 and 1 <= p2 <= 2000:
            lo, hi = min(p1, p2), min(max(p1, p2), min(p1, p2) + 20)
            for p in range(lo, hi + 1):
                pages.add(p)
    return sorted(pages)


def _is_low_value_header_chunk(text: str) -> bool:
    """Phát hiện các chunk mục lục ảo ([CÂY MỤC LỤC...]) hoặc tiêu đề cột lặp lại trong bảng Excel."""
    clean = (text or "").strip()
    if not clean:
        return True
    lower = clean.lower()
    if lower.startswith("[cây mục lục") or "chương / điều / mục chính trong toàn bộ tài liệu" in lower:
        return True
    if len(re.findall(r"(?m)^\s*(?:[-•*]\s*)?\[(?:trang|page)\s+\d+\]", clean, flags=re.IGNORECASE)) >= 2:
        return True
    if lower.count("stt | kanji | hiragana | meaning") >= 3:
        non_header = re.sub(r"(?i)stt\s*\|\s*kanji\s*\|\s*hiragana\s*\|\s*meaning\s*\|?", "", clean).strip()
        if len(non_header) < 40:
            return True
    return False


def _get_document_context_items(
    workspace_id: str,
    document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    max_chunks: int = 12,
    max_chars: int = 6000,
    focus_prompt: Optional[str] = None,
    numbered_sources: bool = False,
) -> tuple[str, List[Dict[str, Any]]]:
    """
    Trích xuất ngữ cảnh tài liệu kèm metadata nguồn (document_id, page_number, chunk_index, snippet)
    để phục vụ sinh nội dung học tập và đối chiếu Citation.
    """
    source_refs: List[Dict[str, Any]] = []
    parts: List[str] = []
    seen_chunks: set[tuple[Optional[str], Optional[int]]] = set()
    total_len = 0

    def _append_chunk(
        c_text: str,
        doc_id: Optional[str],
        doc_name: str,
        page_num: int,
        chunk_idx: Optional[int],
    ) -> bool:
        nonlocal total_len
        clean_text = _clean_study_chunk_text(c_text)
        if not clean_text or _is_low_value_header_chunk(clean_text):
            return True
        key = (doc_id, chunk_idx)
        if chunk_idx is not None and key in seen_chunks:
            return True
        seen_chunks.add(key)

        ref_idx = len(source_refs) + 1
        prefix = (
            f"[Nguồn {ref_idx} · {doc_name} - Trang {page_num}]"
            if numbered_sources
            else f"[{doc_name} - Trang {page_num}]"
        )
        part = f"{prefix}:\n{clean_text}"
        remaining = max_chars - total_len
        if remaining <= 0:
            return False
        if len(part) > remaining:
            part = part[:remaining]
            total_len = max_chars
        else:
            total_len += len(part)

        parts.append(part)
        source_refs.append(
            {
                "ref_index": ref_idx,
                "documentId": doc_id,
                "documentName": doc_name,
                "pageNumber": page_num,
                "chunkIndex": chunk_idx,
                "snippet": clean_text[:280].strip(),
                "_search_text": clean_text.lower(),
                "_raw_text": clean_text,
            }
        )
        return total_len < max_chars and len(source_refs) < max_chunks

    # 1. Nếu có yêu cầu trọng tâm thực sự, ưu tiên Trang chỉ định / Positional / FTS5 nhưng vẫn chừa chỗ lấy mẫu toàn tài liệu
    semantic_focus = (
        focus_prompt.strip()
        if focus_prompt and not _is_generic_focus_prompt(focus_prompt)
        else None
    )
    if semantic_focus:
        try:
            requested_pages = _extract_requested_pages(semantic_focus)
            if requested_pages:
                conn_pg = get_db_connection()
                try:
                    cur_pg = conn_pg.cursor()
                    resolved_pg_ids = _resolve_document_ids(cur_pg, workspace_id, document_id, document_ids)
                    if resolved_pg_ids:
                        doc_ph = ",".join("?" for _ in resolved_pg_ids)
                        pg_ph = ",".join("?" for _ in requested_pages)
                        pg_rows = cur_pg.execute(
                            f"""
                            SELECT c.content, c.document_id, d.file_name, c.page_number, c.chunk_index
                            FROM document_chunks c
                            JOIN documents d ON d.id = c.document_id
                            WHERE c.workspace_id = ?
                              AND c.document_id IN ({doc_ph})
                              AND c.page_number IN ({pg_ph})
                            ORDER BY c.page_number ASC, c.chunk_index ASC
                            LIMIT ?
                            """,
                            (workspace_id, *resolved_pg_ids, *requested_pages, max_chunks),
                        ).fetchall()
                        for row in pg_rows:
                            ok = _append_chunk(
                                str(row["content"] or ""),
                                row["document_id"],
                                str(row["file_name"] or "Tài liệu"),
                                int(row["page_number"] or 1),
                                row["chunk_index"],
                            )
                            if not ok:
                                break
                finally:
                    conn_pg.close()
                if source_refs:
                    return "\n\n".join(parts), source_refs

            from app.services.retrieval_service import (
                detect_positional_intent,
                detect_section_intent,
                search_positional_chunks,
                search_section_chunks,
            )

            sec_intent = detect_section_intent(semantic_focus, None)
            if sec_intent:
                sec_type, sec_num = sec_intent
                sec_chunks = search_section_chunks(
                    workspace_id=workspace_id,
                    sec_type=sec_type,
                    sec_num=sec_num,
                    max_chunks=max_chunks,
                    document_id=document_id,
                    document_ids=document_ids,
                    query=semantic_focus,
                )
                for c in sec_chunks:
                    ok = _append_chunk(
                        str(c.get("content") or ""),
                        c.get("document_id"),
                        str(c.get("document_name") or "Tài liệu"),
                        int(c.get("page_number") or 1),
                        c.get("chunk_index"),
                    )
                    if not ok:
                        break
                if source_refs:
                    return "\n\n".join(parts), source_refs

            pos_intent = detect_positional_intent(semantic_focus)
            if pos_intent:
                pos_type, letter_filter = pos_intent
                pos_chunks = search_positional_chunks(
                    workspace_id=workspace_id,
                    position=pos_type,
                    letter_filter=letter_filter,
                    max_chunks=min(max_chunks, 6),
                    document_id=document_id,
                    document_ids=document_ids,
                )
                for r in pos_chunks:
                    ok = _append_chunk(
                        str(r.get("content") or ""),
                        r.get("document_id"),
                        str(r.get("document_name") or "Tài liệu"),
                        int(r.get("page_number") or 1),
                        r.get("chunk_index"),
                    )
                    if not ok:
                        break
                if source_refs:
                    return "\n\n".join(parts), source_refs

            tokens = [
                t
                for t in re.findall(r"[\w]{2,}", semantic_focus, flags=re.UNICODE)
                if t.lower() not in _FOCUS_META_STOPWORDS and not t.isdigit()
            ]
            if tokens:
                fts_query = " OR ".join(f'"{t}"' for t in tokens[:8])
                fts_limit = max(3, int(max_chunks * 0.6))
                conn_fts = get_db_connection()
                try:
                    cur_fts = conn_fts.cursor()
                    resolved_fts_ids = _resolve_document_ids(cur_fts, workspace_id, document_id, document_ids)
                    if resolved_fts_ids:
                        placeholders = ",".join("?" for _ in resolved_fts_ids)
                        fts_rows = cur_fts.execute(
                            f"""
                            SELECT c.content, c.document_id, d.file_name, c.page_number, c.chunk_index
                            FROM chunks_fts f
                            JOIN document_chunks c ON c.id = f.chunk_id
                            JOIN documents d ON d.id = c.document_id
                            WHERE f.workspace_id = ?
                               AND c.document_id IN ({placeholders})
                               AND chunks_fts MATCH ?
                            ORDER BY bm25(chunks_fts)
                            LIMIT ?
                            """,
                            (workspace_id, *resolved_fts_ids, fts_query, fts_limit),
                        ).fetchall()
                        for row in fts_rows:
                            ok = _append_chunk(
                                str(row["content"] or ""),
                                row["document_id"],
                                str(row["file_name"] or "Tài liệu"),
                                int(row["page_number"] or 1),
                                row["chunk_index"],
                            )
                            if not ok:
                                break
                finally:
                    conn_fts.close()

            if len(source_refs) >= max_chunks or total_len >= max_chars:
                return "\n\n".join(parts), source_refs
        except Exception as exc:
            logger.debug("Truy vấn nhanh FTS5 không khớp, bổ sung bằng spanning sampling: %s", exc)

    # 2. Spanning Sampling: Lấy mẫu trải đều qua toàn bộ tài liệu trong phạm vi đã chọn
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        resolved_ids = _resolve_document_ids(cursor, workspace_id, document_id, document_ids)
        if not resolved_ids:
            return "\n\n".join(parts), source_refs

        per_doc = max(1, max_chunks // len(resolved_ids))

        for doc_id in resolved_ids:
            if total_len >= max_chars or len(source_refs) >= max_chunks:
                break

            total_row = cursor.execute(
                "SELECT COUNT(*) FROM document_chunks WHERE workspace_id = ? AND document_id = ?",
                (workspace_id, doc_id),
            ).fetchone()
            total_doc_chunks = total_row[0] if total_row else 0
            if total_doc_chunks == 0:
                continue

            fetch_target = min(total_doc_chunks, per_doc + 2)
            if total_doc_chunks <= fetch_target:
                rows = cursor.execute(
                    """
                    SELECT c.content, c.document_id, d.file_name, c.page_number, c.chunk_index
                    FROM document_chunks c
                    JOIN documents d ON d.id = c.document_id
                    WHERE c.workspace_id = ? AND c.document_id = ?
                    ORDER BY c.chunk_index ASC
                    """,
                    (workspace_id, doc_id),
                ).fetchall()
            else:
                step = (total_doc_chunks - 1) / max(1, fetch_target - 1)
                sampled_indices = sorted(list({round(i * step) for i in range(fetch_target)}))
                placeholders = ",".join("?" for _ in sampled_indices)
                rows = cursor.execute(
                    f"""
                    SELECT c.content, c.document_id, d.file_name, c.page_number, c.chunk_index
                    FROM document_chunks c
                    JOIN documents d ON d.id = c.document_id
                    WHERE c.workspace_id = ? AND c.document_id = ? AND c.chunk_index IN ({placeholders})
                    ORDER BY c.chunk_index ASC
                    """,
                    (workspace_id, doc_id, *sampled_indices),
                ).fetchall()

            for row in rows:
                ok = _append_chunk(
                    str(row["content"] or ""),
                    row["document_id"],
                    str(row["file_name"] or "Tài liệu"),
                    int(row["page_number"] or 1),
                    row["chunk_index"],
                )
                if not ok:
                    break

        return "\n\n".join(parts), source_refs
    finally:
        conn.close()


def _get_document_context(
    workspace_id: str,
    document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    max_chunks: int = 12,
    max_chars: int = 6000,
    focus_prompt: Optional[str] = None,
) -> str:
    """
    Trích xuất nội dung văn bản thực từ các chunk của tài liệu trong database.
    """
    text, _ = _get_document_context_items(
        workspace_id=workspace_id,
        document_id=document_id,
        document_ids=document_ids,
        max_chunks=max_chunks,
        max_chars=max_chars,
        focus_prompt=focus_prompt,
        numbered_sources=False,
    )
    return text


def _parse_json_response(raw: str) -> Any:
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


def _normalize_mindmap_node(node: Any, depth: int, max_depth: int) -> Optional[Dict[str, Any]]:
    """Chuẩn hoá node mindmap do AI trả về về cấu trúc an toàn cho frontend."""
    if not isinstance(node, dict):
        return None
    label = str(node.get("label") or node.get("name") or node.get("title") or "").strip()
    if not label:
        return None

    normalized: Dict[str, Any] = {
        "id": f"ai-mm-{uuid4().hex[:8]}",
        "label": label[:160],
    }
    detail = node.get("detail") or node.get("description")
    if detail:
        normalized["detail"] = str(detail).strip()[:400]

    if depth < max_depth:
        children = node.get("children") or node.get("nodes") or []
        if isinstance(children, list):
            normalized_children = []
            for child in children[:6]:
                normalized_child = _normalize_mindmap_node(child, depth + 1, max_depth)
                if normalized_child:
                    normalized_children.append(normalized_child)
            if normalized_children:
                normalized["children"] = normalized_children

    return normalized


async def _ensure_ollama_chat_model(
    requested_model: str = DEFAULT_LLM_MODEL,
) -> tuple[Optional[str], Optional[str]]:
    """Kiểm tra dịch vụ Ollama cục bộ và chọn model chat thực tế khả dụng."""
    status = await check_ollama_status()
    if not status["running"]:
        return None, "Dịch vụ AI Ollama chưa chạy. Hãy khởi động Ollama để sinh nội dung AI."

    chosen_model = resolve_available_chat_model(requested_model, status["available_models"])
    if not chosen_model:
        return (
            None,
            "Ollama đang chạy nhưng chưa có model chat khả dụng (ví dụ: `ollama pull qwen2.5:3b`).",
        )
    return chosen_model, None


def _get_study_runtime_budget() -> Dict[str, Any]:
    """Lấy ngưỡng context và token sinh theo hồ sơ phần cứng hiện hành (Eco / Balanced / Performance)."""
    profile = get_active_profile_config()
    profile_id = str(profile.get("id") or "balanced").lower()
    num_ctx = int(profile.get("num_ctx") or 4096)
    profile_num_predict = int(profile.get("num_predict") or 1200)
    if profile_id == "eco":
        summary_max_chars = 1500
        summary_max_chunks = 6
        summary_num_predict = min(profile_num_predict, 450)
    elif profile_id == "performance":
        summary_max_chars = 4500
        summary_max_chunks = 10
        summary_num_predict = min(profile_num_predict, 900)
    else:
        summary_max_chars = 3200
        summary_max_chunks = 8
        summary_num_predict = min(profile_num_predict, 700)
    return {
        "profile_id": profile_id,
        "num_ctx": num_ctx,
        "num_predict": profile_num_predict,
        "summary_max_chars": summary_max_chars,
        "summary_max_chunks": summary_max_chunks,
        "summary_num_predict": summary_num_predict,
    }


async def _call_ollama_chat(
    system_prompt: str,
    user_prompt: str,
    model: str = DEFAULT_LLM_MODEL,
    json_mode: bool = False,
    timeout_sec: float = OLLAMA_TIMEOUT,
    num_predict: int = 1200,
    allow_extended_predict: bool = False,
    stream_salvage: bool = False,
) -> str:
    budget = _get_study_runtime_budget()
    if allow_extended_predict:
        effective_num_predict = min(num_predict, 1800)
        effective_num_ctx = max(int(budget["num_ctx"]), 3072)
    else:
        effective_num_predict = (
            min(num_predict, budget["num_predict"])
            if budget["profile_id"] == "eco" and num_predict > budget["num_predict"]
            else num_predict
        )
        effective_num_ctx = int(budget["num_ctx"])
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "keep_alive": get_recommended_keep_alive(),
        "options": {
            "temperature": 0.45 if json_mode else 0.7,
            "top_p": 0.9,
            "num_predict": effective_num_predict,
            "num_ctx": effective_num_ctx,
        },
    }
    if json_mode:
        payload["format"] = "json"

    timeout = httpx.Timeout(timeout_sec, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        use_stream = (
            stream_salvage
            and type(client).__name__ == "AsyncClient"
            and type(client).__module__.startswith("httpx")
        )
        if use_stream:
            payload["stream"] = True
            stream_timeout = httpx.Timeout(
                connect=10.0,
                read=min(max(timeout_sec, 35.0), 75.0),
                write=15.0,
                pool=10.0,
            )
            collected: List[str] = []
            stream_deadline = time.monotonic() + max(timeout_sec, 20.0)
            try:
                async with client.stream(
                    "POST",
                    f"{OLLAMA_BASE_URL}/api/chat",
                    json=payload,
                    timeout=stream_timeout,
                ) as resp:
                    if resp.status_code >= 400:
                        body_bytes = await resp.aread()
                        detail = body_bytes.decode("utf-8", errors="ignore").strip()[:300]
                        raise RuntimeError(f"Ollama trả về lỗi {resp.status_code}: {detail or resp.reason_phrase}")
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            chunk_data = json.loads(line)
                        except Exception:
                            continue
                        tok = str(chunk_data.get("message", {}).get("content") or "")
                        if tok:
                            collected.append(tok)
                        if chunk_data.get("done") or time.monotonic() >= stream_deadline:
                            break
            except Exception:
                # Nếu đã stream được một phần JSON (ví dụ chạm trần timeout), giữ lại để cứu hộ các câu đã hoàn thiện
                partial = "".join(collected).strip()
                if len(partial) >= 60:
                    return partial
                raise
            content = "".join(collected).strip()
            if not content:
                raise ValueError("Phản hồi AI rỗng")
            return content

        resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        if resp.status_code >= 400:
            detail = ""
            try:
                detail = str(resp.json().get("error") or "").strip()
            except Exception:
                detail = resp.text.strip()[:300]
            raise RuntimeError(f"Ollama trả về lỗi {resp.status_code}: {detail or resp.reason_phrase}")
        content = resp.json().get("message", {}).get("content", "").strip()
        if not content:
            raise ValueError("Phản hồi AI rỗng")
        return content


def _prepare_summary_prompts(
    workspace_id: str,
    document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    focus_prompt: Optional[str] = None,
) -> tuple[str, str, str]:
    """Chuẩn bị ngữ cảnh tinh gọn theo hồ sơ phần cứng và cặp system/user prompt cho Tóm tắt AI."""
    budget = _get_study_runtime_budget()
    summary_max_chars = int(budget["summary_max_chars"])
    context, source_refs = _get_document_context_items(
        workspace_id=workspace_id,
        document_id=document_id,
        document_ids=document_ids,
        max_chunks=int(budget["summary_max_chunks"]),
        max_chars=summary_max_chars,
        focus_prompt=focus_prompt,
        numbered_sources=False,
    )
    clean_focus = (focus_prompt or "").strip()
    semantic_focus = clean_focus if clean_focus and not _is_generic_focus_prompt(clean_focus) else None
    primary_doc = source_refs[0]["documentName"] if source_refs else "Tài liệu học tập"
    title_label = semantic_focus or clean_focus or primary_doc
    title_suffix = (title_label[:42] + "...") if len(title_label) > 42 else title_label
    summary_title = f"Tóm tắt AI · {title_suffix}"

    if not context:
        return "", "", summary_title

    vocab_entries = _extract_vocab_entries(source_refs)
    if len(vocab_entries) >= 8:
        sampled_lines: List[str] = [f"Tài liệu từ vựng: {primary_doc} (mẫu từ vựng tiêu biểu):"]
        step = max(1, len(vocab_entries) // 12)
        for idx in range(0, len(vocab_entries), step):
            ve = vocab_entries[idx]
            sampled_lines.append(f"- {ve['term']} ({ve['reading']}): {ve['meaning']}")
            if len(sampled_lines) >= 13:
                break
        effective_context = "\n".join(sampled_lines)[:summary_max_chars]
    else:
        effective_context = context[:summary_max_chars]

    system_prompt = (
        "Bạn là Trợ lý Học tập AI. Tóm tắt ngắn gọn tài liệu bằng tiếng Việt (Markdown) theo 3 mục:\n"
        "# 📌 Tổng Quan Cốt Lõi\n"
        "## 🔑 Các Luận Điểm & Kiến Thức Chính\n"
        "## 🎯 Ghi Nhớ & Ứng Dụng"
    )

    user_prompt = f"TÀI LIỆU:\n{effective_context}\n\n"
    if semantic_focus:
        user_prompt += f"TRỌNG TÂM: {semantic_focus}\n\n"
    user_prompt += "Tóm tắt súc tích bằng tiếng Việt:"
    return system_prompt, user_prompt, summary_title


async def generate_ai_summary(
    workspace_id: str,
    document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    focus_prompt: Optional[str] = None,
    model: str = DEFAULT_LLM_MODEL,
) -> Dict[str, Any]:
    """
    Sinh bản tóm tắt học tập có cấu trúc Markdown từ tài liệu thực (tối ưu tốc độ phản hồi trên CPU).
    """
    system_prompt, user_prompt, summary_title = _prepare_summary_prompts(
        workspace_id, document_id, document_ids, focus_prompt
    )
    if not user_prompt:
        return {
            "title": "Tóm tắt tài liệu",
            "markdown": "Chưa tìm thấy nội dung văn bản từ các tài liệu được chọn. Vui lòng kiểm tra lại tài liệu đã tải lên.",
            "is_mock": False,
        }

    chosen_model, model_error = await _ensure_ollama_chat_model(model)
    if model_error or not chosen_model:
        return {
            "title": "Tóm tắt tài liệu",
            "markdown": "",
            "error": model_error or "Dịch vụ AI Ollama chưa chạy.",
            "is_mock": True,
        }

    budget = _get_study_runtime_budget()
    try:
        markdown_res = await _call_ollama_chat(
            system_prompt,
            user_prompt,
            model=chosen_model,
            num_predict=int(budget["summary_num_predict"]),
        )
        return {
            "title": summary_title,
            "markdown": markdown_res,
            "is_mock": False,
        }
    except Exception as exc:
        logger.exception("Lỗi khi sinh tóm tắt bằng AI: %s", exc)
        return {
            "title": "Tóm tắt tài liệu",
            "markdown": "",
            "error": f"Quá trình sinh tóm tắt gặp lỗi: {str(exc)}",
            "is_mock": True,
        }


async def stream_ai_summary(
    workspace_id: str,
    document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    focus_prompt: Optional[str] = None,
    model: str = DEFAULT_LLM_MODEL,
) -> AsyncIterator[str]:
    """
    Stream bản tóm tắt học tập theo thời gian thực (SSE) để hiển thị tức thì từng câu ngay khi AI đang viết.
    """
    system_prompt, user_prompt, summary_title = _prepare_summary_prompts(
        workspace_id, document_id, document_ids, focus_prompt
    )
    if not user_prompt:
        yield f"data: {json.dumps({'type': 'done', 'title': 'Tóm tắt tài liệu', 'markdown': 'Chưa tìm thấy nội dung văn bản từ các tài liệu được chọn.', 'is_mock': False}, ensure_ascii=False)}\n\n"
        return

    chosen_model, model_error = await _ensure_ollama_chat_model(model)
    if model_error or not chosen_model:
        yield f"data: {json.dumps({'type': 'error', 'title': 'Tóm tắt tài liệu', 'error': model_error or 'Dịch vụ AI Ollama chưa chạy.', 'is_mock': True}, ensure_ascii=False)}\n\n"
        return

    yield f"data: {json.dumps({'type': 'meta', 'title': summary_title, 'is_mock': False}, ensure_ascii=False)}\n\n"

    budget = _get_study_runtime_budget()
    payload: Dict[str, Any] = {
        "model": chosen_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": True,
        "keep_alive": get_recommended_keep_alive(),
        "options": {
            "temperature": 0.7,
            "top_p": 0.9,
            "num_predict": int(budget["summary_num_predict"]),
            "num_ctx": int(budget["num_ctx"]),
        },
    }

    collected: List[str] = []
    timeout = httpx.Timeout(OLLAMA_TIMEOUT, connect=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", f"{OLLAMA_BASE_URL}/api/chat", json=payload) as resp:
                if resp.status_code >= 400:
                    body_bytes = await resp.aread()
                    detail = body_bytes.decode("utf-8", errors="ignore").strip()[:300]
                    raise RuntimeError(f"Ollama trả về lỗi {resp.status_code}: {detail or resp.reason_phrase}")

                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk_data = json.loads(line)
                    except Exception:
                        continue
                    token = str(chunk_data.get("message", {}).get("content") or "")
                    if token:
                        collected.append(token)
                        yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"
                    if chunk_data.get("done"):
                        break

        full_md = "".join(collected).strip()
        yield f"data: {json.dumps({'type': 'done', 'title': summary_title, 'markdown': full_md, 'is_mock': False}, ensure_ascii=False)}\n\n"
    except Exception as exc:
        logger.exception("Lỗi khi stream tóm tắt bằng AI: %s", exc)
        yield f"data: {json.dumps({'type': 'error', 'title': 'Tóm tắt tài liệu', 'error': f'Quá trình sinh tóm tắt gặp lỗi: {str(exc)}', 'is_mock': True}, ensure_ascii=False)}\n\n"


_VOCAB_ROW_PATTERN = re.compile(
    r"(?:^|\||\s)(\d{1,4})\s*\|\s*([^|\n]{1,35}?)\s*\|\s*([^|\n]{1,40}?)\s*\|\s*([^|\n]{2,90}?)(?=\s*(?:\|\s*\d{1,4}\s*\||\s+\d{1,4}\s*\||\r?\n|$))"
)
_IPA_VOCAB_LINE_PATTERN = re.compile(
    r"^(?:[-•*]\s*|\d{1,4}[\.\)]\s*)?"
    r"([A-Za-z][A-Za-z0-9\s\-\'\.\(\),]{0,68}?)\s+"
    r"(/[^/\n]{1,42}/(?:\s*(?:,|;|or)?\s*/[^/\n]{1,42}/)*)\s+"
    r"([^\n]{2,140})$"
)
_IPA_POS_SPLIT_RE = re.compile(
    r"^(?P<word>[A-Za-z][A-Za-z0-9\s\-\'\.]{0,38}?)\s+"
    r"(?P<pos>(?:(?:modal|aux|linking|phrasal)\s+)?(?:n|v|adj|adv|prep|conj|pron|det|num|abbr|interj|excl|exclamation|idiom)\."
    r"(?:[\s,;]*(?:(?:modal|aux|linking|phrasal)\s+)?(?:n|v|adj|adv|prep|conj|pron|det|num|abbr|interj|excl)\.)*"
    r"(?:\s*\([^\(\)]{1,40}\))?)$",
    flags=re.IGNORECASE,
)
_GLOSSARY_LINE_PATTERN = re.compile(
    r"^(?:[-•*]\s*|\d{1,3}[\.\)]\s*)?([A-Za-zÀ-ỹ0-9][A-Za-zÀ-ỹ0-9\s\-\'\/\(\),\.]{0,58}?)\s*(?::|;|–|—|\s-\s)\s*([^\n]{2,115})$"
)


def _has_balanced_delimiters(text: str) -> bool:
    """Kiểm tra dấu ngoặc (), [], và dấu phiên âm IPA /.../ cân bằng, tránh chuỗi bị cắt dở (VD: '/ə'tə' hoặc 'ni/')."""
    s = (text or "").strip()
    if not s:
        return False
    for open_ch, close_ch in (("(", ")"), ("[", "]")):
        depth = 0
        for ch in s:
            if ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth < 0:
                    return False
        if depth != 0:
            return False
    # Đếm dấu '/' ở ranh giới token (phiên âm IPA /.../), không tính '/' nối giữa 2 từ như 'piano/dương cầm' hay '20/7/1954'
    ipa_opens = len(re.findall(r"(?:^|[\s\(\[])/(?=[^\s\)\]])", s))
    ipa_closes = len(re.findall(r"(?<=[^\s\(\[])/(?=$|[\s,\.;:\)\]])", s))
    if ipa_opens != ipa_closes:
        return False
    return True


def _split_ipa_headword_and_pos(left_raw: str) -> tuple[str, str]:
    """Tách từ gốc và từ loại/ghi chú trong dòng từ điển IPA (VD: 'attorney n. (especially NAmE)' -> ('attorney', 'n. (especially NAmE)'))."""
    clean = re.sub(r"\s+", " ", (left_raw or "").strip(" []-•*\t"))
    m = _IPA_POS_SPLIT_RE.match(clean)
    if m:
        return m.group("word").strip(" ,;"), m.group("pos").strip()
    return _split_glossary_headword(clean)
_NON_GLOSSARY_TERM_PREFIX_RE = re.compile(
    r"(?i)^(?:chương|bài|phần|mục|điều|khoản|bước|đoạn|ý|luận\s*điểm|trường\s*hợp|giai\s*đoạn|"
    r"lưu\s*ý|chú\s*ý|ví\s*dụ|tóm\s*tắt|kết\s*luận|mở\s*đầu|yêu\s*cầu|mục\s*tiêu|nhiệm\s*vụ|"
    r"công\s*thức|định\s*nghĩa|nguyên\s*lý|định\s*lý|nhận\s*xét|câu\s*hỏi|câu\s*\d|trang\s*\d|page\s*\d|"
    r"sheet|nguồn|hình\s*\d|bảng\s*\d|vndoc|http|www\.)\b|(?:\bsố\s*\d+|\bthứ\s*\d+)$"
)
_HEADER_WORDS = {
    "stt",
    "kanji",
    "hiragana",
    "katakana",
    "meaning",
    "nghĩa",
    "nghia",
    "từ vựng",
    "tu vung",
    "thuật ngữ",
    "thuat ngu",
    "cách đọc",
    "cach doc",
    "phiên âm",
    "phien am",
    "word",
    "term",
    "reading",
    "definition",
}


def _make_citation_from_ref(ref: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "documentId": ref.get("documentId"),
        "documentName": ref.get("documentName") or "Tài liệu",
        "pageNumber": ref.get("pageNumber") or 1,
        "chunkIndex": ref.get("chunkIndex"),
        "snippet": ref.get("snippet") or "",
    }


def _split_glossary_headword(term_raw: str) -> tuple[str, str]:
    """Tách thuật ngữ gốc và ghi chú trong ngoặc nếu có, VD: 'amp (viết tắt của amplifier)' -> ('amp', 'viết tắt của amplifier')."""
    clean = re.sub(r"\s+", " ", term_raw).strip(" []-•*\t")
    m = re.match(r"^([^\(\)]{1,42}?)\s*\(([^\(\)]{1,48})\)$", clean)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return clean, ""


def _extract_vocab_entries(source_refs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Trích xuất các mục từ vựng / thuật ngữ từ tài liệu nguồn:
    1) Bảng từ vựng 4 cột (STT | Từ | Cách đọc | Nghĩa)
    2) Danh sách thuật ngữ / từ vựng song ngữ dạng dòng (`term: nghĩa`, `term; nghĩa`, `term - nghĩa`) hoặc bảng 2-3 cột.
    """
    entries: List[Dict[str, Any]] = []
    glossary_candidates: List[Dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for ref in source_refs:
        raw_text = str(ref.get("_raw_text") or ref.get("snippet") or "")
        if not raw_text:
            continue
        for match in _VOCAB_ROW_PATTERN.finditer(raw_text):
            _stt, term_raw, reading_raw, meaning_raw = match.groups()
            term = term_raw.strip().strip("[]")
            reading = reading_raw.strip().strip("[]")
            meaning = meaning_raw.strip().strip("[]")
            if not term or not reading or not meaning:
                continue
            if term.lower() in _HEADER_WORDS or reading.lower() in _HEADER_WORDS or meaning.lower() in _HEADER_WORDS:
                continue
            if re.match(r"^bài\s*\d+", term.lower()):
                continue
            if not re.search(r"[a-zA-ZÀ-ỹ]", meaning):
                continue
            key = (term.lower(), reading.lower(), meaning.lower())
            if key in seen:
                continue
            seen.add(key)
            entries.append(
                {
                    "term": term,
                    "reading": reading,
                    "meaning": meaning,
                    "note": "",
                    "is_cjk_table": True,
                    "ref": ref,
                }
            )

        for raw_line in raw_text.splitlines():
            line = raw_line.strip()
            if not line or _is_boilerplate_study_line(line):
                continue
            # Bỏ qua dòng bảng nhiều cột đã khớp ở _VOCAB_ROW_PATTERN
            if line.count("|") >= 3:
                continue

            # Ưu tiên nhận diện dòng từ điển có phiên âm IPA: `word [pos] [(note)] /IPA/ meaning`
            # (tránh để dấu ':' bên trong IPA như `/ə'tə:ni/` bị tách nhầm bởi _GLOSSARY_LINE_PATTERN)
            ipa_m = _IPA_VOCAB_LINE_PATTERN.match(line)
            if ipa_m:
                left_raw, ipa_raw, meaning_raw = ipa_m.group(1).strip(), ipa_m.group(2).strip(), ipa_m.group(3).strip()
                headword, pos_note = _split_ipa_headword_and_pos(left_raw)
                meaning_clean = re.sub(r"\s+", " ", meaning_raw).strip(" .;:")
                if (
                    headword
                    and 1 <= len(headword) <= 42
                    and len(headword.split()) <= 5
                    and headword.lower() not in _HEADER_WORDS
                    and not _NON_GLOSSARY_TERM_PREFIX_RE.search(headword)
                    and 2 <= len(meaning_clean) <= 135
                    and re.search(r"[a-zA-ZÀ-ỹ]", meaning_clean)
                    and _has_balanced_delimiters(headword)
                    and _has_balanced_delimiters(ipa_raw)
                    and _has_balanced_delimiters(meaning_clean)
                ):
                    key = (headword.lower(), ipa_raw.lower(), meaning_clean.lower())
                    if key not in seen:
                        seen.add(key)
                        glossary_candidates.append(
                            {
                                "term": headword,
                                "reading": ipa_raw,
                                "meaning": meaning_clean,
                                "note": pos_note,
                                "is_cjk_table": False,
                                "ref": ref,
                            }
                        )
                continue

            term_part = ""
            reading_part = ""
            meaning_part = ""
            if "|" in line:
                cols = [c.strip(" []") for c in line.strip("| ").split("|") if c.strip(" []")]
                if len(cols) == 2:
                    term_part, meaning_part = cols[0], cols[1]
                elif len(cols) == 3 and not cols[0].isdigit():
                    term_part, reading_part, meaning_part = cols[0], cols[1], cols[2]
            else:
                gm = _GLOSSARY_LINE_PATTERN.match(line)
                if gm:
                    term_part, meaning_part = gm.group(1).strip(), gm.group(2).strip()

            if not term_part or not meaning_part:
                continue
            # Loại trừ công thức toán học (f(x) ≥ 0, g(x) ≠ 0, dấu ngoặc nhọn hệ phương trình) để không nhận nhầm thành bảng từ vựng
            if re.search(r"[{}≥≤≠√±⇔⇒∆Δπ=]|\b[fgh]\s*\(", f"{term_part} {meaning_part}"):
                continue
            if not _has_balanced_delimiters(term_part) or not _has_balanced_delimiters(meaning_part):
                continue
            if _NON_GLOSSARY_TERM_PREFIX_RE.search(term_part):
                continue
            headword, paren_note = _split_glossary_headword(term_part)
            if not headword or len(headword) > 48 or len(headword.split()) > 7:
                continue
            if headword.lower() in _HEADER_WORDS or meaning_part.lower() in _HEADER_WORDS:
                continue
            if len(meaning_part) < 2 or len(meaning_part) > 115 or len(meaning_part.split()) > 20:
                continue
            if meaning_part.endswith(":") or "=" in meaning_part or headword.lower() == meaning_part.lower():
                continue
            if not re.search(r"[a-zA-ZÀ-ỹ]", meaning_part):
                continue

            eff_reading = reading_part.strip() if reading_part.strip() else headword
            key = (headword.lower(), eff_reading.lower(), meaning_part.lower())
            if key in seen:
                continue
            seen.add(key)
            glossary_candidates.append(
                {
                    "term": headword,
                    "reading": eff_reading,
                    "meaning": meaning_part.rstrip(" .;"),
                    "note": paren_note,
                    "is_cjk_table": False,
                    "ref": ref,
                }
            )

    # Chỉ coi các dòng glossary là bảng thuật ngữ/từ vựng song ngữ khi có >= 5 mục
    # và phần lớn từ gốc (headword) không mang dấu tiếng Việt (từ ngoại ngữ/thuật ngữ chuyên ngành/viết tắt),
    # tránh nhầm dàn ý lý thuyết tiếng Việt kiểu "Kinh tế: ...", "Chính trị: ...", "Ý nghĩa: ...".
    viet_diacritic_re = re.compile(
        r"[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]",
        flags=re.IGNORECASE,
    )
    if len(glossary_candidates) >= 5:
        foreign_or_code = [c for c in glossary_candidates if not viet_diacritic_re.search(c["term"])]
        if len(foreign_or_code) >= 5 and (len(foreign_or_code) / len(glossary_candidates)) >= 0.55:
            entries.extend(foreign_or_code)

    return entries


def _salvage_json_objects(raw_text: str, required_predicate: Any) -> List[Dict[str, Any]]:
    """Cứu dữ liệu các JSON object hoàn chỉnh thỏa mãn điều kiện ngay cả khi phản hồi bị cắt cụt."""
    salvaged: List[Dict[str, Any]] = []
    text = (raw_text or "").strip()
    if not text:
        return salvaged

    n = len(text)
    i = 0
    while i < n:
        if text[i] == "{":
            depth = 0
            in_str = False
            esc = False
            start = i
            for j in range(i, n):
                ch = text[j]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                else:
                    if ch == '"':
                        in_str = True
                    elif ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            candidate = text[start : j + 1]
                            try:
                                obj = json.loads(candidate)
                                if isinstance(obj, dict) and required_predicate(obj):
                                    salvaged.append(obj)
                                    i = j
                                    break
                            except Exception:
                                pass
                            break
        i += 1
    return salvaged


def _salvage_json_question_dicts(raw_text: str) -> List[Dict[str, Any]]:
    """Cứu dữ liệu các object câu hỏi hoàn chỉnh ngay cả khi chuỗi JSON bị cắt cụt ở cuối."""
    return _salvage_json_objects(
        raw_text,
        lambda obj: any(k in obj for k in ("prompt", "question", "cau_hoi", "text", "title"))
        and any(k in obj for k in ("options", "choices", "answers", "lua_chon", "A")),
    )


def _resolve_answer_index(raw_q: Dict[str, Any], options: List[str]) -> int:
    """Chuẩn hoá chỉ số đáp án đúng từ nhiều định dạng trả về khác nhau của LLM."""
    if not options:
        return 0

    letter_map = {"A": 0, "B": 1, "C": 2, "D": 3}

    # Ưu tiên đối chiếu chuỗi đáp án đúng tường minh (correctAnswer / answer) vì model nhỏ 3B-4B hay đếm lệch chỉ số 0-based
    for key in ("correctAnswer", "correct_answer", "answer", "dap_an"):
        ans_val = raw_q.get(key)
        if ans_val is None or isinstance(ans_val, bool):
            continue
        ans_str = re.sub(r"^[A-Da-d][\.\)\:\-]\s*", "", str(ans_val).strip()).strip()
        if not ans_str:
            continue
        upper = ans_str.upper()
        if upper in letter_map and letter_map[upper] < len(options):
            return letter_map[upper]
        for idx, opt in enumerate(options):
            if opt.strip().lower() == ans_str.lower():
                return idx
        if len(ans_str) >= 3:
            matched_idxs = [
                idx for idx, opt in enumerate(options)
                if ans_str.lower() in opt.lower() or (len(opt.strip()) >= 3 and opt.strip().lower() in ans_str.lower())
            ]
            if len(matched_idxs) == 1:
                return matched_idxs[0]

    for key in ("answerIndex", "answer_index", "correctIndex", "correct_index"):
        val = raw_q.get(key)
        if val is not None:
            if isinstance(val, int) and 0 <= val < len(options):
                return val
            val_str = str(val).strip().upper()
            if val_str in letter_map and letter_map[val_str] < len(options):
                return letter_map[val_str]
            try:
                num = int(val_str)
                if 0 <= num < len(options):
                    return num
            except ValueError:
                pass

    return 0


_BROKEN_SINGLE_OPTIONS = {
    "nam", "bắc", "trung", "đông", "tây", "ban", "ngay", "lan", "thanh", "hội",
    "đảng", "nhà", "nước", "ngày", "tháng", "năm", "sau", "trước", "trong", "ngoài",
    "theo", "với", "cho", "từ", "các", "một", "những", "được", "đã", "sẽ", "của",
    "khi", "nếu", "tuy", "nhưng", "hoặc", "hay", "về", "tại", "đến", "cũng",
}


def _is_clean_quiz_question(prompt: str, options: List[str]) -> bool:
    """Cổng kiểm định chất lượng tổng quát cho mọi câu hỏi Quiz (dù từ LLM hay fallback, áp dụng cho mọi loại tài liệu)."""
    p = (prompt or "").strip()
    if len(p) < 8:
        return False
    if p[-1] in {",", "-", "–", "—", ";", "(", "["}:
        return False
    if not _has_balanced_delimiters(p):
        return False
    if _STUDY_BOILERPLATE_LINE_RE.search(p) or re.search(r"(?i)\[(?:trang|page)\s+\d+\]", p):
        return False

    if not isinstance(options, list) or len(options) < 3:
        return False
    seen_opts: set[str] = set()
    for opt in options:
        o = (opt or "").strip()
        if not o or o.lower() in seen_opts:
            return False
        if o[-1] in {",", "-", "–", "—", ";", ":", "(", "["}:
            return False
        if not _has_balanced_delimiters(o):
            return False
        if _STUDY_BOILERPLATE_LINE_RE.search(o) or re.search(r"(?i)\[(?:trang|page)\s+\d+\]", o):
            return False
        if re.search(r"(?i)^không\s+đề\s+cập\s+trong\s+đoạn\s+này", o):
            return False
        seen_opts.add(o.lower())
    return True


def _extract_and_normalize_llm_questions(
    raw_res: str,
    source_refs: List[Dict[str, Any]],
    vocab_entries: List[Dict[str, Any]],
    seen_prompts: Optional[set[str]] = None,
    start_index: int = 0,
) -> List[Dict[str, Any]]:
    """Phân tích và lọc danh sách câu hỏi hợp lệ, bám sát tài liệu từ phản hồi JSON của LLM."""
    raw_items: List[Any] = []
    try:
        data = _parse_json_response(raw_res)
        if isinstance(data, list):
            raw_items = data
        elif isinstance(data, dict):
            for k in ("questions", "quiz", "quizQuestions", "quiz_questions", "data", "items", "cau_hoi"):
                if isinstance(data.get(k), list):
                    raw_items = data[k]
                    break
            if not raw_items:
                for v in data.values():
                    if isinstance(v, list) and v and isinstance(v[0], dict):
                        raw_items = v
                        break
            if not raw_items and any(k in data for k in ("prompt", "question", "cau_hoi")):
                raw_items = [data]
    except Exception:
        raw_items = []

    if not raw_items:
        raw_items = _salvage_json_question_dicts(raw_res)

    is_vocab_doc = len(vocab_entries) >= 8
    vocab_known_tokens: set[str] = set()
    if is_vocab_doc:
        for ve in vocab_entries:
            vocab_known_tokens.add(ve["term"].lower())
            vocab_known_tokens.add(ve["reading"].lower())
            vocab_known_tokens.add(ve["meaning"].lower())

    valid_questions: List[Dict[str, Any]] = []
    local_seen = seen_prompts if seen_prompts is not None else set()

    for q in raw_items:
        if not isinstance(q, dict):
            continue
        prompt_raw = (
            q.get("prompt")
            or q.get("question")
            or q.get("cau_hoi")
            or q.get("text")
            or q.get("title")
        )
        if not prompt_raw:
            continue
        prompt_str = str(prompt_raw).strip()
        # Gỡ thẻ nguồn nội bộ '[Nguồn 4]', '(Nguồn 6)' nếu LLM chép nhầm vào đề bài
        prompt_str = re.sub(
            r"(?:\s*(?:theo\s+định\s+nghĩa\s+)?(?:trong|ở|tại|theo)\s+)?(?:\[|\()\s*Nguồn\s*\d+\s*(?:\]|\))",
            "",
            prompt_str,
            flags=re.IGNORECASE | re.UNICODE,
        )
        prompt_str = re.sub(r"\s{2,}", " ", prompt_str).replace(" ?", "?").strip()
        if len(prompt_str) < 8:
            continue
        prompt_key = prompt_str.lower()
        if prompt_key in local_seen:
            continue

        # Loại bỏ các câu hỏi lạc đề về hệ thống RAG, câu rác quảng cáo hoặc câu hỏi đếm số dòng
        if re.search(r"(?i)\b(?:number of entries|provided data|hybrid rag|sparse retrieval|bm25|reciprocal rank)\b", prompt_str):
            if not any("hybrid rag" in (r.get("_search_text") or "") for r in source_refs):
                continue
        if _STUDY_BOILERPLATE_LINE_RE.search(prompt_str):
            continue

        raw_opts = q.get("options") or q.get("choices") or q.get("answers") or q.get("lua_chon")
        if not isinstance(raw_opts, list) and all(k in q for k in ("A", "B", "C", "D")):
            raw_opts = [q["A"], q["B"], q["C"], q["D"]]
        if not isinstance(raw_opts, list):
            continue

        cleaned_opts: List[str] = []
        has_bad_opt = False
        for opt in raw_opts:
            opt_s = re.sub(r"^[A-Da-d][\.\)\:\-]\s*", "", str(opt or "").strip()).strip()
            if not opt_s:
                continue
            if (
                re.search(r"(?i)^không\s+đề\s+cập\s+trong\s+đoạn\s+này", opt_s)
                or _STUDY_BOILERPLATE_LINE_RE.search(opt_s)
                or (not is_vocab_doc and opt_s.lower() in _BROKEN_SINGLE_OPTIONS)
            ):
                has_bad_opt = True
                break
            if opt_s.lower() not in {o.lower() for o in cleaned_opts}:
                cleaned_opts.append(opt_s)
        if has_bad_opt:
            continue
        options = cleaned_opts[:4]
        if len(options) < 3 or not _is_clean_quiz_question(prompt_str, options):
            continue

        if not is_vocab_doc:
            opt_lens = [len(o) for o in options]
            if min(opt_lens) <= 4 and max(opt_lens) >= 48:
                continue

        ans_idx = _resolve_answer_index(q, options)
        explanation = str(
            q.get("explanation")
            or q.get("giai_thich")
            or q.get("reason")
            or "Theo nội dung kiến thức trong tài liệu nguồn."
        ).strip()

        if is_vocab_doc:
            # Với tài liệu bảng từ vựng, đảm bảo câu hỏi tiếng Việt và chứa từ/nghĩa thực trong tài liệu
            if not re.search(
                r"[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]",
                prompt_str.lower(),
            ):
                continue
            combined_q = f"{prompt_str} {options[ans_idx]}".lower()
            if not any(tok in combined_q for tok in vocab_known_tokens if len(tok) >= 2):
                continue

            # Kiểm chứng xác thực answerIndex dựa trên bảng vocab_entries thật (chống model 3B lệch chỉ số đáp án)
            p_low = prompt_str.lower()
            matched_ve = None
            for ve in sorted(vocab_entries, key=lambda x: len(x.get("term") or ""), reverse=True):
                t_low = (ve.get("term") or "").strip().lower()
                r_low = (ve.get("reading") or "").strip().lower()
                if (t_low and len(t_low) >= 1 and t_low in p_low) or (r_low and len(r_low) >= 2 and r_low in p_low):
                    matched_ve = ve
                    break
            if matched_ve is not None:
                m_low = (matched_ve.get("meaning") or "").strip().lower()
                m_parts = [p.strip() for p in re.split(r"[,;/]", m_low) if len(p.strip()) >= 2]
                verified_idx: Optional[int] = None
                for o_i, opt in enumerate(options):
                    o_low = opt.strip().lower()
                    if m_low and (m_low == o_low or m_low in o_low or (len(o_low) >= 2 and o_low in m_low)):
                        verified_idx = o_i
                        break
                    if any(mp == o_low or mp in o_low for mp in m_parts):
                        verified_idx = o_i
                        break
                if verified_idx is not None:
                    ans_idx = verified_idx
                else:
                    # Câu hỏi hỏi từ trong bảng nhưng KHÔNG có phương án nào khớp nghĩa thật -> loại bỏ để fallback sinh chuẩn
                    continue
        else:
            # Với tài liệu văn xuôi/toán: nếu phần giải thích nhắc duy nhất 1 phương án và khác options[ans_idx], tự hiệu chỉnh
            exp_low = explanation.lower()
            cur_opt_low = options[ans_idx].strip().lower()
            if cur_opt_low and cur_opt_low not in exp_low:
                exp_hits = [
                    o_i for o_i, opt in enumerate(options)
                    if len(opt.strip()) >= 5 and opt.strip().lower() in exp_low
                ]
                if len(exp_hits) == 1:
                    ans_idx = exp_hits[0]

        # Phân bổ vị trí đáp án đúng (A/B/C/D) tự nhiên thay vì dồn hết vào A (giữ nguyên câu đầu tiên cho tính tất định)
        global_idx = start_index + len(valid_questions)
        shift = (global_idx * 3) % len(options)
        if shift > 0:
            correct_val = options[ans_idx]
            options = options[shift:] + options[:shift]
            ans_idx = options.index(correct_val)

        local_seen.add(prompt_key)

        item_q: Dict[str, Any] = {
            "id": f"ai-q-{global_idx + 1}",
            "prompt": prompt_str,
            "options": options,
            "answerIndex": ans_idx,
            "explanation": explanation,
        }
        citation = _resolve_question_citation(
            {
                "prompt": prompt_str,
                "explanation": explanation,
                "sourceIndex": q.get("sourceIndex") or q.get("source_index"),
            },
            source_refs,
        )
        if citation:
            item_q["citation"] = citation
        valid_questions.append(item_q)

    return valid_questions


def _pick_distinct_distractors(
    pool: List[str],
    correct_val: str,
    needed: int,
    seed_offset: int,
) -> List[str]:
    """Chọn các phương án nhiễu hợp lý, tương đồng độ dài và khác biệt nghĩa với đáp án đúng."""
    correct_clean = correct_val.strip()
    correct_norm = correct_clean.lower()
    if not pool:
        return []

    candidates: List[str] = []
    seen_norm: set[str] = {correct_norm}
    for item in pool:
        cand = (item or "").strip()
        cand_norm = cand.lower()
        if not cand or cand_norm in seen_norm:
            continue
        if len(cand_norm) >= 5 and len(correct_norm) >= 5:
            if cand_norm in correct_norm or correct_norm in cand_norm:
                continue
        seen_norm.add(cand_norm)
        candidates.append(cand)

    if not candidates:
        return []

    # Ưu tiên các phương án có độ dài gần với đáp án đúng để tránh lộ đáp án qua độ dài câu chữ
    target_len = max(4, len(correct_clean))
    close_bucket = [c for c in candidates if 0.35 <= (len(c) / target_len) <= 2.6]
    far_bucket = [c for c in candidates if c not in close_bucket]

    distractors: List[str] = []
    for bucket in (close_bucket, far_bucket):
        b_len = len(bucket)
        if b_len == 0:
            continue
        for step in range(b_len):
            cand = bucket[(seed_offset + step * 5) % b_len]
            if cand not in distractors:
                distractors.append(cand)
                if len(distractors) >= needed:
                    return distractors
    return distractors


def _detect_vocab_direction_preference(focus_prompt: Optional[str]) -> Optional[int]:
    """Phát hiện chiều hỏi từ vựng nếu người dùng yêu cầu rõ (0: từ -> nghĩa, 1: nghĩa -> từ)."""
    if not focus_prompt:
        return None
    f = focus_prompt.lower()
    if re.search(r"(?:anh\s*(?:sang|->|→)\s*việt|từ\s*(?:sang|->|→)\s*nghĩa|hỏi\s+nghĩa\s+(?:tiếng\s+việt\s+)?của)", f):
        return 0
    if re.search(r"(?:việt\s*(?:sang|->|→)\s*anh|nghĩa\s*(?:sang|->|→)\s*từ|cho\s+nghĩa\s+chọn\s+từ|chọn\s+thuật\s+ngữ)", f):
        return 1
    return None


def _prioritize_vocab_by_focus(
    vocab_entries: List[Dict[str, Any]],
    semantic_focus: Optional[str],
) -> List[Dict[str, Any]]:
    """Đưa các mục từ vựng/thuật ngữ khớp chủ đề người dùng mô tả lên đầu danh sách."""
    if not semantic_focus:
        return list(vocab_entries)
    focus_l = semantic_focus.lower()
    focus_tokens = [
        t.lower()
        for t in re.findall(r"[\w]{2,}", semantic_focus, flags=re.UNICODE)
        if t.lower() not in _FOCUS_META_STOPWORDS
    ]
    if not focus_tokens and len(focus_l) < 3:
        return list(vocab_entries)

    scored: List[tuple[int, int, Dict[str, Any]]] = []
    for idx, e in enumerate(vocab_entries):
        blob = f"{e['term']} {e['reading']} {e['meaning']} {e.get('note', '')}".lower()
        score = 0
        if focus_l in blob:
            score += 4
        for tok in focus_tokens:
            if tok in blob:
                score += 2
        scored.append((score, idx, e))

    if not any(sc > 0 for sc, _, _ in scored):
        return list(vocab_entries)
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in scored]


def _build_vocab_grounded_questions(
    vocab_entries: List[Dict[str, Any]],
    needed: int,
    existing_prompts: set[str],
    semantic_focus: Optional[str] = None,
    quiz_style: str = "auto",
    difficulty: str = "medium",
) -> List[Dict[str, Any]]:
    """Tạo câu hỏi trắc nghiệm từ vựng / thuật ngữ chuẩn xác 100% bám sát tài liệu và yêu cầu người dùng."""
    if len(vocab_entries) < 4 or needed <= 0:
        return []

    ordered_entries = _prioritize_vocab_by_focus(vocab_entries, semantic_focus)
    preferred_dir = _detect_vocab_direction_preference(semantic_focus)

    focus_tokens = [
        t.lower()
        for t in re.findall(r"[\w]{2,}", semantic_focus or "", flags=re.UNICODE)
        if t.lower() not in _FOCUS_META_STOPWORDS
    ]
    matched_count = 0
    if focus_tokens:
        for e in ordered_entries:
            blob = f"{e['term']} {e['reading']} {e['meaning']} {e.get('note', '')}".lower()
            if any(tok in blob for tok in focus_tokens):
                matched_count += 1
            else:
                break

    total_entries = len(ordered_entries)
    sampled_entries: List[Dict[str, Any]] = []
    used_indices: set[int] = set()

    if matched_count >= 4:
        for idx in range(min(matched_count, max(needed * 2, 12))):
            used_indices.add(idx)
            sampled_entries.append(ordered_entries[idx])

    sample_target = min(total_entries, max(needed * 2, 14))
    step = total_entries / max(1, sample_target)
    for i in range(sample_target):
        idx = min(total_entries - 1, int(i * step))
        if idx not in used_indices:
            used_indices.add(idx)
            sampled_entries.append(ordered_entries[idx])
    for idx, entry in enumerate(ordered_entries):
        if idx not in used_indices:
            sampled_entries.append(entry)

    meanings_pool = list(dict.fromkeys([e["meaning"] for e in ordered_entries if e["meaning"]]))
    terms_pool = list(
        dict.fromkeys(
            [
                f"{e['term']} ({e['reading']})" if e["term"] != e["reading"] else e["term"]
                for e in ordered_entries
            ]
        )
    )
    cjk_readings_pool = list(
        dict.fromkeys(
            [
                e["reading"]
                for e in ordered_entries
                if e.get("is_cjk_table")
                and e["term"] != e["reading"]
                and re.search(r"[\u3040-\u30ff]", e["reading"] or "")
            ]
        )
    )

    generated: List[Dict[str, Any]] = []
    used_terms: set[str] = set()
    base_ans_offset = len(existing_prompts) % 4
    for idx, entry in enumerate(sampled_entries):
        if len(generated) >= needed:
            break
        term = entry["term"]
        reading = entry["reading"]
        meaning = entry["meaning"]
        note = entry.get("note") or ""
        ref = entry["ref"]
        doc_name = ref.get("documentName") or "Tài liệu"
        page_num = ref.get("pageNumber") or 1

        if term.lower() in used_terms:
            continue

        has_cjk_reading = (
            bool(entry.get("is_cjk_table"))
            and term != reading
            and bool(re.search(r"[\u3040-\u30ff]", reading))
            and len(cjk_readings_pool) >= 4
        )

        if preferred_dir is not None:
            q_mode = preferred_dir
        elif quiz_style == "application" or difficulty == "hard":
            q_mode = 3 if idx % 2 == 0 else 1
        elif has_cjk_reading:
            q_mode = idx % 3
        else:
            q_mode = idx % 2

        note_hint = f" ({note})" if note and note.lower() not in meaning.lower() else ""
        if entry.get("is_cjk_table") and term != reading:
            display_word = f"「{term}」 ({reading})"
        elif term != reading:
            display_word = f"\"{term}\" ({reading})"
        else:
            display_word = f"\"{term}\"{note_hint}"

        if q_mode == 0:
            prompt = f"Trong tài liệu, thuật ngữ/từ vựng {display_word} mang ý nghĩa tiếng Việt nào sau đây?"
            correct_opt = meaning
            distractors = _pick_distinct_distractors(meanings_pool, correct_opt, 3, idx * 5 + 3)
            explanation = (
                f"Theo {doc_name} (Trang {page_num}), "
                f"{display_word} có nghĩa là \"{meaning}\"."
            )
        elif q_mode == 1:
            prompt = f"Thuật ngữ hoặc từ vựng nào trong tài liệu dùng để chỉ \"{meaning}\"?"
            correct_opt = f"{term} ({reading})" if term != reading else term
            distractors = _pick_distinct_distractors(terms_pool, correct_opt, 3, idx * 5 + 5)
            explanation = (
                f"Theo {doc_name} (Trang {page_num}), khái niệm/nghĩa \"{meaning}\" "
                f"tương ứng với {display_word}."
            )
        elif q_mode == 2 and has_cjk_reading:
            prompt = f"Cách đọc Hiragana chuẩn của từ 「{term}」 (nghĩa: \"{meaning}\") trong tài liệu là gì?"
            correct_opt = reading
            distractors = _pick_distinct_distractors(cjk_readings_pool, correct_opt, 3, idx * 5 + 7)
            explanation = (
                f"Theo bảng từ vựng trong {doc_name} (Trang {page_num}), "
                f"từ 「{term}」 (nghĩa: \"{meaning}\") được đọc là 「{reading}」."
            )
        else:
            prompt = (
                f"Khi cần diễn đạt ý nghĩa \"{meaning}\", "
                f"từ vựng hoặc thuật ngữ nào sau đây là chính xác nhất theo tài liệu?"
            )
            correct_opt = f"{term} ({reading})" if term != reading else (f"{term} ({note})" if note else term)
            alt_pool = [
                f"{e['term']} ({e['reading']})"
                if e["term"] != e["reading"]
                else (f"{e['term']} ({e.get('note')})" if e.get("note") else e["term"])
                for e in ordered_entries
            ]
            distractors = _pick_distinct_distractors(alt_pool, correct_opt, 3, idx * 7 + 2)
            explanation = (
                f"Theo {doc_name} (Trang {page_num}), \"{correct_opt}\" chính là thuật ngữ biểu đạt \"{meaning}\"."
            )

        if prompt.lower() in existing_prompts or len(distractors) < 3:
            continue

        ans_idx = (base_ans_offset + len(generated)) % 4
        options = list(distractors[:3])
        options.insert(ans_idx, correct_opt)

        existing_prompts.add(prompt.lower())
        used_terms.add(term.lower())
        generated.append(
            {
                "id": f"ai-q-vocab-{len(generated) + 1}",
                "prompt": prompt,
                "options": options,
                "answerIndex": ans_idx,
                "explanation": explanation,
                "citation": _make_citation_from_ref(ref),
            }
        )

    return generated


_VI_UPPER = "A-ZÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬĐÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ"
_VI_LOWER = "a-zàáảãạăắằẳẵặâấầẩẫậđèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ"

_GENERIC_OUTLINE_KEYS = {
    "mục tiêu", "mục đích", "nhiệm vụ", "ý nghĩa", "hạn chế", "thiếu sót", "kết quả",
    "thành tựu", "nguyên nhân", "hoàn cảnh", "bối cảnh", "diễn biến", "chủ trương",
    "nội dung", "nội dung hội nghị", "nội dung chính", "quyết định",
    "kinh tế", "chính trị", "xã hội", "đối nội", "đối ngoại", "văn hóa", "giáo dục",
    "về kinh tế", "về chính trị", "về xã hội", "về đối nội", "về đối ngoại", "về văn hóa",
    "về quân sự", "về ngoại giao", "nhiệm vụ hàng đầu", "nhiệm vụ chủ yếu", "nhiệm vụ trước mắt",
    "quân sự", "ngoại giao", "nông nghiệp", "công nghiệp", "thương nghiệp", "giao thông",
    "tích cực", "tiêu cực", "ưu điểm", "khó khăn", "cơ hội", "thách thức", "âm mưu",
    "thủ đoạn", "bản chất", "biểu hiện", "ảnh hưởng", "tác động", "đặc điểm", "nguồn gốc",
    "bài học kinh nghiệm", "công tác chuẩn bị", "lực lượng cách mạng", "lãnh đạo cách mạng",
    "động lực cách mạng", "chiến lược cách mạng", "nhiệm vụ cách mạng", "phương pháp đấu tranh",
}

_SECTION_HEADING_RE = re.compile(
    r"^(?:(?:CHƯƠNG|PHẦN|BÀI|MỤC)\s+[IVXLC0-9]+[\.:\-\s]+|[IVXLC]+\.\s+|\d+[\./]\s+|[a-d][\./\)]\s+|\*\s*)(.{4,120})$",
    flags=re.IGNORECASE,
)

_CLEAN_BULLET_PREFIX_RE = re.compile(r"^[\s\+\-\*•–—▪►●○✓è=>→]+")


def _clean_statement_text(raw_text: str) -> str:
    text = _CLEAN_BULLET_PREFIX_RE.sub("", (raw_text or "").strip())
    text = re.sub(r"\s+", " ", text).strip(" \t\r\n;")
    return text


def _capitalize_option(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return s
    return s[0].upper() + s[1:]


_DANGLING_END_WORDS = {
    "và", "của", "với", "nhưng", "mà", "để", "là", "trong", "về", "cho", "từ", "đến",
    "khi", "nếu", "bởi", "do", "tại", "theo", "các", "những", "một", "hai", "ba",
    "như", "hoặc", "hay", "trên", "dưới", "giữa", "sau", "trước", "tháng", "ngày", "năm",
    "tổ", "nền", "sự", "việc", "cuộc", "công", "bộ", "ban", "hội", "đảng",
}

_NEW_BLOCK_LINE_RE = re.compile(
    r"^(?:[\+\-\*•–—▪►●○✓è=>→]\s*|(?:CHƯƠNG|PHẦN|BÀI|MỤC)\s+[IVXLC0-9]+|[IVXLC]+\.\s+|\d+[\./]\s+|[a-d][\./\)]\s+)",
    flags=re.IGNORECASE,
)


def _unwrap_pdf_lines(raw_text: str) -> List[str]:
    """Ghép lại các dòng bị ngắt cứng theo chiều rộng trang PDF (VD: 'tháng 6-\\n1949', 'quyết liệt,\\nlà sự...') thành đoạn hoàn chỉnh."""
    merged: List[str] = []
    for raw_line in raw_text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line or _is_boilerplate_study_line(line):
            continue
        if not merged:
            merged.append(line)
            continue
        prev = merged[-1]
        is_prev_heading = bool(
            prev.endswith(":")
            or (prev.isupper() and len(prev) <= 105)
            or (
                re.match(r"^(?:CHƯƠNG|PHẦN|BÀI|[IVXLC]+\.)", prev, flags=re.IGNORECASE)
                and len(prev) <= 105
            )
        )
        is_curr_new_block = bool(
            _NEW_BLOCK_LINE_RE.match(line)
            or (line.isupper() and len(line) <= 105)
            or re.match(r"^[A-Za-zÀ-ỹ][A-Za-zÀ-ỹ\s\-]{1,28}:\s+", line)
        )
        prev_incomplete = (
            not re.search(r"[\.\!\?\:\;»\"”]$", prev)
            or prev.endswith(",")
            or prev.endswith("-")
            or prev.endswith("–")
        )
        if not is_prev_heading and not is_curr_new_block and prev_incomplete:
            if prev.endswith("-") and line and line[0].isdigit():
                merged[-1] = prev + line
            else:
                merged[-1] = f"{prev} {line}"
        else:
            merged.append(line)
    return merged


def _is_complete_statement(text: str) -> bool:
    """Đảm bảo câu/nhận định trọn ý, không bị cắt cụt giữa chừng ở dấu phẩy, gạch ngang hay hư từ cuối câu."""
    s = (text or "").strip()
    if not s:
        return False
    if s[-1] in {",", "-", "–", "—", ";", ":", "(", "[", "“", "/"}:
        return False
    words = s.rstrip(".!?\"”").split()
    if len(words) < 5:
        return False
    if words[-1].lower() in _DANGLING_END_WORDS:
        return False
    return True


def _extract_prose_statements(
    source_refs: List[Dict[str, Any]],
    min_len: int = 35,
    max_len: int = 230,
) -> List[tuple[str, str, Dict[str, Any]]]:
    """
    Tách các câu/mệnh đề học thuật trọn ý (đã ghép lại dòng gãy PDF) kèm tiêu đề mục gần nhất (section_title)
    để câu hỏi giữ đầy đủ ngữ cảnh và không có ký tự đầu dòng thừa (+, -, *).
    """
    statements: List[tuple[str, str, Dict[str, Any]]] = []
    seen_stmts: set[str] = set()

    for ref in source_refs:
        raw = _clean_study_chunk_text(str(ref.get("_raw_text") or ref.get("snippet") or ""))
        current_section = ""
        for line_clean in _unwrap_pdf_lines(raw):
            if not line_clean or _is_boilerplate_study_line(line_clean):
                continue

            # Nhận diện dòng tiêu đề mục (kết thúc bằng ':', viết hoa toàn bộ, hoặc CHƯƠNG/PHẦN/BÀI/I./II.)
            hm = _SECTION_HEADING_RE.match(line_clean)
            is_major_heading = bool(
                re.match(r"^(?:CHƯƠNG|PHẦN|BÀI|[IVXLC]+\.)", line_clean, flags=re.IGNORECASE)
                and (line_clean.isupper() or line_clean.endswith(":") or len(line_clean) <= 115)
            )
            if hm and (
                is_major_heading
                or (len(line_clean) <= 105 and (line_clean.endswith(":") or line_clean.isupper()))
            ):
                sec = _clean_statement_text(hm.group(1)).rstrip(".:;")
                if 5 <= len(sec) <= 95 and sec.lower() not in _GENERIC_OUTLINE_KEYS:
                    current_section = sec
                continue

            if line_clean.endswith(":") and len(line_clean) <= 85:
                sec = _clean_statement_text(line_clean).rstrip(".:;")
                if 5 <= len(sec) <= 80 and sec.lower() not in _GENERIC_OUTLINE_KEYS:
                    current_section = sec
                continue

            for part in re.split(r"(?<=[\.\!\?])\s+", line_clean):
                clean = _clean_statement_text(part)
                if not (min_len <= len(clean) <= max_len):
                    continue
                if _is_boilerplate_study_line(clean) or not _is_complete_statement(clean):
                    continue
                if current_section and clean.lower() == current_section.lower():
                    continue
                if clean.lower() not in seen_stmts:
                    seen_stmts.add(clean.lower())
                    statements.append((clean, current_section, ref))
    return statements


_CONCEPT_DEF_PATTERN = re.compile(
    r"^([A-Za-zÀ-ỹ0-9][A-Za-zÀ-ỹ0-9\s\-\(\)\/]{2,60}?)\s+"
    r"(?:là|bao\s+gồm|gồm\s+có|được\s+hiểu\s+là|được\s+định\s+nghĩa\s+là|có\s+nhiệm\s+vụ|có\s+vai\s+trò|nhằm|dùng\s+để)\s+"
    r"(.{18,165})$",
    flags=re.IGNORECASE,
)

_OUTLINE_KV_PATTERN = re.compile(
    r"^([A-Za-zÀ-ỹ0-9][A-Za-zÀ-ỹ0-9\s\-\(\)\/,]{2,52}?)\s*:\s*([^\n]{20,165})$"
)

_TIMELINE_DATE_RE = re.compile(
    r"(?i)\b("
    r"(?:ngày\s+)?\d{1,2}\s*[/\-\.]\s*\d{1,2}\s*[/\-\.]\s*\d{4}"
    r"|(?:tháng\s+)\d{1,2}\s*[/\-\.]\s*\d{4}"
    r"|(?:năm\s+)\d{4}"
    r"|(?:từ\s+(?:năm\s+)?)?\d{4}\s*[–\-]\s*\d{4}"
    r")\b"
)

_PROPER_PHRASE_RE = re.compile(
    rf"(?<![{_VI_UPPER}{_VI_LOWER}])"
    rf"([{_VI_UPPER}][{_VI_LOWER}\-]{{1,18}}(?:\s+[{_VI_UPPER}][{_VI_LOWER}\-]{{1,18}}){{1,4}})"
    rf"(?![{_VI_UPPER}{_VI_LOWER}])"
)

_ACRONYM_RE = re.compile(r"(?<![A-Za-zÀ-ỹ])([A-Z]{2,7}(?:-[A-Z0-9]{1,4})?)(?![A-Za-zÀ-ỹ])")
_QUOTED_CONCEPT_RE = re.compile(r"[\"“”]([^\"“”\n]{6,52})[\"“”]")

_PROPER_STOP_PREFIXES = {
    "ngày", "tháng", "năm", "sau", "trước", "trong", "ngoài", "từ", "đến", "theo",
    "nhưng", "tuy", "khi", "nếu", "với", "tại", "trên", "dưới", "giữa", "về", "đầu",
    "cuối", "nửa", "sang", "qua", "nhờ", "do", "vì", "bởi", "một", "hai", "ba",
    "các", "những", "nhiều", "toàn", "cả", "mọi", "đây", "đó", "ngay", "riêng",
    "đặc", "nổi", "tiêu", "chủ", "thực", "bước", "nhằm", "góp", "tạo", "mở",
}


_PROPER_STOP_SUFFIXES = {
    "cộng", "nhân", "dân", "cách", "quốc", "tuyên", "hội", "ủy", "ban",
    "đảng", "mặt", "trận", "chiến", "hiệp", "đội", "chủ", "trung", "đồng",
}


def _extract_typed_cloze_target(stmt: str) -> Optional[tuple[str, str, str]]:
    """
    Trích xuất cụm khái niệm/thực thể NGUYÊN VẸN kèm phân loại ('quoted' | 'proper_phrase' | 'acronym')
    để đảm bảo không bao giờ cắt cụt từ tiếng Việt ('Việt Nam' -> 'Nam', 'Đảng Cộng sản' -> 'Đảng Cộng')
    và chỉ ghép phương án nhiễu cùng loại.
    """
    # 1. Ưu tiên thuật ngữ / khẩu hiệu đặt trong ngoặc kép
    for m in _QUOTED_CONCEPT_RE.finditer(stmt):
        target = re.sub(r"\s+", " ", m.group(1)).strip(" ,.;:!?")
        if 6 <= len(target) <= 50 and len(target.split()) >= 2 and not _STUDY_BOILERPLATE_LINE_RE.search(target):
            masked = stmt[: m.start(1)] + "[...]" + stmt[m.end(1) :]
            return "quoted", masked, target

    # 2. Cụm danh từ riêng / tên tổ chức ĐẦY ĐỦ (>= 2 tiếng có dấu Unicode, không cắt cụt cụm danh từ)
    for m in _PROPER_PHRASE_RE.finditer(stmt):
        target = m.group(1).strip()
        words = target.split()
        if len(words) < 2 or len(target) < 6 or len(target) > 48:
            continue
        if words[0].lower() in _PROPER_STOP_PREFIXES or words[-1].lower() in _PROPER_STOP_SUFFIXES:
            continue
        # Tránh cắt dở tên tổ chức/đơn vị/báo/văn kiện có từ thường nối tiếp như "Đội Việt Nam tuyên truyền...", "Báo Thanh niên"
        trailing = stmt[m.end(1) :].lstrip()
        if words[0].lower() in {
            "đội", "ban", "ủy", "hội", "đảng", "mặt", "bộ", "tổng", "báo", "tờ",
            "nhà", "chiến", "hiệp", "đại", "liên", "cộng", "phố", "trường", "đường",
            "luận", "chính", "phong", "trào", "cách", "thực", "chủ",
        } and re.match(rf"^[{_VI_LOWER}]", trailing):
            continue
        if m.start(1) == 0 and len(words) == 2 and words[0].lower() in {"nhà", "ban", "hội", "bộ", "tổ"}:
            continue
        masked = stmt[: m.start(1)] + "[...]" + stmt[m.end(1) :]
        return "proper_phrase", masked, target

    # 3. Từ viết tắt chuyên ngành/tổ chức (VD: XHCN, NATO, ASEAN, SEV, UNESCO)
    for m in _ACRONYM_RE.finditer(stmt):
        target = m.group(1).strip()
        if len(target) < 3 or target in {"III", "VII", "VIII", "XII", "XIII", "XIV", "XIX", "XXI"}:
            continue
        masked = stmt[: m.start(1)] + "[...]" + stmt[m.end(1) :]
        return "acronym", masked, target

    return None


def _normalize_date_label(date_str: str) -> str:
    """Chuẩn hóa chữ hoa/thường đồng nhất cho các mốc thời gian (tránh 'NĂM 2000' lẫn 'Năm 1945')."""
    s = re.sub(r"\s+", " ", (date_str or "").strip(" ,.;:-"))
    s = re.sub(r"(?i)^ngày\s+", "Ngày ", s)
    s = re.sub(r"(?i)^tháng\s+", "Tháng ", s)
    s = re.sub(r"(?i)^năm\s+", "Năm ", s)
    s = re.sub(r"(?i)^từ\s+(?:năm\s+)?", "", s)
    return s.strip()


def _extract_timeline_fact(stmt: str) -> Optional[tuple[str, str, str]]:
    """Trích xuất cặp (loại_mốc, mô_tả_sự_kiện, mốc_thời_gian) từ câu lịch sử/sự kiện hoàn chỉnh."""
    # Bỏ qua tiêu đề chương/bài viết hoa hoặc dòng mục lục
    if stmt.isupper() or re.match(r"^(?:bài|chương|phần)\s+\d+", stmt, flags=re.IGNORECASE):
        return None
    m = _TIMELINE_DATE_RE.search(stmt)
    if not m:
        return None
    date_str = _normalize_date_label(m.group(1))
    # Loại bỏ mốc thời gian khỏi mô tả để tránh lộ đáp án
    before = stmt[: m.start(1)].rstrip(" ,;:-(")
    after = stmt[m.end(1) :].lstrip(" ,;:-)")
    event_desc = re.sub(r"\s+", " ", f"{before} {after}".strip(" ,;:-")).strip()
    event_desc = re.sub(r"^(?:vào|từ|đến|trong|sáng|chiều|tối|đêm|trưa|giữa|cuối|đầu)\s+", "", event_desc, flags=re.IGNORECASE).strip()
    if len(event_desc) < 28 or len(event_desc) > 165 or not _is_complete_statement(event_desc):
        return None
    # Bỏ qua nếu mô tả vẫn còn chứa năm 4 chữ số khác hoặc cụm cụt "từ đến"
    if re.search(r"(?i)\btừ\s+đến\b|\b\d{4}\b", event_desc):
        return None
    if re.search(r"\d{1,2}\s*[/\-\.]\s*\d{1,2}\s*[/\-\.]\s*\d{4}", date_str):
        kind = "full_date"
    elif re.search(r"\d{4}\s*[–\-]\s*\d{4}", date_str):
        kind = "period"
    elif re.search(r"(?i)^tháng\s+\d{1,2}", date_str):
        kind = "month_year"
    else:
        kind = "year_only"
    return kind, event_desc, date_str


def _build_prose_grounded_questions(
    source_refs: List[Dict[str, Any]],
    needed: int,
    existing_prompts: set[str],
) -> List[Dict[str, Any]]:
    """
    Tạo câu hỏi trắc nghiệm ĐA DẠNG (Khái niệm/Vai trò, Nhận diện chủ thể, Mốc thời gian,
    Nhận định theo chủ đề, và Điền cụm từ nguyên vẹn cùng loại) bám sát tài liệu.
    Tuyệt đối không lặp 1 form, không cắt cụt từ tiếng Việt và không dùng 'Không đề cập trong đoạn này'.
    """
    if not source_refs or needed <= 0:
        return []

    statements = _extract_prose_statements(source_refs)
    if len(statements) < 2:
        return []

    concept_pairs: List[tuple[str, str, str, Dict[str, Any]]] = []
    seen_concept_keys: set[tuple[str, str]] = set()
    timeline_by_kind: Dict[str, List[tuple[str, str, str, Dict[str, Any]]]] = {
        "full_date": [],
        "month_year": [],
        "year_only": [],
        "period": [],
    }
    cloze_by_kind: Dict[str, List[tuple[str, str, str, Dict[str, Any]]]] = {
        "quoted": [],
        "proper_phrase": [],
        "acronym": [],
    }
    section_stmts: Dict[str, List[tuple[str, Dict[str, Any]]]] = {}

    for stmt, sec_title, ref in statements:
        if sec_title and 38 <= len(stmt) <= 170 and stmt.lower() != sec_title.lower():
            section_stmts.setdefault(sec_title, []).append((stmt, ref))

        cm = _CONCEPT_DEF_PATTERN.match(stmt)
        if cm:
            subj = _clean_statement_text(cm.group(1)).strip(" ,;-")
            pred = cm.group(2).strip().rstrip(".")
            if 4 <= len(subj) <= 55 and 18 <= len(pred) <= 155 and subj.lower() not in _BROKEN_SINGLE_OPTIONS:
                display_subj = (
                    f"{subj} ({sec_title})"
                    if sec_title and subj.lower() in _GENERIC_OUTLINE_KEYS and sec_title.lower() not in subj.lower()
                    else subj
                )
                ck = (display_subj.lower(), pred.lower())
                if ck not in seen_concept_keys:
                    seen_concept_keys.add(ck)
                    concept_pairs.append((display_subj, pred, stmt, ref))
        else:
            km = _OUTLINE_KV_PATTERN.match(stmt)
            if km:
                subj = _clean_statement_text(km.group(1)).strip(" ,;-")
                pred = _clean_statement_text(km.group(2)).strip().rstrip(".")
                if (
                    4 <= len(subj) <= 50
                    and 20 <= len(pred) <= 155
                    and not re.match(r"^(?:ngày|tháng|năm|\d)", subj, flags=re.IGNORECASE)
                    and subj.lower() not in _BROKEN_SINGLE_OPTIONS
                ):
                    display_subj = (
                        f"{subj} ({sec_title})"
                        if sec_title and subj.lower() in _GENERIC_OUTLINE_KEYS and sec_title.lower() not in subj.lower()
                        else subj
                    )
                    ck = (display_subj.lower(), pred.lower())
                    if ck not in seen_concept_keys:
                        seen_concept_keys.add(ck)
                        concept_pairs.append((display_subj, pred, stmt, ref))

        tl = _extract_timeline_fact(stmt)
        if tl:
            t_kind, ev_desc, dt_str = tl
            timeline_by_kind[t_kind].append((ev_desc, dt_str, stmt, ref))

        clz = _extract_typed_cloze_target(stmt)
        if clz:
            c_kind, masked, target = clz
            cloze_by_kind[c_kind].append((masked, target, stmt, ref))

    # Xây dựng các ứng viên theo 5 nhóm dạng câu hỏi khác nhau rồi trộn xen kẽ (round-robin)
    bucket_concept_fwd: List[Dict[str, Any]] = []
    bucket_concept_rev: List[Dict[str, Any]] = []
    bucket_timeline: List[Dict[str, Any]] = []
    bucket_section_match: List[Dict[str, Any]] = []
    bucket_cloze: List[Dict[str, Any]] = []

    fwd_stems = [
        'Theo tài liệu, "{subj}" có nội dung, vai trò hoặc đặc điểm nào sau đây?',
        'Nội dung nào sau đây phản ánh đúng về "{subj}" theo tài liệu?',
        'Theo nội dung bài học, "{subj}" được xác định như thế nào?',
    ]
    rev_stems = [
        'Khái niệm, chủ thể hoặc nội dung nào trong tài liệu tương ứng với mô tả sau: "{pred}"?',
        'Nhận định "{pred}" trong tài liệu dùng để nói về nội dung nào sau đây?',
    ]

    if len(concept_pairs) >= 4:
        preds_pool = [_capitalize_option(p) for _, p, _, _ in concept_pairs]
        subjs_pool = [_capitalize_option(s) for s, _, _, _ in concept_pairs]
        for idx, (subj, pred, orig_stmt, ref) in enumerate(concept_pairs):
            doc_name = ref.get("documentName") or "Tài liệu"
            page_num = ref.get("pageNumber") or 1
            pred_opt = _capitalize_option(pred)
            subj_opt = _capitalize_option(subj)

            # Dạng 1: Chủ thể -> Đặc điểm/Nội dung
            d_fwd = _pick_distinct_distractors(preds_pool, pred_opt, 3, idx * 5 + 1)
            if len(d_fwd) >= 3:
                p_fwd = fwd_stems[idx % len(fwd_stems)].format(subj=subj)
                bucket_concept_fwd.append(
                    {
                        "prompt": p_fwd,
                        "correct": pred_opt,
                        "distractors": d_fwd[:3],
                        "fact_key": orig_stmt.lower(),
                        "explanation": f"Theo {doc_name} (Trang {page_num}): {subj} — {pred}.",
                        "ref": ref,
                    }
                )

            # Dạng 2: Mô tả -> Nhận diện chủ thể (chỉ lấy khi chủ thể không trùng lặp chung chung)
            if subj.lower() not in _GENERIC_OUTLINE_KEYS:
                d_rev = _pick_distinct_distractors(subjs_pool, subj_opt, 3, idx * 5 + 3)
                if len(d_rev) >= 3:
                    p_rev = rev_stems[idx % len(rev_stems)].format(pred=pred)
                    bucket_concept_rev.append(
                        {
                            "prompt": p_rev,
                            "correct": subj_opt,
                            "distractors": d_rev[:3],
                            "fact_key": orig_stmt.lower(),
                            "explanation": f"Theo {doc_name} (Trang {page_num}), mô tả này nói về \"{subj}\".",
                            "ref": ref,
                        }
                    )

    # Dạng 3: Mốc thời gian / Giai đoạn (TUYỆT ĐỐI chỉ ghép các mốc cùng cấp độ thời gian với nhau)
    tl_stems = [
        'Theo tài liệu, sự kiện "{ev}" diễn ra vào mốc thời gian nào?',
        'Mốc thời gian nào sau đây gắn liền với sự kiện "{ev}" trong tài liệu?',
    ]
    tl_idx = 0
    for kind_key in ("full_date", "month_year", "year_only", "period"):
        items = timeline_by_kind[kind_key]
        same_kind_pool = [_capitalize_option(dt) for _, dt, _, _ in items]
        if len(set(x.lower() for x in same_kind_pool)) < 4:
            continue
        for ev_desc, dt_str, full_stmt, ref in items:
            dt_opt = _capitalize_option(dt_str)
            d_tl = _pick_distinct_distractors(same_kind_pool, dt_opt, 3, tl_idx * 7 + 2)
            if len(d_tl) < 3:
                continue
            doc_name = ref.get("documentName") or "Tài liệu"
            page_num = ref.get("pageNumber") or 1
            bucket_timeline.append(
                {
                    "prompt": tl_stems[tl_idx % len(tl_stems)].format(ev=ev_desc),
                    "correct": dt_opt,
                    "distractors": d_tl[:3],
                    "fact_key": full_stmt.lower(),
                    "explanation": f"Theo {doc_name} (Trang {page_num}): \"{full_stmt}\".",
                    "ref": ref,
                }
            )
            tl_idx += 1

    # Dạng 4: Nhận định đúng thuộc chủ đề/mục cụ thể (lấy phương án nhiễu từ các mục KHÁC trong cùng tài liệu)
    valid_sections = [sec for sec, lst in section_stmts.items() if lst]
    if len(valid_sections) >= 4:
        sec_idx = 0
        for sec in valid_sections:
            other_stmts = [
                _capitalize_option(s)
                for o_sec, o_lst in section_stmts.items()
                if o_sec != sec
                for s, _ in o_lst
            ]
            if len(other_stmts) < 3:
                continue
            for stmt_true, ref in section_stmts[sec][:2]:
                stmt_opt = _capitalize_option(stmt_true)
                d_sec = _pick_distinct_distractors(other_stmts, stmt_opt, 3, sec_idx * 5 + 4)
                if len(d_sec) < 3:
                    continue
                doc_name = ref.get("documentName") or "Tài liệu"
                page_num = ref.get("pageNumber") or 1
                bucket_section_match.append(
                    {
                        "prompt": f'Nội dung nào sau đây thuộc phần "{sec}" theo tài liệu?',
                        "correct": stmt_opt,
                        "distractors": d_sec[:3],
                        "fact_key": stmt_true.lower(),
                        "explanation": f"Theo mục \"{sec}\" trong {doc_name} (Trang {page_num}): \"{stmt_true}\".",
                        "ref": ref,
                    }
                )
                sec_idx += 1

    # Dạng 5: Điền cụm từ nguyên vẹn (chỉ ghép cùng loại: quoted/proper_phrase/acronym) — giới hạn tỷ lệ thấp
    cloze_stems = [
        'Chọn cụm từ chính xác để hoàn thiện nhận định sau theo tài liệu:\n"{masked}"',
        'Theo nội dung tài liệu, cụm từ nào phù hợp với vị trí [...] trong câu sau?\n"{masked}"',
    ]
    clz_idx = 0
    for c_kind in ("quoted", "proper_phrase", "acronym"):
        items = cloze_by_kind[c_kind]
        same_type_pool = [t for _, t, _, _ in items]
        if len(set(x.lower() for x in same_type_pool)) < 4:
            continue
        for masked, target, full_stmt, ref in items:
            d_clz = _pick_distinct_distractors(same_type_pool, target, 3, clz_idx * 7 + 3)
            if len(d_clz) < 3:
                continue
            doc_name = ref.get("documentName") or "Tài liệu"
            page_num = ref.get("pageNumber") or 1
            bucket_cloze.append(
                {
                    "prompt": cloze_stems[clz_idx % len(cloze_stems)].format(masked=masked),
                    "correct": target,
                    "distractors": d_clz[:3],
                    "fact_key": full_stmt.lower(),
                    "explanation": f"Câu gốc trong {doc_name} (Trang {page_num}): \"{full_stmt}\".",
                    "ref": ref,
                }
            )
            clz_idx += 1

    # Trộn xen kẽ (round-robin) giữa các dạng câu hỏi để bộ đề đa dạng, tự nhiên và không lặp 1 form / không trùng dữ kiện
    has_rich_non_cloze = bool(bucket_concept_fwd or bucket_concept_rev or bucket_timeline or bucket_section_match)
    max_cloze_allowed = max(1, (needed + 2) // 3) if has_rich_non_cloze else needed

    ordered_buckets = [
        ("concept_fwd", bucket_concept_fwd),
        ("timeline", bucket_timeline),
        ("concept_rev", bucket_concept_rev),
        ("section_match", bucket_section_match),
        ("cloze", bucket_cloze),
    ]
    cursors = {name: 0 for name, _ in ordered_buckets}
    cloze_used = 0
    used_facts: set[str] = set()
    used_answers: set[str] = set()
    generated: List[Dict[str, Any]] = []

    base_ans_offset = len(existing_prompts) % 4

    def _run_round_robin(allow_reused_facts: bool) -> None:
        nonlocal cloze_used
        while len(generated) < needed:
            progressed = False
            for name, bucket in ordered_buckets:
                if len(generated) >= needed:
                    break
                if name == "cloze" and cloze_used >= max_cloze_allowed:
                    continue
                while cursors[name] < len(bucket):
                    cand = bucket[cursors[name]]
                    cursors[name] += 1
                    p_key = cand["prompt"].lower()
                    ans_key = cand["correct"].lower()
                    f_key = cand.get("fact_key", "")
                    if p_key in existing_prompts:
                        continue
                    if not allow_reused_facts and f_key and f_key in used_facts:
                        continue
                    if not allow_reused_facts and ans_key in used_answers and len(bucket) > needed:
                        continue
                    ans_idx = (base_ans_offset + len(generated) * 3 + 1) % 4
                    options = list(cand["distractors"][:3])
                    options.insert(ans_idx, cand["correct"])
                    existing_prompts.add(p_key)
                    used_answers.add(ans_key)
                    if f_key:
                        used_facts.add(f_key)
                    if name == "cloze":
                        cloze_used += 1
                    generated.append(
                        {
                            "id": f"ai-q-{name}-{len(generated) + 1}",
                            "prompt": cand["prompt"],
                            "options": options,
                            "answerIndex": ans_idx,
                            "explanation": cand["explanation"],
                            "citation": _make_citation_from_ref(cand["ref"]),
                        }
                    )
                    progressed = True
                    break
            if not progressed:
                break

    _run_round_robin(allow_reused_facts=False)
    if len(generated) < needed:
        # Nếu vẫn thiếu câu sau khi đã lấy hết các dữ kiện riêng biệt, nới lỏng để đủ số câu yêu cầu
        max_cloze_allowed = needed
        cursors = {name: 0 for name, _ in ordered_buckets}
        _run_round_robin(allow_reused_facts=True)

    return generated


def _resolve_question_citation(
    raw_q: Dict[str, Any],
    source_refs: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Ánh xạ câu hỏi Quiz về đoạn nguồn tài liệu gốc để người học kiểm chứng."""
    if not source_refs:
        return None

    chosen: Optional[Dict[str, Any]] = None
    src_idx = raw_q.get("sourceIndex") or raw_q.get("source_index")
    if src_idx is not None:
        try:
            idx_num = int(src_idx)
            if 1 <= idx_num <= len(source_refs):
                chosen = source_refs[idx_num - 1]
        except (TypeError, ValueError):
            chosen = None

    if chosen is None:
        q_text = f"{raw_q.get('prompt', '')} {raw_q.get('explanation', '')}".lower()
        q_terms = {t for t in re.findall(r"[\w]{2,}", q_text, flags=re.UNICODE)}
        best_score = -1
        for ref in source_refs:
            haystack = ref.get("_search_text") or ""
            score = sum(1 for term in q_terms if term in haystack)
            if score > best_score:
                best_score = score
                chosen = ref

    if chosen is None:
        chosen = source_refs[0]

    return _make_citation_from_ref(chosen)


_QUIZ_DIFFICULTY_GUIDE = {
    "easy": (
        "Mức Nhận biết (Dễ): Hỏi trực tiếp định nghĩa, ý nghĩa thuật ngữ/từ vựng hoặc thông tin cốt lõi nêu rõ trong bài; "
        "câu hỏi ngắn gọn, rõ ràng."
    ),
    "medium": (
        "Mức Thông hiểu (Vừa): Kiểm tra sự hiểu đúng bản chất, phân biệt các thuật ngữ/khái niệm gần nhau trong cùng chủ đề, "
        "hoặc chọn thuật ngữ đúng cho ngữ cảnh mô tả."
    ),
    "hard": (
        "Mức Vận dụng & Phân tích (Khó): Đặt câu hỏi tình huống thực tế, so sánh điểm khác biệt tinh tế, mối quan hệ nguyên nhân - kết quả; "
        "4 phương án nhiễu phải rất hợp lý, cùng trường nghĩa và có độ dài tương đương."
    ),
}

_QUIZ_STYLE_GUIDE = {
    "auto": (
        "Tự động chọn dạng câu hỏi tối ưu theo bản chất tài liệu (nếu là từ vựng/thuật ngữ thì kiểm tra nghĩa, thuật ngữ tương ứng và ngữ cảnh sử dụng; "
        "nếu là lý thuyết/kỹ thuật thì kiểm tra bản chất khái niệm, nguyên lý và ứng dụng)."
    ),
    "vocabulary": (
        "Tập trung kiểm tra Từ vựng & Thuật ngữ chuyên ngành: hỏi nghĩa chuẩn xác, cho nghĩa/mô tả chọn đúng từ/thuật ngữ, "
        "và phân biệt các thuật ngữ dễ nhầm lẫn trong tài liệu."
    ),
    "concept": (
        "Tập trung kiểm tra Khái niệm, Định nghĩa & Lý thuyết trọng tâm: hỏi bản chất, vai trò, cấu trúc, quy tắc hoặc số liệu cốt lõi."
    ),
    "application": (
        "Tập trung vào Tình huống & Vận dụng thực tế: đưa ra ví dụ, ngữ cảnh hoặc bài toán cụ thể để người học vận dụng kiến thức/thuật ngữ trong tài liệu chọn đáp án đúng."
    ),
    "mixed": (
        "Kết hợp cân đối nhiều dạng câu hỏi: nhận biết thuật ngữ/khái niệm, thông hiểu bản chất và vận dụng vào ngữ cảnh thực tế."
    ),
}


_QUIZ_BATCH_ANGLES = [
    (
        "Ưu tiên câu hỏi trực tiếp về BẢN CHẤT, NỘI DUNG CỐT LÕI hoặc MỤC TIÊU/NHIỆM VỤ chính trong đoạn trích "
        "(VD: 'Nội dung cốt lõi của ... là gì?', 'Mục tiêu chủ yếu của ... là gì?'). "
        "KHÔNG dùng mẫu 'Điền cụm từ vào chỗ trống [...]'."
    ),
    (
        "Ưu tiên câu hỏi về NGUYÊN NHÂN, KẾT QUẢ, Ý NGHĨA hoặc SO SÁNH/PHÂN BIỆT giữa hai sự kiện/khái niệm "
        "(VD: 'Nguyên nhân dẫn đến ... là gì?', 'Điểm khác biệt cơ bản giữa ... và ... là gì?', 'Ý nghĩa quan trọng nhất của ... là gì?'). "
        "KHÔNG dùng mẫu 'Điền cụm từ vào chỗ trống [...]'."
    ),
    (
        "Ưu tiên câu hỏi NHẬN DIỆN SỰ KIỆN/TỔ CHỨC/KHÁI NIỆM qua đặc điểm, HỎI MỐC THỜI GIAN/SỐ LIỆU quan trọng, "
        "hoặc câu hỏi PHỦ ĐỊNH TINH TẾ ('Nội dung nào sau đây KHÔNG đúng về ...?') / TÌNH HUỐNG VẬN DỤNG."
    ),
]


def _format_source_slice(refs_slice: List[Dict[str, Any]], char_limit: int) -> str:
    """Định dạng một nhóm đoạn nguồn giữ nguyên số thứ tự [Nguồn k] để ánh xạ Citation chính xác."""
    parts: List[str] = []
    used = 0
    for ref in refs_slice:
        raw = str(ref.get("_raw_text") or ref.get("snippet") or "").strip()
        if not raw:
            continue
        ref_idx = ref.get("ref_index", 1)
        doc_name = ref.get("documentName") or "Tài liệu"
        page_num = ref.get("pageNumber") or 1
        block = f"[Nguồn {ref_idx} · {doc_name} - Trang {page_num}]:\n{raw}"
        rem = char_limit - used
        if rem <= 120:
            break
        if len(block) > rem:
            block = block[:rem].rstrip()
        parts.append(block)
        used += len(block) + 2
    return "\n\n".join(parts)


async def generate_ai_quiz(
    workspace_id: str,
    document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    difficulty: str = "medium",
    question_count: int = 5,
    focus_prompt: Optional[str] = None,
    model: str = DEFAULT_LLM_MODEL,
    quiz_style: str = "auto",
) -> Dict[str, Any]:
    """
    Sinh danh sách câu hỏi trắc nghiệm kiểm tra kiến thức dựa trên nội dung tài liệu kèm citation.
    Chia thành các lô ngắn (3-4 câu/lô) trên nhiều lát cắt tài liệu với góc hỏi đa dạng để model local
    sinh câu hỏi tự nhiên, giàu tính sư phạm và tránh quá hạn (timeout) rơi toàn bộ về fallback.
    """
    count = min(max(question_count, 1), 20)
    budget = _get_study_runtime_budget()
    is_eco = budget["profile_id"] == "eco"

    max_chunks = min(20, max(12, count + 4))
    max_chars = 5200 if is_eco else 7600
    context, source_refs = _get_document_context_items(
        workspace_id,
        document_id,
        document_ids,
        max_chunks=max_chunks,
        max_chars=max_chars,
        focus_prompt=focus_prompt,
        numbered_sources=True,
    )
    if not context:
        return {
            "title": "Quiz trắc nghiệm",
            "questions": [],
            "error": "Chưa có nội dung tài liệu để tạo câu hỏi trắc nghiệm.",
            "is_mock": False,
        }

    chosen_model, model_error = await _ensure_ollama_chat_model(model)
    if model_error or not chosen_model:
        return {
            "title": "Quiz trắc nghiệm",
            "questions": [],
            "error": model_error or "Ollama chưa được khởi động.",
            "is_mock": True,
        }

    clean_focus = (focus_prompt or "").strip()
    semantic_focus = clean_focus if clean_focus and not _is_generic_focus_prompt(clean_focus) else None
    eff_style = quiz_style if quiz_style in _QUIZ_STYLE_GUIDE else "auto"
    vocab_entries = _extract_vocab_entries(source_refs)
    is_vocab_mode = len(vocab_entries) >= 8 and eff_style != "concept"

    total_raw_chars = sum(len(str(r.get("_raw_text") or "")) for r in source_refs)
    diff_instruction = _QUIZ_DIFFICULTY_GUIDE.get(difficulty, _QUIZ_DIFFICULTY_GUIDE["medium"])
    style_instruction = _QUIZ_STYLE_GUIDE.get(eff_style, _QUIZ_STYLE_GUIDE["auto"])

    # Lập kế hoạch chia lô ngắn để model local (3b/7b trên CPU) phản hồi nhanh, ổn định và đa dạng dạng câu hỏi
    batch_contexts: List[tuple[int, str, str]] = []
    if is_vocab_mode:
        prioritized_vocab = _prioritize_vocab_by_focus(vocab_entries, semantic_focus)
        sample_cap = 22 if is_eco else 32
        sampled_vocab_lines: List[str] = []
        step = max(1, len(prioritized_vocab) // sample_cap)
        for idx in range(0, len(prioritized_vocab), step):
            ve = prioritized_vocab[idx]
            ref_idx = ve["ref"].get("ref_index", 1)
            note_part = f" ({ve['note']})" if ve.get("note") else ""
            reading_part = f" | Cách đọc: {ve['reading']}" if ve["term"] != ve["reading"] else ""
            sampled_vocab_lines.append(
                f"[Nguồn {ref_idx}] Thuật ngữ/Từ: {ve['term']}{note_part}{reading_part} | Nghĩa: {ve['meaning']}"
            )
            if len(sampled_vocab_lines) >= sample_cap:
                break

        llm_total = min(count, 6 if is_eco else min(count, 10))
        if semantic_focus or eff_style in ("application", "mixed") or difficulty == "hard":
            batch_size = 3 if is_eco else 4
        else:
            llm_total = min(count, 4 if is_eco else 6)
            batch_size = 4

        n_batches = max(1, (llm_total + batch_size - 1) // batch_size)
        remaining_ask = llm_total
        for b_idx in range(n_batches):
            ask_n = min(batch_size, remaining_ask)
            if ask_n <= 0:
                break
            remaining_ask -= ask_n
            start_i = (b_idx * len(sampled_vocab_lines)) // n_batches
            end_i = max(start_i + 8, ((b_idx + 1) * len(sampled_vocab_lines)) // n_batches)
            slice_lines = sampled_vocab_lines[start_i:end_i] or sampled_vocab_lines
            angle = (
                "Đa dạng kiểu hỏi từ vựng: hỏi nghĩa tiếng Việt của từ, cho mô tả/nghĩa chọn từ đúng, "
                "và câu hỏi ngữ cảnh vận dụng từ vựng (4 lựa chọn cùng loại, độ dài tương đương)."
            )
            batch_contexts.append((ask_n, "\n".join(slice_lines), angle))
    else:
        llm_total = min(count, 8 if is_eco else min(count, 12))
        if total_raw_chars < 220:
            batch_size = llm_total
        elif is_eco:
            batch_size = 2 if llm_total >= 4 else llm_total
        else:
            batch_size = 3 if llm_total <= 6 else 4
        n_batches = min(5, max(1, (llm_total + batch_size - 1) // batch_size))
        per_batch_chars = 1200 if is_eco else 1550
        remaining_ask = llm_total
        for b_idx in range(n_batches):
            ask_n = min(batch_size, remaining_ask)
            if ask_n <= 0:
                break
            remaining_ask -= ask_n
            if len(source_refs) >= n_batches:
                chunk_start = (b_idx * len(source_refs)) // n_batches
                chunk_end = max(chunk_start + 1, ((b_idx + 1) * len(source_refs)) // n_batches)
                refs_slice = source_refs[chunk_start:chunk_end]
            else:
                refs_slice = source_refs
            slice_text = _format_source_slice(refs_slice, per_batch_chars) or context[:per_batch_chars]
            angle = _QUIZ_BATCH_ANGLES[b_idx % len(_QUIZ_BATCH_ANGLES)]
            batch_contexts.append((ask_n, slice_text, angle))

    valid_questions: List[Dict[str, Any]] = []
    seen_prompts: set[str] = set()
    llm_error: Optional[Exception] = None
    consecutive_errors = 0
    total_budget_sec = min(OLLAMA_TIMEOUT, 125.0 if is_eco else 160.0)
    deadline = time.monotonic() + total_budget_sec

    for b_idx, (ask_n, slice_context, angle_hint) in enumerate(batch_contexts):
        if len(valid_questions) >= count:
            break
        remaining_time = deadline - time.monotonic()
        if b_idx > 0 and remaining_time < 15.0:
            break

        per_call_timeout = min(
            OLLAMA_TIMEOUT,
            max(20.0, min(remaining_time, 42.0 if is_eco else 48.0)),
        )
        predict_tokens = min(680, max(380, ask_n * 165))

        system_prompt = (
            "Bạn là chuyên gia ra đề trắc nghiệm chuẩn sư phạm.\n"
            "Biên soạn câu hỏi trắc nghiệm 4 lựa chọn bằng tiếng Việt bám sát TÀI LIỆU NGUỒN ([Nguồn 1], [Nguồn 2]...).\n"
            "QUY TẮC:\n"
            "1. Chỉ hỏi kiến thức thực có trong tài liệu; tuân thủ YÊU CẦU RIÊNG nếu có; KHÔNG viết '[Nguồn X]' vào trong nội dung câu hỏi.\n"
            "2. Đa dạng cách hỏi tự nhiên (bản chất, nguyên nhân, mục tiêu, ý nghĩa, so sánh, sự kiện, phủ định). "
            "CẤM lặp 1 khuôn mẫu và CẤM dùng dạng điền chỗ trống '[...]'.\n"
            "3. Cả 4 phương án phải CÙNG LOẠI ngữ nghĩa, khác nhau hoàn toàn, đầy đủ nghĩa, độ dài tương đương; CẤM cắt lẻ 1 âm tiết, "
            "CẤM 'Không đề cập trong đoạn này', CẤM hỏi tên website/số trang/mục lục.\n"
            "4. Ghi CHÍNH XÁC nguyên văn phương án đúng vào trường correctAnswer (khớp 100% với 1 trong 4 phần tử của options) và answerIndex tương ứng (0..3).\n"
            'TRẢ VỀ DUY NHẤT JSON: {"questions":[{"prompt":"...","options":["...","...","...","..."],"correctAnswer":"...","answerIndex":0,"explanation":"...","sourceIndex":1}]}\n'
            f"Tạo đúng {ask_n} câu hỏi khác nhau."
        )

        user_prompt = f"TÀI LIỆU NGUỒN:\n{slice_context}\n\n"
        user_prompt += f"- ĐỘ KHÓ: {diff_instruction}\n"
        user_prompt += f"- KIỂU CÂU HỎI: {style_instruction}\n"
        user_prompt += f"- GÓC HỎI LÔ NÀY: {angle_hint}\n"
        if clean_focus and not _is_generic_focus_prompt(clean_focus):
            user_prompt += (
                f"- YÊU CẦU RIÊNG CỦA NGƯỜI HỌC (ƯU TIÊN TUÂN THỦ): \"{clean_focus}\"\n"
            )
        if valid_questions:
            prev_list = "\n".join(f"  * {q['prompt'][:90]}" for q in valid_questions[-6:])
            user_prompt += f"- ĐÃ HỎI (TRÁNH TRÙNG):\n{prev_list}\n"
        user_prompt += f"\nSoạn đúng {ask_n} câu hỏi trắc nghiệm JSON:"

        try:
            raw_res = await _call_ollama_chat(
                system_prompt,
                user_prompt,
                model=chosen_model,
                json_mode=True,
                timeout_sec=per_call_timeout,
                num_predict=predict_tokens,
                allow_extended_predict=True,
                stream_salvage=True,
            )
            batch_qs = _extract_and_normalize_llm_questions(
                raw_res,
                source_refs,
                vocab_entries,
                seen_prompts=seen_prompts,
                start_index=len(valid_questions),
            )
            consecutive_errors = 0
            if not batch_qs:
                # Lô hiện tại không có câu đạt chuẩn -> tiếp tục thử lát cắt tiếp theo thay vì hủy toàn bộ
                continue
            valid_questions.extend(batch_qs)
        except Exception as exc:
            llm_error = exc
            consecutive_errors += 1
            logger.warning(
                "LLM sinh Quiz lô %d/%d gặp lỗi hoặc quá thời gian: %s",
                b_idx + 1,
                len(batch_contexts),
                exc,
            )
            if consecutive_errors >= 2:
                break

    # Lọc câu hỏi sạch TRƯỚC khi tính số lượng cần bù để luôn đảm bảo trả về đủ count câu hỏi
    valid_questions = [
        q for q in valid_questions if _is_clean_quiz_question(str(q.get("prompt") or ""), q.get("options") or [])
    ]

    # Bổ sung câu hỏi chuẩn xác từ tài liệu nguồn nếu LLM trả về thiếu số lượng
    needed = count - len(valid_questions)
    if needed > 0:
        existing_prompts = {q["prompt"].lower() for q in valid_questions}
        if len(vocab_entries) >= 4 and eff_style != "concept":
            vocab_topup = _build_vocab_grounded_questions(
                vocab_entries,
                needed=needed,
                existing_prompts=existing_prompts,
                semantic_focus=semantic_focus,
                quiz_style=eff_style,
                difficulty=difficulty,
            )
            valid_questions.extend(
                q for q in vocab_topup if _is_clean_quiz_question(str(q.get("prompt") or ""), q.get("options") or [])
            )

        needed = count - len(valid_questions)
        if needed > 0 and (total_raw_chars >= 160 or not valid_questions):
            prose_topup = _build_prose_grounded_questions(
                source_refs,
                needed=needed,
                existing_prompts=existing_prompts,
            )
            valid_questions.extend(
                q for q in prose_topup if _is_clean_quiz_question(str(q.get("prompt") or ""), q.get("options") or [])
            )

    if not valid_questions and llm_error is not None:
        logger.exception("Lỗi khi sinh Quiz bằng AI: %s", llm_error)
        return {
            "title": "Quiz trắc nghiệm",
            "questions": [],
            "error": f"Không thể sinh câu hỏi: {str(llm_error)}",
            "is_mock": True,
        }

    final_questions = valid_questions[:count]
    for idx, q in enumerate(final_questions):
        q["id"] = f"ai-q-{idx + 1}"

    primary_doc_name = source_refs[0]["documentName"] if source_refs else "Tài liệu học tập"
    title_topic = (semantic_focus or clean_focus or primary_doc_name).strip()
    if len(title_topic) > 48:
        title_topic = title_topic[:45].rstrip() + "..."
    return {
        "title": f"Quiz · {title_topic}",
        "questions": final_questions,
        "difficulty": difficulty,
        "quiz_style": eff_style,
        "is_mock": False,
    }


_FLASHCARD_STYLE_GUIDE = {
    "term_definition": {
        "label": "Thuật ngữ – Định nghĩa",
        "front_desc": "Tên thuật ngữ, khái niệm hoặc nguyên lý cốt lõi ngắn gọn",
        "back_desc": "Định nghĩa chính xác, nêu rõ bản chất và ý nghĩa (1-3 câu tiếng Việt)",
        "instruction": "Mặt trước (front) nêu đúng tên thuật ngữ/khái niệm; Mặt sau (back) giải thích ngắn gọn bản chất theo tài liệu.",
    },
    "qa": {
        "label": "Câu hỏi – Trả lời",
        "front_desc": "Một câu hỏi gợi mở/kiểm tra kiến thức cụ thể về tài liệu",
        "back_desc": "Câu trả lời rõ ràng, chính xác kèm luận giải ngắn dựa trên tài liệu",
        "instruction": "Mặt trước (front) là câu hỏi tiếng Việt kiểm tra kiến thức trọng tâm; Mặt sau (back) trả lời trực tiếp câu hỏi đó.",
    },
    "vocabulary": {
        "label": "Từ vựng – Nghĩa",
        "front_desc": "Từ vựng trọng tâm (nếu có Kanji và Hiragana thì ghi dạng: Kanji (Hiragana))",
        "back_desc": "Nghĩa tiếng Việt chuẩn xác và lưu ý cách dùng ngắn gọn",
        "instruction": "Mặt trước (front) ghi từ vựng kèm cách đọc (nếu có); Mặt sau (back) ghi nghĩa tiếng Việt tương ứng.",
    },
    "cloze": {
        "label": "Điền khuyết – Ghi nhớ",
        "front_desc": "Câu/mệnh đề trích từ tài liệu có chỗ trống [...] tại từ khóa quan trọng",
        "back_desc": "Từ/cụm từ chính xác cần điền vào [...] và giải thích ngắn gọn",
        "instruction": "Mặt trước (front) tạo câu hoàn chỉnh nhưng ẩn từ khóa bằng '[...]'; Mặt sau (back) đưa ra đáp án điền vào chỗ trống.",
    },
}

_FC_FRONT_KEYS = ("front", "term", "question", "word", "concept", "cau_hoi", "thuat_ngu", "tu_vung", "mat_truoc")
_FC_BACK_KEYS = ("back", "definition", "answer", "meaning", "explanation", "giai_thich", "tra_loi", "nghia", "mat_sau")


def _first_nonempty_str(raw: Dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        val = raw.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _extract_and_normalize_llm_flashcards(
    raw_res: str,
    source_refs: List[Dict[str, Any]],
    vocab_entries: List[Dict[str, Any]],
    card_style: str,
) -> List[Dict[str, Any]]:
    """Phân tích, chuẩn hoá và gắn citation cho danh sách Flashcard từ phản hồi JSON của LLM."""
    raw_items: List[Any] = []
    try:
        data = _parse_json_response(raw_res)
        if isinstance(data, list):
            raw_items = data
        elif isinstance(data, dict):
            for key in ("flashcards", "cards", "items", "data", "results", "the"):
                val = data.get(key)
                if isinstance(val, list):
                    raw_items = val
                    break
            if not raw_items:
                for val in data.values():
                    if isinstance(val, list) and val and isinstance(val[0], dict):
                        raw_items = val
                        break
            if not raw_items and _first_nonempty_str(data, _FC_FRONT_KEYS):
                raw_items = [data]
    except Exception:
        raw_items = []

    if not raw_items:
        raw_items = _salvage_json_objects(
            raw_res,
            lambda obj: bool(_first_nonempty_str(obj, _FC_FRONT_KEYS) and _first_nonempty_str(obj, _FC_BACK_KEYS)),
        )

    is_vocab_doc = len(vocab_entries) >= 8
    vocab_tokens: set[str] = set()
    if is_vocab_doc:
        for ve in vocab_entries:
            vocab_tokens.add(ve["term"].lower())
            vocab_tokens.add(ve["reading"].lower())
            vocab_tokens.add(ve["meaning"].lower())

    valid_cards: List[Dict[str, Any]] = []
    seen_fronts: set[str] = set()

    for item in raw_items:
        if not isinstance(item, dict):
            continue
        front = _first_nonempty_str(item, _FC_FRONT_KEYS)
        back = _first_nonempty_str(item, _FC_BACK_KEYS)
        if not front or not back or len(front) < 2 or len(back) < 2:
            continue
        front_key = front.lower()
        if front_key in seen_fronts:
            continue

        if re.search(r"(?i)\b(?:hybrid rag|sparse retrieval|bm25|reciprocal rank)\b", f"{front} {back}"):
            if not any("hybrid rag" in (r.get("_search_text") or "") for r in source_refs):
                continue

        if is_vocab_doc:
            combined = f"{front} {back}".lower()
            if not any(tok in combined for tok in vocab_tokens if len(tok) >= 1):
                continue

        seen_fronts.add(front_key)
        example = _first_nonempty_str(item, ("example", "vi_du", "usage", "context", "note"))
        citation = _resolve_question_citation(
            {
                "prompt": front,
                "explanation": f"{back} {example}",
                "sourceIndex": item.get("sourceIndex") or item.get("source_index"),
            },
            source_refs,
        )

        card_obj: Dict[str, Any] = {
            "id": f"ai-fc-{len(valid_cards) + 1}",
            "front": front,
            "back": back,
            "cardStyle": card_style,
            "status": "new",
            "is_mock": False,
        }
        if example:
            card_obj["example"] = example
        if citation:
            card_obj["citation"] = citation
        valid_cards.append(card_obj)

    return valid_cards


def _build_vocab_grounded_flashcards(
    vocab_entries: List[Dict[str, Any]],
    needed: int,
    existing_fronts: set[str],
    card_style: str,
    semantic_focus: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Tạo thẻ Flashcard chuẩn xác từ bảng từ vựng trong tài liệu nguồn theo đúng kiểu thẻ."""
    if not vocab_entries or needed <= 0:
        return []

    ordered = list(vocab_entries)
    if semantic_focus:
        focus_l = semantic_focus.lower()
        prioritized = [
            e
            for e in ordered
            if focus_l in e["term"].lower()
            or focus_l in e["reading"].lower()
            or focus_l in e["meaning"].lower()
        ]
        others = [e for e in ordered if e not in prioritized]
        ordered = prioritized + others

    total = len(ordered)
    sampled: List[Dict[str, Any]] = []
    used: set[int] = set()
    target = min(total, max(needed * 2, 16))
    step = total / max(1, target)
    for i in range(target):
        idx = min(total - 1, int(i * step))
        if idx not in used:
            used.add(idx)
            sampled.append(ordered[idx])
    for idx, entry in enumerate(ordered):
        if idx not in used:
            sampled.append(entry)

    generated: List[Dict[str, Any]] = []
    for entry in sampled:
        if len(generated) >= needed:
            break
        term = entry["term"]
        reading = entry["reading"]
        meaning = entry["meaning"]
        ref = entry["ref"]
        doc_name = ref.get("documentName") or "Tài liệu từ vựng"
        page_num = ref.get("pageNumber") or 1
        display_word = f"{term} ({reading})" if term != reading else term

        if card_style == "qa":
            front = f"Từ 「{display_word}」 có nghĩa tiếng Việt là gì?"
            back = meaning
            example = f"Cách đọc: {reading} · Nguồn: {doc_name} (Trang {page_num})"
        elif card_style == "cloze":
            front = f"Điền nghĩa tiếng Việt phù hợp cho 「{display_word}」: [...]"
            back = f"{meaning} ({display_word})"
            example = f"Ghi nhớ: 「{term}」 đọc là 「{reading}」"
        elif card_style == "term_definition":
            front = display_word
            back = f"Nghĩa: {meaning}"
            example = f"Từ vựng trích từ {doc_name} (Trang {page_num})"
        else:
            front = display_word
            back = meaning
            example = f"Cách đọc: {reading}" if term != reading else f"Từ vựng trang {page_num}"

        if front.lower() in existing_fronts:
            continue
        existing_fronts.add(front.lower())
        generated.append(
            {
                "id": f"ai-fc-vocab-{len(generated) + 1}",
                "front": front,
                "back": back,
                "example": example,
                "cardStyle": card_style,
                "status": "new",
                "citation": _make_citation_from_ref(ref),
                "is_mock": False,
            }
        )
    return generated


def _build_prose_grounded_flashcards(
    source_refs: List[Dict[str, Any]],
    needed: int,
    existing_fronts: set[str],
    card_style: str,
) -> List[Dict[str, Any]]:
    """Tạo thêm thẻ Flashcard bám sát các luận điểm/câu văn thực tế trong tài liệu khi LLM sinh thiếu."""
    if not source_refs or needed <= 0:
        return []

    statements = _extract_prose_statements(source_refs, min_len=24, max_len=240)
    if not statements:
        for ref in source_refs:
            snippet = str(ref.get("snippet") or "").strip()
            if snippet:
                statements.append((snippet, ref))
    if not statements:
        return []

    generated: List[Dict[str, Any]] = []
    total = len(statements)
    for i in range(max(needed * 2, total)):
        if len(generated) >= needed:
            break
        stmt, ref = statements[i % total]
        doc_name = ref.get("documentName") or "Tài liệu"
        page_num = ref.get("pageNumber") or 1
        words = stmt.split()

        if card_style == "cloze" and len(words) >= 6:
            hide_idx = max(2, len(words) // 2)
            hidden_word = words[hide_idx].strip(",.;:()[]{}\"'")
            masked = words[:hide_idx] + ["[...]"] + words[hide_idx + 1 :]
            front = " ".join(masked)
            back = f"{hidden_word} — {stmt}"
        elif card_style == "qa":
            head = " ".join(words[:7]).rstrip(",.;:")
            front = f"Nội dung chính liên quan đến \"{head}...\" trong {doc_name} là gì?"
            back = stmt
        elif card_style == "vocabulary":
            term = " ".join(words[:4]).rstrip(",.;:")
            front = f"{term} (#{i + 1})" if term.lower() in existing_fronts else term
            back = stmt
        else:
            split_colon = stmt.split(":", 1)
            if len(split_colon) == 2 and 4 <= len(split_colon[0].strip()) <= 70 and len(split_colon[1].strip()) >= 12:
                front = split_colon[0].strip()
                back = split_colon[1].strip()
            else:
                head = " ".join(words[:6]).rstrip(",.;:")
                front = f"Khái niệm: {head}..."
                back = stmt

        if front.lower() in existing_fronts:
            front = f"{front} ({doc_name} · Tr.{page_num} #{i + 1})"
        if front.lower() in existing_fronts:
            continue
        existing_fronts.add(front.lower())
        generated.append(
            {
                "id": f"ai-fc-doc-{len(generated) + 1}",
                "front": front,
                "back": back,
                "example": f"Trích từ {doc_name} (Trang {page_num})",
                "cardStyle": card_style,
                "status": "new",
                "citation": _make_citation_from_ref(ref),
                "is_mock": False,
            }
        )
    return generated


async def generate_ai_flashcards(
    workspace_id: str,
    document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    count: int = 10,
    focus_prompt: Optional[str] = None,
    model: str = DEFAULT_LLM_MODEL,
    card_style: str = "term_definition",
) -> Dict[str, Any]:
    """
    Sinh bộ thẻ Flashcard (hỗ trợ nhiều kiểu thẻ, ví dụ minh họa, citation và đảm bảo đủ số lượng).
    """
    style_key = card_style if card_style in _FLASHCARD_STYLE_GUIDE else "term_definition"
    style_meta = _FLASHCARD_STYLE_GUIDE[style_key]
    card_count = min(max(count, 1), 40)

    max_chunks = min(28, max(14, card_count + 4))
    max_chars = 8500 if card_count > 12 else 6500
    context, source_refs = _get_document_context_items(
        workspace_id,
        document_id,
        document_ids,
        max_chunks=max_chunks,
        max_chars=max_chars,
        focus_prompt=focus_prompt,
        numbered_sources=True,
    )
    if not context:
        return {
            "title": "Bộ thẻ Flashcards",
            "card_style": style_key,
            "flashcards": [],
            "error": "Chưa có nội dung tài liệu để tạo Flashcards.",
            "is_mock": False,
        }

    chosen_model, model_error = await _ensure_ollama_chat_model(model)
    if model_error or not chosen_model:
        return {
            "title": "Bộ thẻ Flashcards",
            "card_style": style_key,
            "flashcards": [],
            "error": model_error or "Ollama chưa được khởi động.",
            "is_mock": True,
        }

    clean_focus = (focus_prompt or "").strip()
    semantic_focus = clean_focus if clean_focus and not _is_generic_focus_prompt(clean_focus) else None
    vocab_entries = _extract_vocab_entries(source_refs)

    if len(vocab_entries) >= 8:
        sampled_lines: List[str] = []
        step = max(1, len(vocab_entries) // 14)
        for idx in range(0, len(vocab_entries), step):
            ve = vocab_entries[idx]
            ref_idx = ve["ref"].get("ref_index", 1)
            sampled_lines.append(
                f"[Nguồn {ref_idx}] Từ vựng: {ve['term']} | Cách đọc: {ve['reading']} | Nghĩa tiếng Việt: {ve['meaning']}"
            )
            if len(sampled_lines) >= 14:
                break
        llm_context = "\n".join(sampled_lines)
        llm_ask_count = min(card_count, 5)
        llm_timeout = min(OLLAMA_TIMEOUT, 30.0)
        predict_tokens = 750
    else:
        llm_context = context[:3600]
        llm_ask_count = min(card_count, 10)
        llm_timeout = min(OLLAMA_TIMEOUT, 65.0)
        predict_tokens = min(2200, max(900, llm_ask_count * 180))

    system_prompt = (
        f"Bạn là Trợ lý Học tập thông minh. Hãy đọc kỹ các đoạn nguồn [Nguồn 1], [Nguồn 2]... và trích xuất thành "
        f"bộ thẻ Flashcards theo kiểu \"{style_meta['label']}\" bằng tiếng Việt.\n"
        f"HƯỚNG DẪN KIỂU THẺ: {style_meta['instruction']}\n"
        "TUYỆT ĐỐI KHÔNG bịa nội dung ngoài TÀI LIỆU NGUỒN.\n\n"
        "YÊU CẦU ĐỊNH DẠNG JSON:\n"
        "Trả về duy nhất một JSON OBJECT có key 'flashcards':\n"
        "{\n"
        '  "flashcards": [\n'
        "    {\n"
        f'      "front": "{style_meta["front_desc"]}",\n'
        f'      "back": "{style_meta["back_desc"]}",\n'
        '      "example": "Ví dụ áp dụng hoặc ngữ cảnh ngắn trích từ tài liệu (nếu có)",\n'
        '      "sourceIndex": 1\n'
        "    }\n"
        "  ]\n"
        "}\n"
        f"Hãy tạo đúng {llm_ask_count} thẻ Flashcards giá trị nhất."
    )

    user_prompt = f"TÀI LIỆU NGUỒN:\n{llm_context}\n\n"
    if semantic_focus:
        user_prompt += f"TRỌNG TÂM NỘI DUNG CẦN TẠO THẺ: {semantic_focus}\n\n"
    user_prompt += f"Hãy tạo đúng {llm_ask_count} thẻ Flashcards kiểu {style_meta['label']} dạng JSON:"

    valid_cards: List[Dict[str, Any]] = []
    llm_error: Optional[Exception] = None

    try:
        raw_res = await _call_ollama_chat(
            system_prompt,
            user_prompt,
            model=chosen_model,
            json_mode=True,
            timeout_sec=llm_timeout,
            num_predict=predict_tokens,
        )
        valid_cards = _extract_and_normalize_llm_flashcards(raw_res, source_refs, vocab_entries, style_key)
    except Exception as exc:
        llm_error = exc
        logger.warning("LLM sinh Flashcards gặp lỗi hoặc quá thời gian, kiểm tra bổ sung từ tài liệu: %s", exc)

    needed = card_count - len(valid_cards)
    if needed > 0:
        existing_fronts = {c["front"].lower() for c in valid_cards}
        if len(vocab_entries) >= 2:
            valid_cards.extend(
                _build_vocab_grounded_flashcards(
                    vocab_entries,
                    needed=needed,
                    existing_fronts=existing_fronts,
                    card_style=style_key,
                    semantic_focus=semantic_focus,
                )
            )

        needed = card_count - len(valid_cards)
        total_raw_chars = sum(len(str(r.get("_raw_text") or "")) for r in source_refs)
        if needed > 0 and (total_raw_chars >= 80 or not valid_cards):
            valid_cards.extend(
                _build_prose_grounded_flashcards(
                    source_refs,
                    needed=needed,
                    existing_fronts=existing_fronts,
                    card_style=style_key,
                )
            )

    if not valid_cards and llm_error is not None:
        logger.exception("Lỗi khi sinh Flashcards bằng AI: %s", llm_error)
        return {
            "title": "Bộ thẻ Flashcards",
            "card_style": style_key,
            "flashcards": [],
            "error": f"Không thể sinh Flashcards: {str(llm_error)}",
            "is_mock": True,
        }

    final_cards = valid_cards[:card_count]
    for idx, card in enumerate(final_cards):
        card["id"] = f"ai-fc-{idx + 1}"

    primary_doc_name = source_refs[0]["documentName"] if source_refs else "Tài liệu học tập"
    deck_topic = clean_focus[:48] if clean_focus else primary_doc_name[:48]
    return {
        "title": f"Flashcards · {deck_topic}",
        "card_style": style_key,
        "flashcards": final_cards,
        "is_mock": False,
    }


async def generate_ai_mindmap(
    workspace_id: str,
    document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    focus_prompt: Optional[str] = None,
    max_depth: int = 3,
    model: str = DEFAULT_LLM_MODEL,
) -> Dict[str, Any]:
    """
    Sinh sơ đồ tư duy (Mindmap) phân cấp bằng AI từ nội dung tài liệu.
    """
    context = _get_document_context(
        workspace_id,
        document_id,
        document_ids,
        max_chunks=16,
        max_chars=8000,
        focus_prompt=focus_prompt,
    )
    if not context:
        return {
            "root": None,
            "error": "Chưa tìm thấy nội dung văn bản từ tài liệu được chọn.",
            "is_mock": False,
        }

    chosen_model, model_error = await _ensure_ollama_chat_model(model)
    if model_error or not chosen_model:
        return {
            "root": None,
            "error": model_error or "Ollama chưa được khởi động.",
            "is_mock": True,
        }

    depth_limit = min(max(max_depth, 2), 4)
    system_prompt = (
        "Bạn là chuyên gia thiết kế sơ đồ tư duy học tập. Hãy đọc hiểu tài liệu nguồn và xây dựng "
        "một cây Mindmap phân cấp bằng tiếng Việt, phản ánh logic cấu trúc khái niệm của tài liệu.\n\n"
        "BẠN PHẢI TRẢ VỀ DUY NHẤT MỘT JSON OBJECT CÓ DẠNG:\n"
        "{\n"
        '  "label": "Chủ đề gốc ngắn gọn",\n'
        '  "detail": "Mô tả 1 câu về chủ đề gốc",\n'
        '  "children": [\n'
        '    {"label": "Nhánh chính", "detail": "Giải thích ngắn", "children": [\n'
        '      {"label": "Nhánh con", "detail": "Giải thích ngắn"}\n'
        "    ]}\n"
        "  ]\n"
        "}\n"
        f"LƯU Ý: Tối đa {depth_limit} tầng và mỗi node tối đa 6 nhánh con. Không thêm markdown hay giải thích ngoài JSON."
    )
    user_prompt = f"TÀI LIỆU NGUỒN:\n{context}\n\n"
    if focus_prompt and focus_prompt.strip():
        user_prompt += f"TRỌNG TÂM YÊU CẦU: {focus_prompt.strip()}\n\n"
    user_prompt += "Hãy tạo cây Mindmap dạng JSON object theo đúng cấu trúc:"

    try:
        raw_res = await _call_ollama_chat(system_prompt, user_prompt, model=chosen_model, json_mode=True)
        data = _parse_json_response(raw_res)
        root = _normalize_mindmap_node(data, depth=0, max_depth=depth_limit)
        if not root:
            raise ValueError("AI không trả về cấu trúc Mindmap hợp lệ")
        return {"root": root, "is_mock": False}
    except Exception as exc:
        logger.exception("Lỗi khi sinh Mindmap bằng AI: %s", exc)
        return {
            "root": None,
            "error": f"Không thể sinh Mindmap: {str(exc)}",
            "is_mock": True,
        }


async def generate_ai_notes(
    workspace_id: str,
    document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    focus_prompt: Optional[str] = None,
    model: str = DEFAULT_LLM_MODEL,
) -> Dict[str, Any]:
    """
    Sinh ghi chú học tập có cấu trúc Markdown bằng AI từ tài liệu.
    """
    context = _get_document_context(
        workspace_id,
        document_id,
        document_ids,
        max_chunks=16,
        max_chars=8000,
        focus_prompt=focus_prompt,
    )
    if not context:
        return {
            "title": "Ghi chú học tập",
            "markdown": "Chưa tìm thấy nội dung văn bản từ tài liệu được chọn.",
            "error": "Chưa có nội dung tài liệu để tạo ghi chú.",
            "is_mock": False,
        }

    chosen_model, model_error = await _ensure_ollama_chat_model(model)
    if model_error or not chosen_model:
        return {
            "title": "Ghi chú học tập",
            "markdown": "",
            "error": model_error or "Ollama chưa được khởi động.",
            "is_mock": True,
        }

    system_prompt = (
        "Bạn là Trợ lý Học tập AI. Hãy đọc hiểu tài liệu nguồn và soạn một bản GHI CHÚ HỌC TẬP "
        "có cấu trúc rõ ràng bằng Markdown tiếng Việt, giúp sinh viên ôn tập nhanh.\n\n"
        "CẤU TRÚC GHI CHÚ:\n"
        "# Ghi chú: <Tên chủ đề>\n"
        "## 1. Tổng quan ngắn gọn\n"
        "## 2. Thuật ngữ & định nghĩa quan trọng (bảng hoặc gạch đầu dòng)\n"
        "## 3. Các ý chính cần nhớ (phân tích bản chất, không chép nguyên văn)\n"
        "## 4. Câu hỏi tự ôn tập (3-5 câu)\n"
        "## 5. Liên hệ & ứng dụng thực tiễn"
    )
    user_prompt = f"TÀI LIỆU NGUỒN:\n{context}\n\n"
    if focus_prompt and focus_prompt.strip():
        user_prompt += f"TRỌNG TÂM YÊU CẦU: {focus_prompt.strip()}\n\n"
    user_prompt += "Hãy soạn ghi chú học tập theo đúng cấu trúc trên:"

    try:
        markdown_res = await _call_ollama_chat(system_prompt, user_prompt, model=chosen_model)
        return {
            "title": "Ghi chú AI · " + (focus_prompt[:40] + "..." if focus_prompt else "Tài liệu học tập"),
            "markdown": markdown_res,
            "is_mock": False,
        }
    except Exception as exc:
        logger.exception("Lỗi khi sinh ghi chú bằng AI: %s", exc)
        return {
            "title": "Ghi chú học tập",
            "markdown": "",
            "error": f"Không thể sinh ghi chú: {str(exc)}",
            "is_mock": True,
        }


async def generate_ai_plan(
    workspace_id: str,
    document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    day_span: int = 7,
    focus_prompt: Optional[str] = None,
    model: str = DEFAULT_LLM_MODEL,
) -> Dict[str, Any]:
    """
    Sinh lộ trình học tập (danh sách nhiệm vụ kèm hạn hoàn thành) bằng AI từ tài liệu.
    """
    context = _get_document_context(
        workspace_id,
        document_id,
        document_ids,
        max_chunks=14,
        max_chars=7000,
        focus_prompt=focus_prompt,
    )
    if not context:
        return {
            "tasks": [],
            "error": "Chưa có nội dung tài liệu để tạo lộ trình học tập.",
            "is_mock": False,
        }

    chosen_model, model_error = await _ensure_ollama_chat_model(model)
    if model_error or not chosen_model:
        return {
            "tasks": [],
            "error": model_error or "Ollama chưa được khởi động.",
            "is_mock": True,
        }

    try:
        base_date = date.fromisoformat(start_date) if start_date else date.today()
    except ValueError:
        base_date = date.today()
    span = min(max(day_span, 1), 30)

    system_prompt = (
        "Bạn là Chuyên gia Thiết kế Lộ trình Học tập. Hãy đọc hiểu tài liệu và lập kế hoạch học tập "
        "thực tế bằng tiếng Việt gồm 5-8 nhiệm vụ, sắp xếp theo thứ tự ưu tiên và phân bổ đều thời gian.\n\n"
        "BẠN PHẢI TRẢ VỀ DUY NHẤT MỘT JSON OBJECT CÓ DẠNG:\n"
        "{\n"
        '  "tasks": [\n'
        '    {"title": "Nhiệm vụ cụ thể, bắt đầu bằng động từ", "due_offset_days": 1, '
        '"detail": "Cách thực hiện hoặc tiêu chí hoàn thành ngắn gọn"}\n'
        "  ]\n"
        "}\n"
        f"LƯU Ý: due_offset_days là số nguyên từ 0 đến {span} (số ngày kể từ ngày bắt đầu). "
        "Không thêm markdown hay giải thích ngoài JSON."
    )
    user_prompt = f"TÀI LIỆU NGUỒN:\n{context}\n\n"
    if focus_prompt and focus_prompt.strip():
        user_prompt += f"TRỌNG TÂM LỘ TRÌNH: {focus_prompt.strip()}\n\n"
    user_prompt += f"Hãy tạo lộ trình học tập trong {span} ngày kể từ {base_date.isoformat()}, trả về JSON object có key 'tasks':"

    try:
        raw_res = await _call_ollama_chat(system_prompt, user_prompt, model=chosen_model, json_mode=True)
        data = _parse_json_response(raw_res)
        raw_tasks = data if isinstance(data, list) else data.get("tasks", [])
        if not isinstance(raw_tasks, list):
            raw_tasks = []

        tasks = []
        for i, item in enumerate(raw_tasks[:8]):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            try:
                offset = int(item.get("due_offset_days", i + 1))
            except (TypeError, ValueError):
                offset = i + 1
            offset = min(max(offset, 0), span)
            due_date = (base_date + timedelta(days=offset)).isoformat()
            task = {"title": title[:200], "due_date": due_date}
            detail = item.get("detail")
            if detail:
                task["detail"] = str(detail).strip()[:300]
            tasks.append(task)

        if not tasks:
            raise ValueError("AI không trả về nhiệm vụ học tập hợp lệ")
        return {"tasks": tasks, "is_mock": False}
    except Exception as exc:
        logger.exception("Lỗi khi sinh lộ trình học tập bằng AI: %s", exc)
        return {
            "tasks": [],
            "error": f"Không thể sinh lộ trình: {str(exc)}",
            "is_mock": True,
        }
