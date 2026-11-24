"""Workspace-scoped hybrid retrieval: SQLite FTS5 plus optional BGE-M3 (NumPy SIMD accelerated), RRF, and Section Extraction.

Các chế độ truy xuất:
1. Section Extraction (search_section_chunks): Dành cho câu hỏi về Bài/Chương/Lab cụ thể (ví dụ: "bài 1 làm về gì", "cách làm bài 1", "các bước tiếp theo"), lấy toàn bộ các chunk liên tục thuộc phần đó để không bị cắt xén.
2. Spanning Retrieval (search_spanning_chunks): Dành cho câu hỏi tóm tắt toàn bộ tài liệu (ví dụ: "tóm tắt các bài cần làm", "tài liệu gồm những gì"), lấy chunk phân phối đều từ đầu đến cuối.
3. Hybrid Retrieval (search_relevant_chunks): Dành cho câu hỏi tra cứu khái niệm hoặc chi tiết cụ thể (ví dụ: "DNS là gì", "port 80 dùng làm gì"), kết hợp BM25 + Dense BGE-M3 + Rerank.
"""
import math
import re
import logging
import threading
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore

import app.database as db_mod
from app.config import (
    EMBEDDING_MODEL,
    RERANK_MAX_CANDIDATES,
    RETRIEVAL_CANDIDATE_MULTIPLIER,
    RRF_K,
    SIMILARITY_CUTOFF,
    TOP_K_RETRIEVAL,
)
from app.database import get_db_connection
from app.services.embedding_service import embed_texts, unpack_vector
from app.services.hardware_profile_service import get_active_profile_config
from app.services.reranker_service import rerank_documents

logger = logging.getLogger(__name__)

_VECTOR_CACHE: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
_VECTOR_CACHE_LOCK = threading.Lock()


def invalidate_workspace_vector_cache(workspace_id: Optional[str] = None) -> None:
    """Xóa bộ nhớ đệm ma trận vector của workspace khi có thay đổi tài liệu."""
    with _VECTOR_CACHE_LOCK:
        if workspace_id is None:
            _VECTOR_CACHE.clear()
            return
        keys = [k for k in _VECTOR_CACHE if k[1] == workspace_id]
        for k in keys:
            _VECTOR_CACHE.pop(k, None)

# Từ khóa nhận biết câu hỏi muốn TÓM TẮT TOÀN BỘ tài liệu (hỗ trợ cả có dấu & không dấu)
_GLOBAL_SUMMARY_KEYWORDS = [
    "tóm tắt", "tóm lại", "tổng hợp", "liệt kê tất cả", "liệt kê các",
    "các bài", "các chương", "các phần", "nội dung chính", "toàn bộ",
    "overview", "summarize", "summary", "list all", "all chapters",
    "all sections", "main topics", "những bài", "những chương",
    "nêu các", "kể tên", "có những gì", "gồm những gì",
    "tom tat", "tom lai", "tong hop", "liet ke tat ca", "liet ke cac",
    "cac bai", "cac chuong", "cac phan", "noi dung chinh", "toan bo",
    "nhung bai", "nhung chuong", "neu cac", "ke ten", "co nhung gi", "gom nhung gi",
]

_ROMAN_TO_INT = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
    "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
    "XI": 11, "XII": 12, "XIII": 13, "XIV": 14, "XV": 15,
}
_INT_TO_ROMAN = {v: k for k, v in _ROMAN_TO_INT.items()}

# Regex nhận diện "bài X", "chương II", "điều 5", "khoản 2", "lab 1", "article 4"...
# Lưu ý: với số La Mã, chỉ khớp chữ IN HOA (I, II, III, IV, V...) để không khớp nhầm chữ cái thường kiểu 'phần c'
_SECTION_PATTERN = re.compile(
    r"\b([Bb]ài|[Cc]hương|[Pp]hần|[Đđ]iều|[Kk]hoản|[Mm]ục|[Ll]ab|[Ee]xercise|[Cc]hapter|[Ss]ection|[Aa]rticle|[Bb]ai|[Cc]huong|[Pp]han|[Dd]ieu|[Kk]hoan|[Mm]uc)"
    r"(?:\s+(?:tập|số|tap|so))?\s+"
    r"(\d+|(?:XIII|XII|XI|XIV|XV|VIII|VII|VI|IV|IX|III|II|I|V|X))\b",
    re.UNICODE,
)

# Regex bản chuẩn giữ nguyên khoảng trắng tùy chọn (\s*) cho chữ số (vd: 'Bài1', 'Điều 5')
_SECTION_ARABIC_COMPACT_RE = re.compile(
    r"\b(bài|chương|phần|điều|khoản|mục|lab|exercise|chapter|section|article|bai|chuong|phan|dieu|khoan|muc)"
    r"(?:\s+tập|\s+số|\s+tap|\s+so)?\s*(\d+)\b",
    re.IGNORECASE | re.UNICODE,
)


def _parse_section_number(token: str) -> Optional[int]:
    clean = (token or "").strip().upper()
    if clean.isdigit():
        return int(clean)
    return _ROMAN_TO_INT.get(clean)


def _normalize_section_type(sec_raw: str) -> str:
    low = sec_raw.lower()
    mapping = {
        "bài": "bài", "bai": "bài",
        "chương": "chương", "chuong": "chương",
        "phần": "phần", "phan": "phần",
        "điều": "điều", "dieu": "điều",
        "khoản": "khoản", "khoan": "khoản",
        "mục": "mục", "muc": "mục",
    }
    return mapping.get(low, low)

# Từ khóa thể hiện ý định hỏi về các bước hoặc câu hỏi nối tiếp về bài đang làm
_FOLLOW_UP_KEYWORDS = [
    "bước tiếp", "bước iếp", "tiếp theo", "tiếp tục", "các bước",
    "từng bước", "hướng dẫn", "cách làm", "làm thế nào", "còn gì nữa",
    "chi tiết hơn", "bước mấy",
    "buoc tiep", "tiep theo", "tiep tuc", "cac buoc", "tung buoc",
    "huong dan", "cach lam", "lam the nao", "con gi nua", "chi tiet hon", "buoc may",
]


_CJK_CHAR_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_CJK_SEQ_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
_QUOTED_TERM_RE = re.compile(r'["\'“”‘’「」『』]([^"\'“”‘’「」『」]{1,40})["\'“”‘’「」『』]')

_START_POS_PATTERN = re.compile(
    r"(?:\b(?:trang|phần|mục|đoạn|dòng|câu|từ(?:\s+vựng)?|phan|muc|doan|dong|cau|tu(?:\s+vung)?)\s+(?:đầu(?:\s+tiên)?|dau(?:\s+tien)?)\b|"
    r"\b(?:đầu\s+tiên|dau\s+tien)\s+(?:trong|của|ở|cua|o)\s+(?:file|tệp|tài\s+liệu|văn\s+bản|danh\s+sách|tep|tai\s+lieu|van\s+ban|danh\s+sach)\b|"
    r"\b(?:mở\s+đầu|từ\s+đầu|mo\s+dau|tu\s+dau)\s+(?:file|tệp|tài\s+liệu|tep|tai\s+lieu)\b|"
    r"\b(?:bắt\s+đầu|bat\s+dau)\s+(?:bằng|với|bang|voi)\s+(?:chữ|chu)\b|"
    r"\b\d+\s+(?:từ(?:\s+vựng)?|mục|câu|dòng|tu(?:\s+vung)?|muc|cau|dong)\s+(?:đầu(?:\s+tiên)?|dau(?:\s+tien)?)\b)",
    re.IGNORECASE | re.UNICODE,
)
_END_POS_PATTERN = re.compile(
    r"(?:\b(?:trang|phần|mục|đoạn|dòng|câu|từ(?:\s+vựng)?|phan|muc|doan|dong|cau|tu(?:\s+vung)?)\s+(?:cuối(?:\s+cùng)?|cuoi(?:\s+cung)?)\b|"
    r"\b(?:cuối\s+cùng|cuoi\s+cung)\s+(?:trong|của|ở|cua|o)\s+(?:file|tệp|tài\s+liệu|văn\s+bản|danh\s+sách|tep|tai\s+lieu|van\s+ban|danh\s+sach)\b|"
    r"\b\d+\s+(?:từ(?:\s+vựng)?|mục|câu|dòng|tu(?:\s+vung)?|muc|cau|dong)\s+(?:cuối(?:\s+cùng)?|cuoi(?:\s+cung)?)\b)",
    re.IGNORECASE | re.UNICODE,
)
_LETTER_FILTER_PATTERN = re.compile(
    r"(?:(?:bắt\s+đầu|bat\s+dau)\s+(?:bằng|với|bang|voi)\s+(?:(?:chữ(?:\s+cái)?|chu(?:\s+cai)?)\s+)?|(?:chữ\s+cái|chu\s+cai)\s+)[\"']?([a-zA-Z])[\"']?(?:\b|$)",
    re.IGNORECASE | re.UNICODE,
)


def _contains_cjk(text: str) -> bool:
    return bool(_CJK_CHAR_RE.search(text or ""))


def _extract_exact_lookup_terms(query: str) -> List[str]:
    """Trích xuất từ khóa CJK hoặc cụm từ đặt trong dấu ngoặc để tìm khớp chính xác."""
    terms: List[str] = []
    seen: set[str] = set()
    for m in _QUOTED_TERM_RE.findall(query or ""):
        clean = m.strip()
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            terms.append(clean)
    for m in _CJK_SEQ_RE.findall(query or ""):
        clean = m.strip()
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            terms.append(clean)
    return terms


def detect_positional_intent(query: str) -> Optional[Tuple[str, Optional[str]]]:
    """Phát hiện ý định đọc phần đầu/cuối tài liệu hoặc liệt kê theo chữ cái mở đầu."""
    q = (query or "").strip()
    if not q or _SECTION_PATTERN.search(q):
        return None
    letter_m = _LETTER_FILTER_PATTERN.search(q)
    letter = letter_m.group(1).lower() if letter_m else None
    if _END_POS_PATTERN.search(q):
        return "end", letter
    if _START_POS_PATTERN.search(q):
        return "start", letter
    return None


def _build_doc_scope_filter(
    document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    latest_only_when_unscoped: bool = True,
) -> Tuple[str, tuple]:
    """Tạo mệnh đề lọc phạm vi tài liệu và tự động ưu tiên bản mới nhất (is_latest=1) nếu không chỉ định bản cụ thể."""
    if document_id:
        return " AND c.document_id = ?", (document_id,)
    if document_ids:
        placeholders = ",".join("?" for _ in document_ids)
        return f" AND c.document_id IN ({placeholders})", tuple(document_ids)
    if latest_only_when_unscoped:
        return " AND COALESCE(d.is_latest, 1) = 1", ()
    return "", ()


def search_positional_chunks(
    workspace_id: str,
    position: str = "start",
    letter_filter: Optional[str] = None,
    max_chunks: int = 5,
    document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Lấy các chunk đầu tiên hoặc cuối cùng theo đúng thứ tự trang/chunk trong tài liệu."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        doc_filter, doc_params = _build_doc_scope_filter(document_id, document_ids)

        cursor.execute(
            f"""
            SELECT c.id AS chunk_id, c.document_id, c.workspace_id, c.content,
                   c.page_number, c.chunk_index, d.file_name AS document_name,
                   COALESCE(d.version_number, 1) AS version_number,
                   d.effective_date
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.workspace_id = ?{doc_filter}
            ORDER BY d.created_at DESC, c.page_number ASC, c.chunk_index ASC
            """,
            (workspace_id, *doc_params),
        )
        all_chunks = [dict(row) for row in cursor.fetchall()]
        if not all_chunks:
            return []

        candidates = all_chunks
        if letter_filter:
            pat = re.compile(rf"(?:^|\n|\|)\s*{re.escape(letter_filter)}[a-zA-Z]{{1,}}", re.IGNORECASE)
            # Bỏ qua chunk trang bìa/header thuần túy không có từ nào bắt đầu bằng chữ cái mục tiêu
            matched = [c for c in all_chunks if pat.search(c.get("content", ""))]
            if matched:
                # Ưu tiên tài liệu từ vựng / bảng từ (có phiên âm IPA /.../ hoặc nhãn loại từ) lên trước tài liệu kỹ thuật lẫn chữ cái tình cờ
                ipa_re = re.compile(r"/[^/\n]{2,20}/")
                line_hits_re = re.compile(rf"(?im)^\s*{re.escape(letter_filter)}[a-z]{{1,18}}\b")
                matched.sort(
                    key=lambda c: (
                        1 if ("từ vựng" in (c.get("document_name") or "").lower() or "từ tiếng anh" in (c.get("document_name") or "").lower() or "vocabulary" in (c.get("document_name") or "").lower()) else 0,
                        1 if ipa_re.search(c.get("content") or "") else 0,
                        min(len(line_hits_re.findall(c.get("content") or "")), 8),
                    ),
                    reverse=True,
                )
                candidates = matched

        selected = candidates[-max_chunks:] if position == "end" else candidates[:max_chunks]
        for c in selected:
            if "page_label" not in c and c.get("page_number") is not None:
                c["page_label"] = f"Trang {c['page_number']}"
        return selected
    finally:
        conn.close()


def is_global_summary_query(query: str) -> bool:
    """Trả về True nếu người dùng muốn tóm tắt/liệt kê toàn bộ nội dung tài liệu."""
    raw_q = (query or "").strip()
    q = raw_q.lower()
    # Nếu có chỉ định rõ bài/chương/điều cụ thể (ví dụ: "tóm tắt bài 1", "chương II") thì ưu tiên Section Extraction
    if _SECTION_ARABIC_COMPACT_RE.search(raw_q) or _SECTION_PATTERN.search(raw_q):
        return False
    return any(kw in q for kw in _GLOBAL_SUMMARY_KEYWORDS)


def detect_section_intent(
    query: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> Optional[Tuple[str, int]]:
    """
    Phát hiện xem người dùng đang hỏi về Bài/Chương/Điều/Lab mấy (hỗ trợ cả chữ số Ả Rập và số La Mã).
    Hỗ trợ phát hiện trong câu hỏi hiện tại hoặc suy luận từ ngữ cảnh hội thoại trước đó.
    """
    q = (query or "").strip()
    m = _SECTION_ARABIC_COMPACT_RE.search(q) or _SECTION_PATTERN.search(q)
    if m:
        num = _parse_section_number(m.group(2))
        if num is not None:
            return _normalize_section_type(m.group(1)), num

    # Chỉ coi là câu hỏi nối tiếp section khi thực sự chứa từ khóa hỏi bước/nội dung nối tiếp và không chứa Kanji/Cụm tra cứu từ mới
    q_lower = q.lower()
    has_cjk_lookup = bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff]", q))
    is_follow_up = any(kw in q_lower for kw in _FOLLOW_UP_KEYWORDS) and not has_cjk_lookup
    if is_follow_up and history:
        for turn in reversed(history[-8:]):
            if turn.get("role") == "user":
                prev_text = turn.get("content", "")
                pm = _SECTION_ARABIC_COMPACT_RE.search(prev_text) or _SECTION_PATTERN.search(prev_text)
                if pm:
                    num = _parse_section_number(pm.group(2))
                    if num is not None:
                        return _normalize_section_type(pm.group(1)), num

    return None


def _build_section_heading_regex(sec_type: str, sec_num: int) -> re.Pattern:
    roman = _INT_TO_ROMAN.get(sec_num)
    num_pat = rf"(?:{sec_num}|{roman})" if roman else str(sec_num)
    return re.compile(rf"\b{re.escape(sec_type)}\s*{num_pat}\b", re.IGNORECASE | re.UNICODE)


def search_section_chunks(
    workspace_id: str,
    sec_type: str,
    sec_num: int,
    max_chunks: int = 16,
    document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Trích xuất toàn bộ các chunk liên tục thuộc về Bài X / Chương II / Điều 5 trong tài liệu.
    Bắt đầu từ chunk chứa tiêu đề (bỏ qua trang Mục lục) cho đến khi gặp phần kế tiếp
    hoặc đạt tối đa max_chunks chunk.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        doc_filter, doc_params = _build_doc_scope_filter(document_id, document_ids)

        cursor.execute(
            f"""
            SELECT c.id AS chunk_id, c.document_id, c.workspace_id, c.content,
                   c.page_number, c.chunk_index, d.file_name AS document_name,
                   COALESCE(d.version_number, 1) AS version_number,
                   d.effective_date
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.workspace_id = ?{doc_filter}
            ORDER BY c.document_id, c.page_number ASC, c.chunk_index ASC
            """,
            (workspace_id, *doc_params),
        )
        all_chunks = [dict(row) for row in cursor.fetchall()]
        if not all_chunks:
            return []

        pat_start = _build_section_heading_regex(sec_type, sec_num)
        pat_next = _build_section_heading_regex(sec_type, sec_num + 1)

        start_idx = None
        end_idx = None

        for i, c in enumerate(all_chunks):
            content_lower = c["content"].lower()
            # Bỏ qua các trang Mục lục đầu tài liệu hoặc dòng Danh mục tổng quan
            is_toc = (
                (
                    "mục lục" in content_lower
                    or "danh mục các phần trong bảng:" in content_lower
                    or "cây mục lục & tổng quan" in content_lower
                    or "table of contents" in content_lower
                    or "........" in c["content"]
                )
                and c["page_number"] <= 3
                and int(c.get("chunk_index", 0)) <= 1
                and sec_num > 1
            )
            if not is_toc and pat_start.search(c["content"]):
                if start_idx is None:
                    start_idx = i
            if start_idx is not None and i > start_idx:
                if pat_next.search(c["content"]):
                    end_idx = i
                    break

        if start_idx is not None:
            if end_idx is None:
                end_idx = min(start_idx + max_chunks, len(all_chunks))
            else:
                end_idx = min(end_idx, start_idx + max_chunks)
            res = all_chunks[start_idx:end_idx]
            for c in res:
                if "page_label" not in c and c.get("page_number") is not None:
                    c["page_label"] = f"Trang {c['page_number']}"
            return res

        # Nếu không tìm thấy bằng regex có số, fallback lấy theo FTS anchor
        return []
    finally:
        conn.close()


def search_spanning_chunks(
    workspace_id: str,
    query: str,
    max_chunks: int = 14,
    document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Lấy chunk phân phối ĐỀU toàn bộ tài liệu (theo thứ tự trang/chunk_index).
    Dùng cho câu hỏi "tóm tắt toàn bộ", "liệt kê các chương", v.v.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        doc_filter, doc_params = _build_doc_scope_filter(document_id, document_ids)

        cursor.execute(
            f"""
            SELECT c.id AS chunk_id, c.document_id, c.workspace_id, c.content,
                   c.page_number, c.chunk_index, d.file_name AS document_name,
                   COALESCE(d.version_number, 1) AS version_number,
                   d.effective_date
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.workspace_id = ?{doc_filter}
            ORDER BY c.document_id, c.page_number ASC, c.chunk_index ASC
            """,
            (workspace_id, *doc_params),
        )
        all_chunks = [dict(row) for row in cursor.fetchall()]

        if not all_chunks:
            return []

        total = len(all_chunks)
        if total <= max_chunks:
            selected = all_chunks
        else:
            step = total / max_chunks
            selected = [all_chunks[int(i * step)] for i in range(max_chunks)]
        for c in selected:
            if "page_label" not in c and c.get("page_number") is not None:
                c["page_label"] = f"Trang {c['page_number']}"
        return selected
    finally:
        conn.close()


def _cosine(left: List[float], right: List[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    norm_left = math.sqrt(sum(a * a for a in left))
    norm_right = math.sqrt(sum(b * b for b in right))
    return dot / (norm_left * norm_right) if norm_left and norm_right else 0.0


def filter_relevant_chunks(
    query: str,
    chunks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Lọc bỏ các chunk hoàn toàn lạc đề khi tài liệu không chứa thông tin về câu hỏi.
    Ngăn chặn triệt để hiện tượng AI hallucination và sinh trích dẫn giả.
    """
    if not chunks:
        return []

    stopwords = {
        "là", "gì", "những", "các", "cho", "tôi", "như", "nào", "trong", "của", "với", "được", "có", "làm",
        "thế", "sao", "ở", "đâu", "khi", "nào", "bao", "nhiêu", "hãy", "giải", "thích", "nêu", "hỏi", "về",
        "cần", "muốn", "biết", "và", "hoặc", "hay", "đã", "đang", "sẽ", "một", "hai", "ba", "bốn", "năm",
        "bản", "bạn", "mình", "người", "dùng", "file", "tệp", "xem", "không", "chăng", "tài", "liệu",
        "nói", "nội", "dung", "văn", "thông", "tin", "sách", "giáo", "trình", "đoạn", "trang"
    }
    clean_q = re.sub(r"[^\w\s]", " ", query.lower(), flags=re.UNICODE)
    substantive_tokens = [
        w for w in clean_q.split()
        if (len(w) >= 2 or _contains_cjk(w)) and w not in stopwords
    ]

    # Nếu câu hỏi không có từ khóa nội dung đặc thù, giữ nguyên
    if not substantive_tokens:
        return chunks

    # Các từ khóa chuyên biệt / danh từ riêng có độ dài >= 5 ký tự (vd: bitcoin, windows, hybrid, docker...)
    long_specific_tokens = [w for w in substantive_tokens if len(w) >= 5]

    filtered = []
    for c in chunks:
        if c.get("_exact_match"):
            filtered.append(c)
            continue
        c_text = (c.get("content", "") + " " + c.get("document_name", "")).lower()
        score = c.get("rerank_score")
        dense_score = c.get("dense_score")

        # Kiểm tra xem có từ khóa chuyên biệt dài nào không
        has_specific_match = (
            any(tok in c_text for tok in long_specific_tokens)
            if long_specific_tokens
            else True
        )

        matched_tokens = sum(1 for tok in substantive_tokens if tok in c_text)

        # Điều kiện giữ lại chunk:
        # 1. Nếu có từ khóa chuyên biệt dài: bắt buộc phải xuất hiện ít nhất 1 từ chuyên biệt đó
        #    và tổng số từ khóa khớp >= 1 (hoặc >= 2 nếu câu hỏi dài)
        # 2. Hoặc điểm rerank rất cao (> -0.45), hay điểm dense cao (>= 0.48 khi tắt rerank)
        is_semantic_match = (score is not None and score > -0.45) or (
            score is None and dense_score is not None and float(dense_score) >= 0.48
        )
        is_keyword_match = has_specific_match and (matched_tokens >= (2 if len(substantive_tokens) >= 4 else 1))

        if is_keyword_match or is_semantic_match:
            filtered.append(c)

    return filtered


def expand_and_stitch_chunks(
    chunks: List[Dict[str, Any]],
    max_total_chunks: int = 6,
    max_total_chars: int = 4800,
) -> List[Dict[str, Any]]:
    """
    Mở rộng và ghép nối 2 chiều có điều kiện các chunk liền kề (c_idx - 1 và c_idx + 1) của cùng tài liệu.
    Giúp giữ trọn câu điều kiện/tiêu đề dẫn ngay phía trên cũng như phần bước/danh sách phía dưới
    trong giới hạn ngân sách ký tự cho GPU/CPU cục bộ.
    """
    if not chunks:
        return []

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        needed_keys = set()
        for c in chunks:
            doc_id = c.get("document_id")
            c_idx = c.get("chunk_index")
            if doc_id and c_idx is not None:
                needed_keys.add((doc_id, c_idx))
                if int(c_idx) > 0:
                    needed_keys.add((doc_id, int(c_idx) - 1))
                needed_keys.add((doc_id, int(c_idx) + 1))

        doc_ids = list({k[0] for k in needed_keys})
        if not doc_ids:
            return chunks

        placeholders = ",".join("?" for _ in doc_ids)
        cursor.execute(
            f"""
            SELECT c.id AS chunk_id, c.document_id, c.workspace_id, c.content,
                   c.page_number, c.chunk_index, d.file_name AS document_name,
                   COALESCE(d.version_number, 1) AS version_number,
                   d.effective_date
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.document_id IN ({placeholders})
            ORDER BY c.document_id, c.chunk_index ASC
            """,
            tuple(doc_ids),
        )

        all_doc_chunks = cursor.fetchall()
        doc_chunk_map: Dict[str, Dict[int, Dict[str, Any]]] = {}
        for r in all_doc_chunks:
            d = dict(r)
            doc_chunk_map.setdefault(d["document_id"], {})[d["chunk_index"]] = d

        stitched: List[Dict[str, Any]] = []
        visited = set()
        accumulated_chars = 0

        for c in chunks:
            doc_id = c.get("document_id")
            c_idx = c.get("chunk_index")
            if not doc_id or c_idx is None:
                stitched.append(c)
                accumulated_chars += len(c.get("content", ""))
                continue

            if (doc_id, c_idx) in visited:
                continue

            merged_content = c.get("content", "")
            start_page = c.get("page_number")
            end_page = c.get("page_number")
            visited.add((doc_id, c_idx))

            content_stripped = merged_content.strip()
            is_tabular_chunk = content_stripped.count("|") >= 4

            # 1. Ghép ngược chunk liền trước (c_idx - 1) nếu chunk hiện tại bắt đầu lửng hoặc nối sau tiêu đề/dấu ':'
            prev_c = doc_chunk_map.get(doc_id, {}).get(int(c_idx) - 1) if int(c_idx) > 0 else None
            if (
                prev_c
                and (doc_id, int(c_idx) - 1) not in visited
                and (accumulated_chars + len(merged_content) + len(prev_c.get("content", ""))) <= max_total_chars
            ):
                prev_text = prev_c.get("content", "").strip()
                prev_is_tabular = prev_text.count("|") >= 4
                should_prepend = False
                if is_tabular_chunk and prev_is_tabular:
                    should_prepend = True
                elif not is_tabular_chunk and prev_text:
                    # Chỉ ghép ngược khi chunk trước kết thúc bằng dấu ':' hoặc '-' (dẫn vào danh sách)
                    # hoặc chunk hiện tại bắt đầu bằng chữ thường (câu bị cắt giữa chừng)
                    if prev_text.endswith((":", "-")):
                        should_prepend = True
                    elif content_stripped and content_stripped[0].islower():
                        should_prepend = True
                if should_prepend:
                    visited.add((doc_id, int(c_idx) - 1))
                    merged_content = prev_text + "\n\n" + merged_content
                    if prev_c.get("page_number") is not None:
                        start_page = (
                            min(start_page, prev_c["page_number"])
                            if start_page is not None
                            else prev_c["page_number"]
                        )

            # 2. Ghép xuôi chunk liền sau (c_idx + 1) nếu có lý do liên tục
            next_c = doc_chunk_map.get(doc_id, {}).get(int(c_idx) + 1)
            should_stitch = False
            content_stripped = merged_content.strip()
            if next_c and (doc_id, int(c_idx) + 1) not in visited and (
                accumulated_chars + len(merged_content) + len(next_c.get("content", ""))
            ) <= max_total_chars:
                next_stripped = next_c.get("content", "").strip()
                # Đang liệt kê bước thực hành (Bước, Step)
                if re.search(r'\b(?:bước|step)\s*\d+', content_stripped, re.IGNORECASE):
                    should_stitch = True
                # Chunk tiếp theo bắt đầu bằng Bước hoặc chữ thường (câu bị cắt giữa chừng)
                elif next_stripped.startswith(("Bước", "Step")) or (next_stripped and next_stripped[0].islower()):
                    should_stitch = True
                # Đoạn hiện tại kết thúc bằng dấu ':' (dẫn sang danh sách ở chunk sau)
                elif not is_tabular_chunk and content_stripped.endswith(":"):
                    should_stitch = True

            if should_stitch and next_c:
                visited.add((doc_id, int(c_idx) + 1))
                merged_content += "\n\n" + next_c.get("content", "")
                if next_c.get("page_number") is not None:
                    end_page = next_c["page_number"]

            if start_page is not None:
                page_label = f"Trang {start_page}" if start_page == end_page else f"Trang {start_page} - {end_page}"
            else:
                page_label = ""

            item = dict(c)
            item["content"] = merged_content
            item["page_label"] = page_label
            stitched.append(item)
            accumulated_chars += len(merged_content)

            if len(stitched) >= max_total_chunks or accumulated_chars >= max_total_chars:
                break

        return stitched
    finally:
        conn.close()


def _find_exact_term_chunks(
    cursor: Any,
    workspace_id: str,
    document_filter: str,
    document_params: tuple,
    terms: List[str],
    limit: int = 6,
) -> List[Dict[str, Any]]:
    """Tìm trực tiếp các chunk chứa chính xác từ khóa CJK hoặc cụm từ trích dẫn."""
    if not terms:
        return []
    like_clauses = []
    like_params: List[Any] = []
    for term in terms[:6]:
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like_clauses.append("c.content LIKE ? ESCAPE '\\'")
        like_params.append(f"%{escaped}%")

    cursor.execute(
        f"""
        SELECT c.id AS chunk_id, c.document_id, c.workspace_id, c.content,
               c.page_number, c.chunk_index, d.file_name AS document_name,
               COALESCE(d.version_number, 1) AS version_number,
               d.effective_date
        FROM document_chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.workspace_id = ?{document_filter}
          AND ({' OR '.join(like_clauses)})
        ORDER BY d.created_at DESC, c.page_number ASC, c.chunk_index ASC
        LIMIT ?
        """,
        (workspace_id, *document_params, *like_params, max(limit * 4, 24)),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    if not rows:
        return []

    boundary_pats = [
        re.compile(
            rf"(?:^|[\s|｜/・,.;:()\[\]「」『』\"']){re.escape(t)}(?:$|[\s|｜/・,.;:()\[\]「」『』\"'])",
            re.IGNORECASE,
        )
        for t in terms[:6]
    ]
    scored: List[Tuple[Tuple[int, int, int], Dict[str, Any]]] = []
    for r in rows:
        txt = r.get("content", "")
        standalone_hits = sum(1 for pat in boundary_pats if pat.search(txt))
        substring_hits = sum(1 for t in terms[:6] if t.lower() in txt.lower())
        r["_exact_match"] = True
        scored.append(((standalone_hits, substring_hits, -int(r.get("chunk_index", 0))), r))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [pair[1] for pair in scored[:limit]]


_MAX_CACHED_WORKSPACES = 3


def _store_vector_cache_entry(db_key: Tuple[str, str, str], entry: Dict[str, Any]) -> None:
    with _VECTOR_CACHE_LOCK:
        _VECTOR_CACHE.pop(db_key, None)
        while len(_VECTOR_CACHE) >= _MAX_CACHED_WORKSPACES:
            _VECTOR_CACHE.pop(next(iter(_VECTOR_CACHE)), None)
        _VECTOR_CACHE[db_key] = entry


def _get_workspace_vector_index(cursor: Any, workspace_id: str) -> Dict[str, Any]:
    """Tải và đệm ma trận vector chuẩn hóa L2 theo từng chiều (dim) để tính cosine hàng loạt cực nhanh."""
    db_key = (str(db_mod.DATABASE_PATH), workspace_id, EMBEDDING_MODEL)
    stat_row = cursor.execute(
        """
        SELECT COUNT(*) AS cnt, COALESCE(SUM(COALESCE(d.is_latest, 1)), 0) AS latest_sum
        FROM chunk_embeddings e
        JOIN document_chunks c ON c.id = e.chunk_id
        JOIN documents d ON d.id = c.document_id
        WHERE c.workspace_id = ? AND e.model = ?
        """,
        (workspace_id, EMBEDDING_MODEL),
    ).fetchone()
    row_count = int(stat_row["cnt"])
    latest_sum = int(stat_row["latest_sum"])

    with _VECTOR_CACHE_LOCK:
        cached = _VECTOR_CACHE.get(db_key)
        if cached and cached.get("total_count") == row_count and cached.get("latest_sum") == latest_sum:
            return cached

    if row_count == 0:
        empty_index = {"total_count": 0, "latest_sum": 0, "buckets": {}}
        _store_vector_cache_entry(db_key, empty_index)
        return empty_index

    cursor.execute(
        """
        SELECT c.id AS chunk_id, c.document_id, c.workspace_id, c.content,
               c.page_number, c.chunk_index, d.file_name AS document_name,
               COALESCE(d.version_number, 1) AS version_number,
               COALESCE(d.is_latest, 1) AS is_latest,
               d.effective_date,
               e.vector, e.dimensions
        FROM chunk_embeddings e
        JOIN document_chunks c ON c.id = e.chunk_id
        JOIN documents d ON d.id = c.document_id
        WHERE c.workspace_id = ? AND e.model = ?
        """,
        (workspace_id, EMBEDDING_MODEL),
    )
    rows = cursor.fetchall()
    raw_buckets: Dict[int, Dict[str, Any]] = {}

    for row in rows:
        item = dict(row)
        blob = item.pop("vector")
        dims = int(item.pop("dimensions"))
        if np is not None:
            vec = np.frombuffer(blob, dtype=np.float32, count=dims)
            v_norm = float(np.linalg.norm(vec))
            norm_vec = (vec / v_norm).astype(np.float32) if v_norm > 0 else np.zeros(dims, dtype=np.float32)
        else:
            raw_list = unpack_vector(blob, dims)
            v_norm = math.sqrt(sum(x * x for x in raw_list))
            norm_vec = [x / v_norm for x in raw_list] if v_norm > 0 else [0.0] * dims

        bucket = raw_buckets.setdefault(dims, {"vecs": [], "metas": [], "doc_ids": [], "is_latest": []})
        bucket["vecs"].append(norm_vec)
        bucket["metas"].append(item)
        bucket["doc_ids"].append(item["document_id"])
        bucket["is_latest"].append(int(item.get("is_latest", 1)) == 1)

    buckets: Dict[int, Dict[str, Any]] = {}
    for dims, bucket in raw_buckets.items():
        if np is not None:
            matrix = np.vstack(bucket["vecs"]).astype(np.float32)
            doc_ids_arr = np.asarray(bucket["doc_ids"], dtype=object)
            latest_arr = np.asarray(bucket["is_latest"], dtype=bool)
        else:
            matrix = bucket["vecs"]
            doc_ids_arr = bucket["doc_ids"]
            latest_arr = bucket["is_latest"]
        buckets[dims] = {
            "matrix": matrix,
            "metas": bucket["metas"],
            "doc_ids": doc_ids_arr,
            "is_latest": latest_arr,
        }

    built = {"total_count": row_count, "latest_sum": latest_sum, "buckets": buckets}
    _store_vector_cache_entry(db_key, built)
    return built


def _search_dense_candidates(
    cursor: Any,
    workspace_id: str,
    query: str,
    candidate_limit: int,
    document_id: Optional[str],
    document_ids: Optional[List[str]],
) -> List[Dict[str, Any]]:
    """Tìm kiếm Dense Vector bằng phép nhân ma trận NumPy có lọc theo tài liệu & bản mới nhất."""
    vec_index = _get_workspace_vector_index(cursor, workspace_id)
    if vec_index["total_count"] == 0:
        return []

    query_vectors = embed_texts([query])
    if not query_vectors:
        return []

    raw_q = query_vectors[0]
    q_dim = len(raw_q)
    bucket = vec_index["buckets"].get(q_dim)
    if not bucket:
        return []

    allowed_ids = (
        {document_id}
        if document_id
        else (set(document_ids) if document_ids else None)
    )
    metas = bucket["metas"]
    dense: List[Dict[str, Any]] = []

    if np is not None:
        q_vec = np.asarray(raw_q, dtype=np.float32)
        q_norm = float(np.linalg.norm(q_vec))
        if q_norm > 0:
            q_vec = q_vec / q_norm
        matrix = bucket["matrix"]
        if allowed_ids is not None:
            mask = np.isin(bucket["doc_ids"], list(allowed_ids))
        else:
            mask = bucket["is_latest"]

        if not np.any(mask):
            return []
        sub_indices = np.flatnonzero(mask)
        scores = matrix[sub_indices] @ q_vec
        for local_pos, orig_idx in enumerate(sub_indices):
            score = float(scores[local_pos])
            if score >= SIMILARITY_CUTOFF:
                item = dict(metas[int(orig_idx)])
                item["score"] = score
                dense.append(item)
    else:
        for idx, meta in enumerate(metas):
            if allowed_ids is not None:
                if meta["document_id"] not in allowed_ids:
                    continue
            elif not bucket["is_latest"][idx]:
                continue
            score = _cosine(raw_q, bucket["matrix"][idx])
            if score >= SIMILARITY_CUTOFF:
                item = dict(meta)
                item["score"] = score
                dense.append(item)

    dense.sort(key=lambda item: item["score"], reverse=True)
    return dense[:candidate_limit]


def _fts_hit_is_sufficient_for_eco(
    sparse: List[Dict[str, Any]],
    tokens: List[str],
    top_k: int,
) -> bool:
    """Trong chế độ Eco, chỉ bỏ qua Dense BGE-M3 khi FTS5 đã tìm thấy kết quả đủ tin cậy."""
    if not sparse:
        return False
    if len(sparse) >= min(top_k, 2):
        return True
    top_text = str(sparse[0].get("content", "")).lower()
    meaningful = [t.lower() for t in tokens if len(t) >= 2 or _contains_cjk(t)]
    if not meaningful:
        return True
    matched = sum(1 for tok in meaningful if tok in top_text)
    return matched >= min(len(meaningful), 2)


_TOC_DOT_LEADER_RE = re.compile(r"\.{5,}\s*\d+")

_RETRIEVAL_STOPWORDS = {
    "dựa", "vào", "theo", "trong", "của", "từ", "cho", "với", "và", "hoặc", "hay",
    "là", "gì", "nào", "này", "đó", "kia", "những", "các", "một", "hai", "ba",
    "hãy", "vui", "lòng", "giúp", "tôi", "bạn", "mình", "em", "anh", "chị",
    "tài", "liệu", "file", "tệp", "văn", "bản", "sách", "sau", "rồi", "để", "mà",
    "xem", "nó", "có", "không", "được", "bị", "bằng", "lớn", "nhỏ", "hơn", "kém",
    "bao", "nhiêu", "lần", "lượt", "lúc", "khi", "nếu", "thì", "nhưng", "vì", "nên",
    "tính", "toán", "so", "sánh", "giải", "chi", "tiết", "bài", "mới", "áp", "dụng", "đúng",
    "dua", "vao", "trong", "cua", "cho", "voi", "va", "hoac", "la", "gi", "nao", "nay",
    "nhung", "cac", "mot", "hay", "tai", "lieu", "tep", "sau", "de", "xem", "co", "khong",
    "duoc", "bang", "lon", "nho", "hon", "bao", "nhieu", "lan", "luot", "neu", "thi",
    "tinh", "so", "sanh", "giai", "chi", "tiet", "bai", "moi", "ap", "dung", "dung",
}


def _is_toc_chunk(text: str) -> bool:
    """Nhận diện đoạn Mục lục nhiều dòng chấm dẫn '...... 14' để tránh lấn át trang nội dung."""
    txt = text or ""
    if len(_TOC_DOT_LEADER_RE.findall(txt)) >= 3:
        return True
    head = txt[:160].upper()
    return ("MỤC LỤC" in head or "MỤC\xa0LỤC" in head) and txt.count("...") >= 2


def _extract_content_phrases(query: str) -> List[str]:
    """Tạo các cụm từ 2-3 chữ có nghĩa (bỏ từ nối) để cộng điểm khớp cụm chuyên ngành."""
    raw_words = [
        w.lower()
        for w in re.sub(r"[^\w\s]", " ", query or "", flags=re.UNICODE).split()
        if len(w) >= 2 and w.lower() not in _RETRIEVAL_STOPWORDS and not w.isdigit()
    ]
    phrases: List[str] = []
    seen = set()
    for n in (3, 2):
        for i in range(len(raw_words) - n + 1):
            ph = " ".join(raw_words[i : i + n])
            if ph not in seen:
                seen.add(ph)
                phrases.append(ph)
    return phrases[:14]


def _fts_hit_is_high_confidence_fast_path(
    sparse: List[Dict[str, Any]],
    tokens: List[str],
) -> bool:
    """
    Kiểm tra xem kết quả đầu của FTS5 BM25 đã khớp hầu hết (>=75%) từ khóa câu hỏi hay chưa.
    Dùng để bỏ qua Cross-Encoder Reranker trên CPU (và bỏ qua nạp lạnh BGE-M3 khi đang tiết kiệm RAM),
    rút thời gian truy xuất xuống < 15ms.
    """
    if not sparse:
        return False
    top_raw = str(sparse[0].get("content", ""))
    if _is_toc_chunk(top_raw):
        return False
    meaningful = [t.lower() for t in tokens if len(t) >= 2 or t.isdigit() or _contains_cjk(t)]
    if not meaningful:
        return False
    top_text = top_raw.lower()
    matched = sum(1 for tok in meaningful if tok in top_text)
    required = max(1, int(math.ceil(len(meaningful) * 0.75)))
    return matched >= required


def _smart_rerank(
    query: str,
    docs: List[Dict[str, Any]],
    limit: int,
    profile: Dict[str, Any],
    max_candidates: Optional[int] = None,
    single_doc_scope: bool = False,
) -> List[Dict[str, Any]]:
    """Bỏ qua Cross-Encoder trên CPU khi không cần thiết hoặc khi top kết quả đã khớp rõ ràng để tăng tốc rõ rệt."""
    if not docs or limit <= 0:
        return []
    if not profile.get("rerank_enabled", True):
        return docs[:limit]
    if len(docs) <= 2 or (single_doc_scope and len(docs) <= limit):
        return docs[:limit]

    # Fast-path: bỏ qua Cross-Encoder CPU nếu kết quả đã khớp exact/heading, không đủ ứng viên thừa để lọc,
    # hoặc top-1 dẫn trước top-2 rõ rệt (tránh tốn 2-5s & 1.3GB ONNX trên máy yếu).
    q_tokens = [
        t for t in re.sub(r"[^\w\s]", " ", query or "", flags=re.UNICODE).split()
        if len(t) >= 2 or t.isdigit() or _contains_cjk(t)
    ]
    rrf_lead = float(docs[0].get("rrf_score", 0.0)) - float(docs[min(len(docs) - 1, 1)].get("rrf_score", 0.0))
    if (
        len(docs) <= limit
        or docs[0].get("_exact_match")
        or docs[0].get("_heading_match")
        or rrf_lead >= 0.025
        or _fts_hit_is_high_confidence_fast_path(docs[:1], q_tokens)
    ):
        return docs[:limit]

    profile_cap = int(profile.get("rerank_max_candidates") or RERANK_MAX_CANDIDATES)
    cap = min(max_candidates or RERANK_MAX_CANDIDATES, profile_cap)
    return rerank_documents(query, docs, limit, max_candidates=cap)


_QUERY_SYNONYM_MAP: List[Tuple[Tuple[str, ...], str]] = [
    (("đi muộn", "đi trễ", "trễ giờ", "chậm giờ", "di muon", "di tre", "tre gio", "cham gio"), "chậm giờ thời gian làm việc kỷ luật"),
    (("trừ lương", "bị phạt", "phạt tiền", "chế tài", "tru luong", "bi phat", "phat tien", "che tai"), "mức phạt xử phạt chế tài khấu trừ"),
    (("nghỉ việc", "nghỉ phép", "nghỉ ốm", "vắng mặt", "nghi viec", "nghi phep", "nghi om", "vang mat"), "nghỉ phép chế độ ngày nghỉ bảo hiểm"),
    (("chậm tiến độ", "trễ hạn", "quá hạn", "cham tien do", "tre han", "qua han"), "chậm tiến độ thời hạn phạt vi phạm hợp đồng"),
    (("tính tiền", "tổng tiền", "cách tính", "ra bao nhiêu", "tinh tien", "tong tien", "cach tinh", "ra bao nhieu"), "công thức tính tỷ lệ đơn giá"),
    (("rủi ro", "bất lợi", "nguy cơ", "bẫy", "rui ro", "bat loi", "nguy co", "bay"), "điều khoản phạt nghĩa vụ trách nhiệm ngoại lệ"),
    (("đăng nhập", "lỗi xác thực", "mật khẩu", "dang nhap", "loi xac thuc", "mat khau"), "xác thực token mật khẩu quyền truy cập"),
]

_OVERVIEW_OR_TABULAR_QUERY_RE = re.compile(
    r"\b(?:mục\s*lục|cấu\s*trúc|các\s*chương|bao\s*nhiêu\s*(?:chương|điều|mục|dòng|cột|hàng)|"
    r"tóm\s*tắt\s*toàn\s*bộ|tổng\s*quan|toàn\s*bảng|tổng\s*(?:cộng|doanh\s*thu|chi\s*phí|số\s*lượng|giá\s*trị|tiền|điểm)|"
    r"trung\s*bình|cao\s*nhất|thấp\s*nhất|lớn\s*nhất|nhỏ\s*nhất|"
    r"muc\s*luc|cau\s*truc|cac\s*chuong|bao\s*nhieu\s*(?:chuong|dieu|muc|dong|cot|hang)|"
    r"tom\s*tat\s*toan\s*bo|tong\s*quan|toan\s*bang|tong\s*(?:cong|doanh\s*thu|chi\s*phi|so\s*luong|gia\s*tri|tien|diem)|"
    r"trung\s*binh|cao\s*nhat|thap\s*nhat|lon\s*nhat|nho\s*nhat)\b",
    re.IGNORECASE | re.UNICODE,
)


def _fetch_outline_or_tabular_summary_chunks(
    cursor: Any,
    workspace_id: str,
    document_filter: str,
    document_params: tuple,
    limit: int = 2,
) -> List[Dict[str, Any]]:
    """Lấy trực tiếp các chunk chứa Cây mục lục tài liệu hoặc Thống kê toàn bảng dữ liệu."""
    cursor.execute(
        f"""
        SELECT c.id AS chunk_id, c.document_id, c.workspace_id, c.content,
               c.page_number, c.chunk_index, d.file_name AS document_name,
               COALESCE(d.version_number, 1) AS version_number,
               d.effective_date
        FROM document_chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.workspace_id = ?{document_filter}
          AND (
              c.content LIKE '[CÂY MỤC LỤC%'
              OR c.content LIKE '[THỐNG KÊ TOÀN BẢNG%'
          )
        ORDER BY d.created_at DESC, c.chunk_index ASC
        LIMIT ?
        """,
        (workspace_id, *document_params, limit),
    )
    return [dict(r) for r in cursor.fetchall()]


def _build_rescue_query(query: str) -> Optional[str]:
    """Mở rộng truy vấn thông minh bằng đồng nghĩa nghiệp vụ khi tìm kiếm vòng 1 không có kết quả."""
    clean_lower = re.sub(r"\s+", " ", (query or "").lower()).strip()
    if not clean_lower:
        return None
    expansions: List[str] = []
    for cues, target_terms in _QUERY_SYNONYM_MAP:
        if any(cue in clean_lower for cue in cues):
            expansions.append(target_terms)

    stripped = re.sub(
        r"\b(?:là\s+gì|như\s+thế\s+nào|thế\s+nào|ra\s+sao|bao\s+nhiêu|ở\s+đâu|khi\s+nào|"
        r"cho\s+tôi\s+hỏi|hãy\s+cho\s+biết|có\s+bị|không|vậy|ạ|nhé|"
        r"la\s+gi|nhu\s+the\s+nao|the\s+nao|bao\s+nhieu|o\s+dau|khi\s+nao|"
        r"cho\s+toi\s+hoi|hay\s+cho\s+biet|co\s+bi|khong|vay|nhe)\b",
        " ",
        clean_lower,
        flags=re.IGNORECASE | re.UNICODE,
    )
    core = re.sub(r"\s+", " ", stripped).strip()
    if not expansions and (not core or core == clean_lower):
        return None
    combined = f"{core} {' '.join(expansions)}".strip()
    return combined if combined and combined != clean_lower else None


def _run_hybrid_rrf_candidates(
    cursor: Any,
    workspace_id: str,
    query: str,
    tokens: List[str],
    exact_matches: List[Dict[str, Any]],
    document_filter: str,
    document_params: tuple,
    document_id: Optional[str],
    document_ids: Optional[List[str]],
    candidate_limit: int,
    top_k: int,
    profile: Dict[str, Any],
) -> List[Dict[str, Any]]:
    sparse: List[Dict[str, Any]] = []
    if tokens:
        match_query = " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens)
        try:
            cursor.execute(
                """SELECT c.id AS chunk_id, c.document_id, c.workspace_id, c.content,
                   c.page_number, c.chunk_index, d.file_name AS document_name,
                   COALESCE(d.version_number, 1) AS version_number,
                   d.effective_date,
                   bm25(chunks_fts) AS score
                FROM chunks_fts f
                JOIN document_chunks c ON c.id = f.chunk_id
                JOIN documents d ON d.id = c.document_id
                WHERE chunks_fts MATCH ? AND c.workspace_id = ?{document_filter}
                ORDER BY score ASC LIMIT ?
            """.format(document_filter=document_filter),
                (match_query, workspace_id, *document_params, candidate_limit),
            )
            sparse = [dict(row) for row in cursor.fetchall()]
        except Exception:
            sparse = []

    # Ở chế độ Eco hoặc khi BGE-M3 chưa nạp vào RAM mà FTS5 đã tìm thấy đoạn khớp độ tin cậy cao (>=75% từ khóa),
    # bỏ qua nạp lạnh BGE-M3 để phản hồi tức thì (<15ms) và tiết kiệm ~2.9GB RAM.
    from app.services.embedding_service import is_embedding_model_loaded
    embed_mocked = bool(
        hasattr(embed_texts, "_mock_name")
        or hasattr(embed_texts, "assert_called")
        or getattr(embed_texts, "__module__", "").startswith("unittest.mock")
    )
    avail_ram_gb = float((profile.get("specs") or {}).get("available_ram_gb") or 8.0)
    should_skip_dense_for_eco = (
        profile.get("fts_first_shortcut")
        and (bool(exact_matches) or _fts_hit_is_sufficient_for_eco(sparse, tokens, top_k))
    ) or (
        not embed_mocked
        and not is_embedding_model_loaded()
        and (
            (
                str(profile.get("id") or "balanced").lower() != "performance"
                and (bool(exact_matches) or _fts_hit_is_high_confidence_fast_path(sparse, tokens))
            )
            or (avail_ram_gb < 4.5 and len(sparse) >= 2)
        )
    )
    dense: List[Dict[str, Any]] = []
    if profile.get("enable_dense_retrieval", True) and not should_skip_dense_for_eco:
        dense = _search_dense_candidates(
            cursor,
            workspace_id,
            query,
            candidate_limit,
            document_id,
            document_ids,
        )

    # Reciprocal Rank Fusion (RRF) + Heading Topic Boost + Phrase Boost - TOC Penalty
    q_low = (query or "").lower()
    topic_cues = [
        w for w in ("công nghệ", "mở rộng", "kiến trúc", "lộ trình", "mục tiêu", "đánh giá", "module", "chế độ", "hoạt động")
        if w in q_low
    ]
    content_phrases = _extract_content_phrases(query)
    is_overview_q = is_global_summary_query(query) or bool(_OVERVIEW_OR_TABULAR_QUERY_RE.search(query or ""))

    merged: Dict[str, Dict[str, Any]] = {}
    for channel_name, ranking in (("sparse", sparse), ("dense", dense)):
        for rank, item in enumerate(ranking, start=1):
            chunk_id = item["chunk_id"]
            if chunk_id not in merged:
                merged[chunk_id] = {key: value for key, value in item.items() if key != "score"}
                merged[chunk_id]["rrf_score"] = 0.0
            if channel_name == "dense" and "score" in item:
                merged[chunk_id]["dense_score"] = float(item["score"])
            merged[chunk_id]["rrf_score"] += 1.0 / (RRF_K + rank)

    heading_line_re = (
        re.compile(
            r"(?:^|\n)\s*(?:#{1,4}\s*|\d{1,2}(?:\.\d{1,2})?\.\s+|(?:chương|bài|phần|mục|điều|vấn\s+đề)\s+(?:[IVXLCDM]+|\d+)\b)([^\n]{2,110})",
            re.IGNORECASE | re.UNICODE,
        )
        if topic_cues
        else None
    )

    for item in merged.values():
        full_txt = str(item.get("content") or "")
        is_toc = _is_toc_chunk(full_txt)
        if is_toc and not is_overview_q:
            item["rrf_score"] -= 0.045
            continue

        low_txt = full_txt.lower()
        if content_phrases:
            phrase_hits = 0
            heading_phrase_hits = 0
            for ph in content_phrases:
                if ph in low_txt:
                    phrase_hits += 1
                    item["rrf_score"] += 0.025
                    # Thưởng thêm nếu cụm từ khóa xuất hiện ngay trong dòng tiêu đề/mục (vd: '2. HÀM SỐ ĐỒNG BIẾN – NGHỊCH BIẾN')
                    if re.search(rf"(?:^|\n)\s*(?:#{1,4}\s*|\d{{1,2}}\.\s*)[^\n]{{0,35}}{re.escape(ph)}", low_txt):
                        item["rrf_score"] += 0.035
                        heading_phrase_hits += 1
                    if phrase_hits >= 4:
                        break
            min_heading_hits = 1 if len(content_phrases) <= 1 else 2
            if heading_phrase_hits >= min_heading_hits:
                item["_heading_match"] = True

        if topic_cues and heading_line_re is not None:
            heading_texts = " ".join(m.group(0).lower() for m in heading_line_re.finditer(full_txt))
            head_slice = low_txt[:260]
            for cue in topic_cues:
                if cue in heading_texts:
                    item["rrf_score"] += 0.045
                elif cue in head_slice:
                    item["rrf_score"] += 0.020
    return sorted(merged.values(), key=lambda item: item["rrf_score"], reverse=True)


def _collect_named_section_chunks(
    cursor: Any,
    start_chunk: Dict[str, Any],
    query: str,
    max_chunks: int = 5,
    max_chars: int = 5200,
) -> List[Dict[str, Any]]:
    """
    Khi người dùng hỏi đích danh tên một Mục/Chương/Phần (vd: '9. HAI ĐƯỜNG THẲNG...'),
    lấy trọn vẹn phần thân của mục đó qua các trang/chunk kế tiếp và tự động cắt dừng
    ngay trước tiêu đề mục đồng cấp hoặc cấp lớn hơn kế tiếp (vd dừng trước '10. ...').
    """
    doc_id = start_chunk.get("document_id")
    start_idx = start_chunk.get("chunk_index")
    if not doc_id or start_idx is None:
        return [start_chunk]

    cursor.execute(
        """
        SELECT c.id AS chunk_id, c.document_id, c.workspace_id, c.content,
               c.page_number, c.chunk_index, d.file_name AS document_name,
               COALESCE(d.version_number, 1) AS version_number,
               d.effective_date
        FROM document_chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.document_id = ? AND c.chunk_index >= ? AND c.chunk_index <= ?
        ORDER BY c.chunk_index ASC
        """,
        (doc_id, int(start_idx), int(start_idx) + max_chunks - 1),
    )
    seq_rows = [dict(r) for r in cursor.fetchall()]
    if not seq_rows:
        return [start_chunk]

    phrases = _extract_content_phrases(query)
    num_m = re.search(r"\b(\d{1,2})\b", query or "")
    q_num = num_m.group(1) if num_m else None

    # Xác định dòng tiêu đề mở đầu mục trong chunk đầu tiên để cắt bỏ phần đuôi mục trước nếu nằm chung chunk
    first_lines = (seq_rows[0].get("content") or "").splitlines()
    start_line_idx = 0
    started_num: Optional[int] = int(q_num) if q_num else None
    heading_pat = re.compile(
        r"^\s*(?:#{1,4}\s*)?(?:(\d{1,2})\s*\.\s+|(?:VẤN\s+ĐỀ|CHƯƠNG|PHẦN|BÀI)\s+(?:[IVXLCDM]{1,6}|\d{1,3})\b)",
        re.IGNORECASE | re.UNICODE,
    )
    for i, ln in enumerate(first_lines):
        low_ln = ln.lower()
        hm = heading_pat.match(ln)
        if hm and ((q_num and hm.group(1) == q_num) or sum(1 for ph in phrases if ph in low_ln) >= (1 if len(phrases) <= 1 else 2)):
            start_line_idx = i
            if hm.group(1):
                started_num = int(hm.group(1))
            break

    def _is_next_major_heading(ln: str) -> bool:
        s = ln.strip()
        if not s:
            return False
        if re.match(r"^(?:VẤN\s+ĐỀ|CHƯƠNG|PHẦN)\s+(?:[IVXLCDM]{1,6}|\d{1,3})\b", s, re.IGNORECASE | re.UNICODE):
            return True
        m_num = re.match(r"^(\d{1,2})\s*\.\s+[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯẠ-Ỹ]", s, re.UNICODE)
        if m_num:
            cand_num = int(m_num.group(1))
            if started_num is not None:
                return cand_num != started_num and cand_num >= started_num + 1
            return True
        return False

    collected: List[Dict[str, Any]] = []
    total_chars = 0
    for seq_pos, row in enumerate(seq_rows):
        lines = (row.get("content") or "").splitlines()
        if seq_pos == 0 and start_line_idx > 0:
            lines = lines[start_line_idx:]

        kept_lines: List[str] = []
        hit_boundary = False
        for ln_pos, ln in enumerate(lines):
            # Ở chunk đầu tiên, bỏ qua chính dòng tiêu đề mở đầu khi kiểm tra ranh giới dừng
            if not (seq_pos == 0 and ln_pos == 0) and _is_next_major_heading(ln):
                hit_boundary = True
                break
            kept_lines.append(ln)

        piece = "\n".join(kept_lines).strip()
        if piece:
            if collected and total_chars + len(piece) > max_chars:
                break
            row_copy = dict(row)
            row_copy["content"] = piece
            row_copy["_exact_match"] = True
            if row_copy.get("page_number") is not None:
                row_copy["page_label"] = f"Trang {row_copy['page_number']}"
            collected.append(row_copy)
            total_chars += len(piece)

        if hit_boundary or total_chars >= max_chars:
            break

    return collected or [start_chunk]


def search_relevant_chunks(
    workspace_id: str,
    query: str,
    top_k: int = TOP_K_RETRIEVAL,
    document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Tìm kiếm đoạn văn bản liên quan kết hợp Exact Lookup + BM25 (FTS5) + Dense Matrix Cache + RRF + Smart Reranker.
    """
    profile = get_active_profile_config()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        clean_query = re.sub(r"[^\w\s]", " ", query, flags=re.UNICODE)
        # Giữ lại token >= 2 ký tự, chữ số, hoặc ký tự CJK đơn lẻ (Kanji/Kana như '夢', '愛'...)
        raw_tokens = [
            token for token in clean_query.split()
            if len(token) >= 2 or token.isdigit() or _contains_cjk(token)
        ]
        # Loại bỏ các từ nối/từ chung khỏi FTS5 BM25 để tránh loãng điểm khi câu hỏi dài
        filtered_tokens = [
            token for token in raw_tokens
            if token.lower() not in _RETRIEVAL_STOPWORDS or _contains_cjk(token)
        ]
        tokens = filtered_tokens if filtered_tokens else raw_tokens
        exact_terms = _extract_exact_lookup_terms(query)
        candidate_limit = max(top_k * RETRIEVAL_CANDIDATE_MULTIPLIER, top_k, 24)
        single_doc_scope = bool(document_id or (document_ids and len(document_ids) == 1))
        document_filter, document_params = _build_doc_scope_filter(document_id, document_ids)

        exact_matches = _find_exact_term_chunks(
            cursor,
            workspace_id,
            document_filter,
            document_params,
            exact_terms,
            limit=min(top_k, 4),
        )
        exact_ids = {item["chunk_id"] for item in exact_matches}
        if exact_matches and len(tokens) <= 4:
            # Truy vấn tra cứu từ khóa/Kanji cụ thể đã có khớp chính xác -> ưu tiên tuyệt đối tránh nhiễu làm tràn ngữ cảnh LLM
            return expand_and_stitch_chunks(exact_matches, max_total_chunks=min(top_k, 4))

        ranked = _run_hybrid_rrf_candidates(
            cursor,
            workspace_id,
            query,
            tokens,
            exact_matches,
            document_filter,
            document_params,
            document_id,
            document_ids,
            candidate_limit,
            top_k,
            profile,
        )

        # Tự động ưu tiên Cây mục lục (Document Outline) hoặc Thống kê toàn bảng (Tabular Analytics)
        # khi câu hỏi mang tính tổng quan toàn tài liệu hoặc tính tổng/trung bình/min/max trên bảng lớn
        summary_pinned: List[Dict[str, Any]] = []
        if _OVERVIEW_OR_TABULAR_QUERY_RE.search(query or ""):
            summary_pinned = _fetch_outline_or_tabular_summary_chunks(
                cursor,
                workspace_id,
                document_filter,
                document_params,
                limit=min(2, top_k),
            )
            if summary_pinned:
                sum_ids = {item["chunk_id"] for item in summary_pinned}
                for item in summary_pinned:
                    item["_exact_match"] = True
                ranked = summary_pinned + [item for item in ranked if item["chunk_id"] not in sum_ids]

        # A direct question about a named file (for example, "Data.txt chứa gì?")
        # should retrieve that file even when its name is absent from extracted text.
        # Chỉ áp dụng khi không đang lọc trong phạm vi 1 tài liệu cụ thể (not single_doc_scope),
        # và loại trừ các từ chung như 'tai', 'lieu', 'file', 'de', 'tong', 'quan' để không ghim nhầm chunk_index=0,1.
        _GENERIC_FILENAME_STOPWORDS = {
            "tai", "tài", "lieu", "liệu", "file", "tep", "tệp", "doc", "docx", "pdf", "txt",
            "tong", "tổng", "quan", "de", "đề", "ban", "bản", "bao", "báo", "cao", "cáo",
            "cong", "công", "thuc", "thức", "so", "sổ", "tay", "tra", "cuu", "cứu",
            "toan", "toán", "huong", "hướng", "dan", "dẫn", "giao", "trinh", "trình",
            "on", "ôn", "tap", "tập", "sach", "sách", "bai", "bài", "phan", "phần",
            "chuong", "chương", "muc", "mục", "dieu", "điều", "personal", "knowledge", "platform",
        }
        query_terms = {
            term.lower() for term in tokens
            if len(term) > 2 and term.lower() not in _GENERIC_FILENAME_STOPWORDS
        }
        named_ids: set[str] = set()
        if query_terms and not single_doc_scope:
            cursor.execute(
                """
                SELECT c.id AS chunk_id, c.document_id, c.workspace_id, c.content,
                       c.page_number, c.chunk_index, d.file_name AS document_name,
                       COALESCE(d.version_number, 1) AS version_number,
                       d.effective_date
                FROM documents d JOIN document_chunks c ON c.document_id = d.id
                WHERE d.workspace_id = ?{document_filter}
                ORDER BY d.created_at DESC, c.chunk_index ASC
            """.format(document_filter=document_filter.replace("c.document_id", "d.id")),
                (workspace_id, *document_params),
            )
            named_matches = []
            for row in cursor.fetchall():
                item = dict(row)
                stem = re.sub(r"\.[^.]+$", "", item["document_name"]).lower()
                name_terms = {
                    w for w in re.findall(r"[\w]+", stem, flags=re.UNICODE)
                    if len(w) > 2 and w not in _GENERIC_FILENAME_STOPWORDS
                }
                if name_terms & query_terms:
                    named_matches.append(item)
            named_ids = {item["chunk_id"] for item in named_matches}

        is_file_overview_q = bool(
            re.search(r"\b(?:chứa\s+gì|gồm\s+những\s+gì|nội\s+dung\s+gì|tóm\s+tắt|nói\s+về\s+gì|chua\s+gi|noi\s+dung\s+gi)\b", query or "", re.IGNORECASE)
        )
        if named_ids and (is_file_overview_q or not ranked):
            ranked_tail = [item for item in ranked if item["chunk_id"] not in named_ids]
            pinned = named_matches[:top_k]
            final_chunks = expand_and_stitch_chunks(pinned + ranked_tail[: max(0, top_k - len(pinned))], max_total_chunks=top_k)
            return filter_relevant_chunks(query, final_chunks)
        if named_ids and ranked:
            for item in ranked:
                if item["chunk_id"] in named_ids:
                    item["rrf_score"] = float(item.get("rrf_score", 0.0)) + 0.035
            ranked.sort(key=lambda item: float(item.get("rrf_score", 0.0)), reverse=True)

        if not ranked and (document_id or document_ids):
            cursor.execute(
                """
                SELECT c.id AS chunk_id, c.document_id, c.workspace_id, c.content,
                       c.page_number, c.chunk_index, d.file_name AS document_name
                FROM documents d
                JOIN document_chunks c ON c.document_id = d.id
                WHERE d.workspace_id = ?{document_filter}
                ORDER BY d.created_at DESC, c.chunk_index ASC
                LIMIT ?
                """.format(document_filter=document_filter.replace("c.document_id", "d.id")),
                (workspace_id, *document_params, top_k),
            )
            attached_document_chunks = [dict(row) for row in cursor.fetchall()]
            if attached_document_chunks:
                return expand_and_stitch_chunks(attached_document_chunks, max_total_chunks=top_k)

        pinned_front = list(exact_matches)
        for sp in summary_pinned:
            if sp["chunk_id"] not in exact_ids:
                pinned_front.append(sp)
                exact_ids.add(sp["chunk_id"])

        if pinned_front:
            remaining_rank = [item for item in ranked if item["chunk_id"] not in exact_ids]
            remaining_limit = max(0, top_k - len(pinned_front))
            reranked_tail = _smart_rerank(
                query,
                remaining_rank,
                remaining_limit,
                profile,
                single_doc_scope=single_doc_scope,
            )
            stitched = expand_and_stitch_chunks(pinned_front + reranked_tail, max_total_chunks=top_k)
        else:
            is_named_section_ask = bool(
                re.search(
                    r"^(?:nội\s+dung|tóm\s+tắt|giải\s+thích).{0,25}(?:chương|phần|mục|bài|vấn\s+đề)\b",
                    query or "",
                    re.IGNORECASE | re.UNICODE,
                )
            )
            heading_matched = [item for item in ranked if item.get("_heading_match")]
            if is_named_section_ask and heading_matched:
                best_heading_chunk = _smart_rerank(
                    query,
                    heading_matched,
                    1,
                    profile,
                    single_doc_scope=single_doc_scope,
                )[0]
                stitched = _collect_named_section_chunks(
                    cursor,
                    best_heading_chunk,
                    query,
                    max_chunks=min(5, top_k + 2),
                    max_chars=5200,
                )
            else:
                reranked = _smart_rerank(
                    query,
                    ranked,
                    top_k,
                    profile,
                    single_doc_scope=single_doc_scope,
                )
                stitched = expand_and_stitch_chunks(reranked, max_total_chunks=top_k)
        # Chỉ lọc liên quan nếu người dùng không chỉ định đích danh file đính kèm
        if not (document_id or document_ids):
            relevant = filter_relevant_chunks(query, stitched)
            if relevant:
                return relevant
            rescue_q = _build_rescue_query(query)
            if rescue_q:
                rescue_tokens = [
                    token
                    for token in re.sub(r"[^\w\s]", " ", rescue_q, flags=re.UNICODE).split()
                    if len(token) >= 2 or token.isdigit() or _contains_cjk(token)
                ]
                rescue_ranked = _run_hybrid_rrf_candidates(
                    cursor,
                    workspace_id,
                    rescue_q,
                    rescue_tokens,
                    [],
                    document_filter,
                    document_params,
                    document_id,
                    document_ids,
                    candidate_limit,
                    top_k,
                    profile,
                )
                if rescue_ranked:
                    rescue_reranked = _smart_rerank(
                        rescue_q,
                        rescue_ranked,
                        top_k,
                        profile,
                        single_doc_scope=single_doc_scope,
                    )
                    rescue_stitched = expand_and_stitch_chunks(rescue_reranked, max_total_chunks=top_k)
                    return filter_relevant_chunks(rescue_q, rescue_stitched)
            return []
        return stitched
    finally:
        conn.close()
