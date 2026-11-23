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

# Từ khóa nhận biết câu hỏi muốn TÓM TẮT TOÀN BỘ tài liệu
_GLOBAL_SUMMARY_KEYWORDS = [
    "tóm tắt", "tóm lại", "tổng hợp", "liệt kê tất cả", "liệt kê các",
    "các bài", "các chương", "các phần", "nội dung chính", "toàn bộ",
    "overview", "summarize", "summary", "list all", "all chapters",
    "all sections", "main topics", "những bài", "những chương",
    "nêu các", "kể tên", "có những gì", "gồm những gì",
]

# Regex nhận diện "bài X", "chương X", "phần X", "lab X", "bài tập X", "bài số X"
_SECTION_PATTERN = re.compile(
    r"\b(?:(bài|chương|phần|lab|exercise|chapter|section|bai|chuong|phan)(?:\s+tập|\s+số|\s+tap|\s+so)?)\s*(\d+)\b",
    re.IGNORECASE | re.UNICODE,
)

# Từ khóa thể hiện ý định hỏi về các bước hoặc câu hỏi nối tiếp về bài đang làm
_FOLLOW_UP_KEYWORDS = [
    "bước tiếp", "bước iếp", "tiếp theo", "tiếp tục", "các bước",
    "từng bước", "hướng dẫn", "cách làm", "làm thế nào", "còn gì nữa",
    "chi tiết hơn", "bước mấy",
]


_CJK_CHAR_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_CJK_SEQ_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
_QUOTED_TERM_RE = re.compile(r'["\'“”‘’「」『』]([^"\'“”‘’「」『」]{1,40})["\'“”‘’「」『』]')

_START_POS_PATTERN = re.compile(
    r"(?:\b(?:trang|phần|mục|đoạn|dòng|câu|từ(?:\s+vựng)?)\s+đầu(?:\s+tiên)?\b|"
    r"\bđầu\s+tiên\s+(?:trong|của|ở)\s+(?:file|tệp|tài\s+liệu|văn\s+bản|danh\s+sách)\b|"
    r"\b(?:mở\s+đầu|từ\s+đầu)\s+(?:file|tệp|tài\s+liệu)\b|"
    r"\bbắt\s+đầu\s+(?:bằng|với)\s+chữ\b|"
    r"\b\d+\s+(?:từ(?:\s+vựng)?|mục|câu|dòng)\s+đầu(?:\s+tiên)?\b)",
    re.IGNORECASE | re.UNICODE,
)
_END_POS_PATTERN = re.compile(
    r"(?:\b(?:trang|phần|mục|đoạn|dòng|câu|từ(?:\s+vựng)?)\s+cuối(?:\s+cùng)?\b|"
    r"\bcuối\s+cùng\s+(?:trong|của|ở)\s+(?:file|tệp|tài\s+liệu|văn\s+bản|danh\s+sách)\b|"
    r"\b\d+\s+(?:từ(?:\s+vựng)?|mục|câu|dòng)\s+cuối(?:\s+cùng)?\b)",
    re.IGNORECASE | re.UNICODE,
)
_LETTER_FILTER_PATTERN = re.compile(
    r"(?:bắt\s+đầu\s+(?:bằng|với)\s+(?:chữ(?:\s+cái)?\s+)?|chữ\s+cái\s+)[\"']?([a-zA-Z])[\"']?(?:\b|$)",
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
    q = query.lower().strip()
    # Nếu có chỉ định rõ bài cụ thể (ví dụ: "tóm tắt bài 1") thì ưu tiên Section Extraction
    if _SECTION_PATTERN.search(q):
        return False
    return any(kw in q for kw in _GLOBAL_SUMMARY_KEYWORDS)


def detect_section_intent(
    query: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> Optional[Tuple[str, int]]:
    """
    Phát hiện xem người dùng đang hỏi về Bài/Chương/Lab mấy.
    Hỗ trợ phát hiện trong câu hỏi hiện tại hoặc suy luận từ ngữ cảnh hội thoại trước đó.
    """
    q = query.lower().strip()
    m = _SECTION_PATTERN.search(q)
    if m:
        sec_raw = m.group(1).lower()
        sec_norm = (
            "bài" if sec_raw in ("bài", "bai")
            else "chương" if sec_raw in ("chương", "chuong")
            else "phần" if sec_raw in ("phần", "phan")
            else sec_raw
        )
        return sec_norm, int(m.group(2))

    # Nếu câu hỏi hiện tại là câu nối tiếp (ví dụ: "các bước tiếp theo đâu", "bước iếp theo")
    is_follow_up = any(kw in q for kw in _FOLLOW_UP_KEYWORDS) or len(q.split()) <= 5
    if is_follow_up and history:
        for turn in reversed(history[-8:]):
            if turn.get("role") == "user":
                prev_text = turn.get("content", "").lower()
                pm = _SECTION_PATTERN.search(prev_text)
                if pm:
                    psec_raw = pm.group(1).lower()
                    psec_norm = (
                        "bài" if psec_raw in ("bài", "bai")
                        else "chương" if psec_raw in ("chương", "chuong")
                        else "phần" if psec_raw in ("phần", "phan")
                        else psec_raw
                    )
                    return psec_norm, int(pm.group(2))

    return None


def search_section_chunks(
    workspace_id: str,
    sec_type: str,
    sec_num: int,
    max_chunks: int = 16,
    document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Trích xuất toàn bộ các chunk liên tục thuộc về Bài X / Chương X trong tài liệu.
    Bắt đầu từ chunk chứa tiêu đề Bài X (bỏ qua trang Mục lục) cho đến khi gặp Bài X+1
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

        pat_start = re.compile(rf"\b{sec_type}\s*{sec_num}\b", re.IGNORECASE)
        pat_next = re.compile(rf"\b{sec_type}\s*{sec_num + 1}\b", re.IGNORECASE)

        start_idx = None
        end_idx = None

        for i, c in enumerate(all_chunks):
            content_lower = c["content"].lower()
            # Bỏ qua các trang Mục lục đầu tài liệu
            is_toc = ("mục lục" in content_lower or "table of contents" in content_lower or "........" in c["content"]) and c["page_number"] <= 3
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
    Mở rộng và ghép nối có điều kiện các chunk liền kề (adjacent chunks) của cùng một tài liệu.
    Chỉ ghép khi chunk hiện tại chưa kết thúc câu hoặc đang liệt kê các bước/danh sách;
    kiểm soát ngân sách ký tự để mô hình cục bộ xử lý cực nhanh trên GPU/CPU máy yếu.
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
                needed_keys.add((doc_id, c_idx + 1))

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

            # Ghép với chunk liền sau nếu có lý do liên tục
            next_c = doc_chunk_map.get(doc_id, {}).get(c_idx + 1)
            should_stitch = False
            content_stripped = merged_content.strip()

            is_tabular_chunk = content_stripped.count("|") >= 4
            if next_c and (accumulated_chars + len(merged_content) + len(next_c.get("content", ""))) <= max_total_chars:
                # 1. Đang liệt kê bước thực hành (Bước, Step, Bài)
                if re.search(r'\b(?:bước|step|bài)\s*\d+', content_stripped, re.IGNORECASE):
                    should_stitch = True
                # 2. Chunk tiếp theo bắt đầu bằng bước hoặc số thứ tự tiếp nối
                elif next_c.get("content", "").strip().startswith(("Bước", "Step", "1.", "2.", "3.", "4.", "5.")):
                    should_stitch = True
                # 3. Đoạn văn kết thúc lửng lơ (chưa hết câu), không áp dụng cho bảng/từ vựng phân cách bằng '|'
                elif not is_tabular_chunk and content_stripped and not content_stripped.endswith((".", "!", "?", "...", ":")):
                    should_stitch = True

            if should_stitch and next_c:
                visited.add((doc_id, c_idx + 1))
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
        with _VECTOR_CACHE_LOCK:
            _VECTOR_CACHE[db_key] = empty_index
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
    with _VECTOR_CACHE_LOCK:
        _VECTOR_CACHE[db_key] = built
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


def _smart_rerank(
    query: str,
    docs: List[Dict[str, Any]],
    limit: int,
    profile: Dict[str, Any],
    max_candidates: Optional[int] = None,
    single_doc_scope: bool = False,
) -> List[Dict[str, Any]]:
    """Bỏ qua Cross-Encoder trên CPU khi không cần thiết để tăng tốc rõ rệt."""
    if not docs or limit <= 0:
        return []
    if not profile.get("rerank_enabled", True):
        return docs[:limit]
    if len(docs) <= 2 or (single_doc_scope and len(docs) <= limit):
        return docs[:limit]

    profile_cap = int(profile.get("rerank_max_candidates") or RERANK_MAX_CANDIDATES)
    cap = min(max_candidates or RERANK_MAX_CANDIDATES, profile_cap)
    return rerank_documents(query, docs, limit, max_candidates=cap)


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
        tokens = [
            token for token in clean_query.split()
            if len(token) >= 2 or token.isdigit() or _contains_cjk(token)
        ]
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

        # Ở chế độ Eco (máy yếu): ưu tiên FTS5 BM25 tức thì, chỉ nạp Dense khi FTS5 chưa đủ khớp tin cậy
        should_skip_dense_for_eco = (
            profile.get("fts_first_shortcut")
            and (bool(exact_matches) or _fts_hit_is_sufficient_for_eco(sparse, tokens, top_k))
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

        # Reciprocal Rank Fusion (RRF)
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
        ranked = sorted(merged.values(), key=lambda item: item["rrf_score"], reverse=True)

        # A direct question about a named file (for example, "Data.txt chứa gì?")
        # should retrieve that file even when its name is absent from extracted text.
        query_terms = {term.lower() for term in tokens if len(term) > 2}
        named_ids: set[str] = set()
        if query_terms:
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
                name_terms = set(re.findall(r"[\w]+", stem, flags=re.UNICODE))
                if name_terms & query_terms:
                    named_matches.append(item)
            named_ids = {item["chunk_id"] for item in named_matches}
            ranked = named_matches + [item for item in ranked if item["chunk_id"] not in named_ids]

        if named_ids:
            pinned = [item for item in ranked if item["chunk_id"] in named_ids][:top_k]
            pinned = _smart_rerank(
                query,
                pinned,
                len(pinned),
                profile,
                max_candidates=len(pinned),
                single_doc_scope=single_doc_scope,
            )
            remaining = [item for item in ranked if item["chunk_id"] not in named_ids]
            if len(pinned) < top_k:
                remaining = _smart_rerank(
                    query,
                    remaining,
                    top_k - len(pinned),
                    profile,
                    single_doc_scope=single_doc_scope,
                )
            else:
                remaining = []
            final_chunks = expand_and_stitch_chunks(pinned + remaining, max_total_chunks=top_k)
            return filter_relevant_chunks(query, final_chunks)

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

        if exact_matches:
            remaining_rank = [item for item in ranked if item["chunk_id"] not in exact_ids]
            remaining_limit = max(0, top_k - len(exact_matches))
            reranked_tail = _smart_rerank(
                query,
                remaining_rank,
                remaining_limit,
                profile,
                single_doc_scope=single_doc_scope,
            )
            stitched = expand_and_stitch_chunks(exact_matches + reranked_tail, max_total_chunks=top_k)
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
            return filter_relevant_chunks(query, stitched)
        return stitched
    finally:
        conn.close()
