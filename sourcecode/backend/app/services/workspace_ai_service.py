"""AI services for Workspace metadata auto-generation and multi-level semantic search."""
import logging
import math
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore

from app.config import DEFAULT_LLM_MODEL, EMBEDDING_MODEL
from app.database import get_db_connection
from app.services.embedding_service import embed_texts, pack_vector, unpack_vector
from app.services.llm_service import call_ollama_json

logger = logging.getLogger(__name__)

ALLOWED_WORKSPACE_CATEGORIES = (
    "Kỹ thuật",
    "Nghiên cứu",
    "Ngoại ngữ",
    "Đại học",
    "Dự án",
    "Chung",
)

DEFAULT_WORKSPACE_BASE_NAME = "Workspace mới"
_DEFAULT_NAME_PATTERN = re.compile(r"^workspace\s+mới(?:\s+\d+|\s*\(\d+\))?$", re.IGNORECASE)

_VI_ACCENTED_STOPWORDS = {
    "và", "của", "cho", "với", "về", "trong", "là", "các", "những", "này", "đó",
    "khi", "nào", "sao", "để", "trên", "dưới", "từ", "hay", "hoặc", "một", "hai",
    "ba", "không", "gì", "ở", "đâu", "như", "thế", "có", "được", "tài", "liệu",
    "bài", "phần", "mục", "file", "tệp", "nội", "dung", "thông", "tin",
    "and", "for", "with", "of", "in", "on", "to", "the", "a", "an",
}

_VI_UNACCENTED_STOPWORDS = {
    "va", "cua", "cho", "voi", "ve", "trong", "la", "cac", "nhung", "nay", "do",
    "khi", "nao", "sao", "tren", "duoi", "tu", "hay", "hoac", "mot", "hai", "ba",
    "khong", "gi", "o", "dau", "nhu", "the", "co", "duoc", "tai", "lieu", "bai",
    "phan", "muc", "file", "tep", "noi", "dung", "thong", "tin",
    "and", "for", "with", "of", "in", "on", "to", "the", "a", "an",
}


def _has_accent(text: str) -> bool:
    return any(ord(ch) > 127 for ch in text)


def _normalize_vi(text: str) -> str:
    """Chuẩn hóa tách CamelCase, chữ thường và bỏ dấu tiếng Việt để so khớp từ khóa chính xác."""
    if not text:
        return ""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    s = spaced.replace("đ", "d").replace("Đ", "D").lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def _extract_query_tokens(query: str) -> Tuple[str, List[str], List[str]]:
    """Tách token chuẩn hóa (bỏ stopword theo ngữ cảnh dấu tiếng Việt) và token thô cho FTS5."""
    q_norm = _normalize_vi(query)
    raw_all = [
        t
        for t in re.sub(r"[^\w\s]", " ", query, flags=re.UNICODE).split()
        if len(t) >= 2 or t.isdigit()
    ]
    query_accented = _has_accent(query)

    filtered_raw: List[str] = []
    for t in raw_all:
        t_low = t.lower()
        t_norm = _normalize_vi(t_low)
        is_stop = (
            t_low in _VI_ACCENTED_STOPWORDS
            if query_accented
            else (t_norm in _VI_UNACCENTED_STOPWORDS)
        )
        if not is_stop:
            filtered_raw.append(t)

    raw_tokens = filtered_raw or raw_all
    q_tokens = [_normalize_vi(t) for t in raw_tokens if _normalize_vi(t)]
    if not q_tokens:
        q_tokens = [t for t in q_norm.split() if len(t) >= 2 or t.isdigit()]
    return q_norm, q_tokens, raw_tokens


def _is_default_workspace_name(name: str) -> bool:
    return bool(_DEFAULT_NAME_PATTERN.match((name or "").strip()))


def generate_unique_default_workspace_name(conn: Any, owner_user_id: Optional[str]) -> str:
    """Sinh tên tạm duy nhất cho workspace mới tạo nhanh không nhập tên."""
    if owner_user_id:
        rows = conn.execute(
            "SELECT name FROM workspaces WHERE owner_user_id = ?",
            (owner_user_id,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT name FROM workspaces").fetchall()

    existing = {str(r["name"]).strip().lower() for r in rows if r["name"]}
    if DEFAULT_WORKSPACE_BASE_NAME.lower() not in existing:
        return DEFAULT_WORKSPACE_BASE_NAME

    idx = 2
    while f"{DEFAULT_WORKSPACE_BASE_NAME} {idx}".lower() in existing:
        idx += 1
    return f"{DEFAULT_WORKSPACE_BASE_NAME} {idx}"


def _deduplicate_workspace_title(
    conn: Any,
    workspace_id: str,
    owner_user_id: Optional[str],
    candidate: str,
) -> str:
    clean = re.sub(r"\s+", " ", (candidate or "").strip())[:100].strip(" -–—:;,.")
    if not clean:
        clean = DEFAULT_WORKSPACE_BASE_NAME

    if owner_user_id:
        rows = conn.execute(
            "SELECT name FROM workspaces WHERE owner_user_id = ? AND id != ?",
            (owner_user_id, workspace_id),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT name FROM workspaces WHERE id != ?",
            (workspace_id,),
        ).fetchall()

    existing = {str(r["name"]).strip().lower() for r in rows if r["name"]}
    if clean.lower() not in existing:
        return clean

    suffix = 2
    while True:
        tagged = f"{clean[:92]} ({suffix})"
        if tagged.lower() not in existing:
            return tagged
        suffix += 1


def _humanize_filename_stem(file_name: str) -> str:
    stem = re.sub(r"\.[^.]+$", "", (file_name or "").strip())
    stem = re.sub(r"[_\-]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem or "Tài liệu"


_FALLBACK_LISTING_RE = re.compile(r"^tổng hợp \d+ tài liệu\s*:", re.IGNORECASE)


def _looks_like_file_list_desc(desc: str) -> bool:
    d = (desc or "").strip()
    if not d:
        return True
    return bool(_FALLBACK_LISTING_RE.match(d))


def _build_fallback_metadata(
    doc_names: List[str],
    note_titles: List[str],
) -> Tuple[str, str, str]:
    if doc_names:
        stems = [_humanize_filename_stem(n) for n in doc_names]
        primary_stem = stems[0][:65]
        if len(doc_names) == 1:
            title = primary_stem
            description = f"Không gian lưu trữ tài liệu và hỏi đáp AI về chủ đề {primary_stem}."
        else:
            title = f"{primary_stem[:50]} (+{len(doc_names) - 1} tệp)"
            topics = ", ".join(s[:40] for s in stems[:3])
            description = f"Không gian học tập và tra cứu kiến thức liên quan đến {topics}."
        return title[:120], description[:500], "Chung"

    if note_titles:
        title = note_titles[0][:80]
        description = f"Không gian ghi chú và nghiên cứu về {note_titles[0]}."
        return title, description[:500], "Nghiên cứu"

    return DEFAULT_WORKSPACE_BASE_NAME, "", "Chung"


def _collect_workspace_context(
    conn: Any,
    workspace_id: str,
    max_docs: int = 6,
    max_chars: int = 1050,
) -> Dict[str, Any]:
    docs = conn.execute(
        """
        SELECT id, file_name, file_type, created_at
        FROM documents
        WHERE workspace_id = ?
        ORDER BY created_at DESC
        """,
        (workspace_id,),
    ).fetchall()
    doc_names = [str(r["file_name"]) for r in docs]

    notes = conn.execute(
        """
        SELECT title, content
        FROM notes
        WHERE workspace_id = ?
        ORDER BY updated_at DESC
        LIMIT 4
        """,
        (workspace_id,),
    ).fetchall()
    note_titles = [str(r["title"]) for r in notes if r["title"]]

    snippets: List[str] = []
    total_chars = 0

    if docs:
        target_docs = docs[:max_docs]
        per_doc_budget = max(140, max_chars // len(target_docs))
        for doc in target_docs:
            if total_chars >= max_chars:
                break
            chunk_rows = conn.execute(
                """
                SELECT content, page_number
                FROM document_chunks
                WHERE workspace_id = ? AND document_id = ?
                ORDER BY chunk_index ASC
                LIMIT 1
                """,
                (workspace_id, doc["id"]),
            ).fetchall()
            if not chunk_rows:
                continue
            combined = re.sub(r"\s+", " ", (chunk_rows[0]["content"] or "").strip())
            if not combined:
                continue
            excerpt = combined[:per_doc_budget]
            part = f"[{doc['file_name']}]: {excerpt}"
            remaining = max_chars - total_chars
            if len(part) > remaining:
                part = part[:remaining]
            snippets.append(part)
            total_chars += len(part)

    if total_chars < max_chars and notes:
        for n in notes:
            if total_chars >= max_chars:
                break
            text = f"[Ghi chú: {n['title']}] {(n['content'] or '')[:200]}"
            snippets.append(text[: max_chars - total_chars])
            total_chars += len(text)

    return {
        "doc_names": doc_names,
        "note_titles": note_titles,
        "context_text": "\n".join(snippets),
    }


def _normalize_category(raw_category: Any) -> str:
    value = str(raw_category or "").strip()
    if value in ALLOWED_WORKSPACE_CATEGORIES:
        return value
    norm = _normalize_vi(value)
    mapping = {
        "ky thuat": "Kỹ thuật",
        "cong nghe": "Kỹ thuật",
        "lap trinh": "Kỹ thuật",
        "it": "Kỹ thuật",
        "nghien cuu": "Nghiên cứu",
        "khoa hoc": "Nghiên cứu",
        "ngoai ngu": "Ngoại ngữ",
        "tieng anh": "Ngoại ngữ",
        "tieng nhat": "Ngoại ngữ",
        "dai hoc": "Đại học",
        "hoc tap": "Đại học",
        "mon hoc": "Đại học",
        "du an": "Dự án",
    }
    for k, target in mapping.items():
        if k in norm:
            return target
    return "Chung"


def build_workspace_profile_text(conn: Any, workspace_id: str) -> Optional[str]:
    """Tạo chuỗi mô tả hồ sơ đầy đủ của workspace để encode vector BGE-M3."""
    ws = conn.execute(
        "SELECT id, name, description, category FROM workspaces WHERE id = ?",
        (workspace_id,),
    ).fetchone()
    if not ws:
        return None

    doc_rows = conn.execute(
        "SELECT file_name FROM documents WHERE workspace_id = ? ORDER BY created_at DESC LIMIT 30",
        (workspace_id,),
    ).fetchall()
    note_rows = conn.execute(
        "SELECT title FROM notes WHERE workspace_id = ? ORDER BY updated_at DESC LIMIT 15",
        (workspace_id,),
    ).fetchall()
    nb_rows = conn.execute(
        "SELECT name FROM notebooks WHERE workspace_id = ? ORDER BY created_at DESC LIMIT 15",
        (workspace_id,),
    ).fetchall()

    parts = [str(ws["name"])]
    if ws["category"] and str(ws["category"]).strip() != "Chung":
        parts.append(str(ws["category"]))
    if ws["description"]:
        parts.append(str(ws["description"]))
    if doc_rows:
        parts.append(", ".join(_humanize_filename_stem(str(r["file_name"])) for r in doc_rows))
    if nb_rows:
        parts.append(", ".join(str(r["name"]) for r in nb_rows))
    if note_rows:
        parts.append(", ".join(str(r["title"]) for r in note_rows))
    return ". ".join(p for p in parts if p)


def upsert_workspace_embedding(workspace_id: str) -> bool:
    """Tính và lưu vector BGE-M3 cho hồ sơ workspace nếu nội dung thay đổi."""
    conn = get_db_connection()
    try:
        profile_text = build_workspace_profile_text(conn, workspace_id)
        if not profile_text:
            return False

        existing = conn.execute(
            "SELECT model, source_text FROM workspace_embeddings WHERE workspace_id = ?",
            (workspace_id,),
        ).fetchone()
        if (
            existing
            and existing["model"] == EMBEDDING_MODEL
            and existing["source_text"] == profile_text
        ):
            return True

        vectors = embed_texts([profile_text])
        if not vectors:
            return False
        vec = vectors[0]
        conn.execute(
            """
            INSERT INTO workspace_embeddings (workspace_id, model, dimensions, source_text, vector, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(workspace_id) DO UPDATE SET
                model = excluded.model,
                dimensions = excluded.dimensions,
                source_text = excluded.source_text,
                vector = excluded.vector,
                updated_at = CURRENT_TIMESTAMP
            """,
            (workspace_id, EMBEDDING_MODEL, len(vec), profile_text, pack_vector(vec)),
        )
        conn.commit()
        return True
    except Exception:
        logger.exception("Failed to upsert workspace embedding for %s", workspace_id)
        return False
    finally:
        conn.close()


async def generate_and_apply_workspace_metadata(
    workspace_id: str,
    model: str = DEFAULT_LLM_MODEL,
) -> Dict[str, Any]:
    """Tự động sinh & cập nhật Title, Description, Category cho Workspace từ toàn bộ tài liệu."""
    conn = get_db_connection()
    try:
        ws = conn.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
        if not ws:
            return {"updated": False, "source": "not_found", "workspace": None}

        owner_user_id = ws["owner_user_id"]
        ctx = _collect_workspace_context(conn, workspace_id)
        doc_names: List[str] = ctx["doc_names"]
        note_titles: List[str] = ctx["note_titles"]
        context_text: str = ctx["context_text"]

        if not doc_names and not note_titles:
            return {"updated": False, "source": "empty", "workspace": dict(ws)}

        other_rows = conn.execute(
            "SELECT name FROM workspaces WHERE owner_user_id IS ? AND id != ?",
            (owner_user_id, workspace_id),
        ).fetchall()
        other_names = [str(r["name"]) for r in other_rows if r["name"]]
    finally:
        conn.close()

    system_prompt = (
        "Bạn là chuyên gia tổ chức kho tri thức cá nhân. Dựa trên trích đoạn nội dung của TẤT CẢ tài liệu trong workspace, "
        "hãy đặt tiêu đề tổng quát và viết mô tả TỔNG HỢP CHỦ ĐỀ CHUNG bằng TIẾNG VIỆT.\n\n"
        "BẮT BUỘC TRẢ VỀ DUY NHẤT MỘT JSON OBJECT:\n"
        "{\n"
        '  "title": "Tên workspace ngắn gọn bằng tiếng Việt (3-8 từ, tối đa 70 ký tự, bao quát các tài liệu)",\n'
        '  "description": "Tóm tắt 1-2 câu bằng tiếng Việt (tối đa 220 ký tự) về nội dung kiến thức và mục đích học tập chung của workspace",\n'
        '  "category": "Chọn ĐÚNG 1 giá trị trong: Kỹ thuật | Nghiên cứu | Ngoại ngữ | Đại học | Dự án | Chung"\n'
        "}\n"
        "QUY TẮC BẮT BUỘC:\n"
        "- Viết cả title và description bằng tiếng Việt (chỉ giữ tên riêng/thuật ngữ như JLPT N3, Kanji, TCP/IP).\n"
        "- TUYỆT ĐỐI KHÔNG liệt kê tên tệp, KHÔNG chép đuôi tệp (.pdf, .xlsx, .docx) và KHÔNG viết kiểu 'Tổng hợp 3 tài liệu: ...' vào description."
    )

    files_summary = ", ".join(doc_names[:12])
    avoid_names = ", ".join(other_names[:12]) if other_names else "(không có)"
    user_prompt = (
        f"Các tệp hiện có ({len(doc_names)} tệp): {files_summary}\n"
        f"Tránh đặt trùng tên: {avoid_names}\n\n"
        f"Trích đoạn nội dung từ các tài liệu:\n{context_text or '(chỉ có tên tệp)'}\n\n"
        "Trả về JSON object gồm title, description, category bằng tiếng Việt:"
    )

    ai_res = await call_ollama_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=model,
        num_predict=180,
        num_ctx=2048,
        temperature=0.35,
        timeout_sec=180.0,
    )

    source = "ai"
    raw_data = ai_res.get("data") if ai_res.get("ok") else None
    if isinstance(raw_data, dict) and (raw_data.get("title") or raw_data.get("name")):
        raw_title = str(raw_data.get("title") or raw_data.get("name") or "").strip()
        raw_desc = str(raw_data.get("description") or "").strip()
        raw_cat = _normalize_category(raw_data.get("category"))
    else:
        source = "fallback"
        raw_title, raw_desc, raw_cat = _build_fallback_metadata(doc_names, note_titles)

    conn = get_db_connection()
    try:
        ws = conn.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
        if not ws:
            return {"updated": False, "source": "not_found", "workspace": None}

        existing_desc = (ws["description"] or "").strip()
        if source == "fallback" and not _is_default_workspace_name(ws["name"]) and len(doc_names) > 1:
            final_title = ws["name"]
            final_cat = ws["category"] or raw_cat
            final_desc = existing_desc if (existing_desc and not _looks_like_file_list_desc(existing_desc)) else raw_desc[:500]
        else:
            final_title = _deduplicate_workspace_title(
                conn, workspace_id, ws["owner_user_id"], raw_title
            )
            final_cat = raw_cat
            final_desc = raw_desc[:500] if raw_desc else existing_desc

        conn.execute(
            """
            UPDATE workspaces
            SET name = ?, description = ?, category = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (final_title, final_desc, final_cat, workspace_id),
        )
        conn.commit()
        updated_row = conn.execute(
            """
            SELECT w.*,
                   (SELECT COUNT(*) FROM documents d WHERE d.workspace_id = w.id) AS doc_count,
                   (SELECT COUNT(*) FROM chat_sessions s WHERE s.workspace_id = w.id) AS conversation_count
            FROM workspaces w
            WHERE w.id = ?
            """,
            (workspace_id,),
        ).fetchone()
    finally:
        conn.close()

    upsert_workspace_embedding(workspace_id)
    return {
        "updated": True,
        "source": source,
        "model_used": ai_res.get("model_used"),
        "workspace": dict(updated_row) if updated_row else None,
    }


def _cosine_plain(left: List[float], right: List[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    norm_l = math.sqrt(sum(a * a for a in left))
    norm_r = math.sqrt(sum(b * b for b in right))
    return dot / (norm_l * norm_r) if norm_l and norm_r else 0.0


def _score_vector_rows(
    q_vec_list: Optional[List[float]],
    rows: List[Any],
    blob_key: str = "vector",
    dims_key: str = "dimensions",
) -> List[float]:
    if not q_vec_list or not rows:
        return [0.0] * len(rows)

    if np is not None:
        q_arr = np.asarray(q_vec_list, dtype=np.float32)
        q_norm = float(np.linalg.norm(q_arr))
        if q_norm <= 0:
            return [0.0] * len(rows)
        q_arr = q_arr / q_norm
        q_dim = q_arr.shape[0]

        scores = [0.0] * len(rows)
        valid_indices: List[int] = []
        valid_vecs: List[Any] = []
        for idx, r in enumerate(rows):
            dims = int(r[dims_key])
            if dims != q_dim:
                continue
            vec = np.frombuffer(r[blob_key], dtype=np.float32, count=dims)
            valid_indices.append(idx)
            valid_vecs.append(vec)

        if valid_vecs:
            mat = np.vstack(valid_vecs)
            norms = np.linalg.norm(mat, axis=1, keepdims=True)
            safe_norms = np.where(norms > 0, norms, 1.0)
            mat_norm = mat / safe_norms
            dots = mat_norm @ q_arr
            for pos, score in zip(valid_indices, dots.tolist()):
                scores[pos] = max(0.0, float(score))
        return scores

    return [
        max(0.0, _cosine_plain(q_vec_list, unpack_vector(r[blob_key], int(r[dims_key]))))
        for r in rows
    ]


def _keyword_match_score(
    query_norm: str,
    query_tokens: List[str],
    target_text: str,
    raw_query_tokens: Optional[List[str]] = None,
) -> float:
    """So khớp từ khóa theo ranh giới nguyên từ và giữ phân biệt dấu tiếng Việt khi cần."""
    if not query_norm or not target_text:
        return 0.0
    target_norm = _normalize_vi(target_text)
    if not target_norm:
        return 0.0

    target_spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", target_text)
    target_raw_words = set(re.findall(r"[^\W_]+", target_spaced.lower(), flags=re.UNICODE))
    target_norm_words = set(target_norm.split())

    norm_to_raw_variants: Dict[str, set[str]] = {}
    for rw in target_raw_words:
        nw = _normalize_vi(rw)
        if nw:
            norm_to_raw_variants.setdefault(nw, set()).add(rw)

    if re.search(rf"(?<!\w){re.escape(query_norm)}(?!\w)", target_norm):
        if raw_query_tokens and any(_has_accent(rt) for rt in raw_query_tokens):
            phrase_ok = True
            for rt in raw_query_tokens:
                rt_l = rt.lower()
                nt = _normalize_vi(rt_l)
                variants = norm_to_raw_variants.get(nt, set())
                if _has_accent(rt_l) and variants and rt_l not in variants and nt not in variants:
                    phrase_ok = False
                    break
            if phrase_ok:
                return 1.0
        else:
            return 1.0

    if not query_tokens:
        return 0.0

    raw_map: Dict[str, str] = {}
    if raw_query_tokens:
        for rt in raw_query_tokens:
            nt = _normalize_vi(rt)
            if nt:
                raw_map[nt] = rt.lower()

    hits = 0
    for tok in query_tokens:
        if tok not in target_norm_words:
            continue
        raw_tok = raw_map.get(tok)
        if raw_tok and _has_accent(raw_tok):
            variants = norm_to_raw_variants.get(tok, set())
            if variants and raw_tok not in variants and tok not in variants:
                continue
        hits += 1

    return hits / len(query_tokens)


def _ensure_user_workspace_embeddings(conn: Any, user_id: str, workspace_ids: List[str]) -> None:
    if not workspace_ids:
        return
    placeholders = ",".join("?" for _ in workspace_ids)
    existing_rows = conn.execute(
        f"SELECT workspace_id, model, source_text FROM workspace_embeddings WHERE workspace_id IN ({placeholders})",
        tuple(workspace_ids),
    ).fetchall()
    existing_map = {r["workspace_id"]: r for r in existing_rows}

    to_embed: List[Tuple[str, str]] = []
    for ws_id in workspace_ids:
        profile_text = build_workspace_profile_text(conn, ws_id)
        if not profile_text:
            continue
        cur = existing_map.get(ws_id)
        if cur and cur["model"] == EMBEDDING_MODEL and cur["source_text"] == profile_text:
            continue
        to_embed.append((ws_id, profile_text))

    if not to_embed:
        return

    vectors = embed_texts([item[1] for item in to_embed])
    if not vectors:
        return

    for (ws_id, profile_text), vec in zip(to_embed, vectors):
        conn.execute(
            """
            INSERT INTO workspace_embeddings (workspace_id, model, dimensions, source_text, vector, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(workspace_id) DO UPDATE SET
                model = excluded.model,
                dimensions = excluded.dimensions,
                source_text = excluded.source_text,
                vector = excluded.vector,
                updated_at = CURRENT_TIMESTAMP
            """,
            (ws_id, EMBEDDING_MODEL, len(vec), profile_text, pack_vector(vec)),
        )
    conn.commit()


def _query_fts_hits_for_user(
    conn: Any,
    user_id: str,
    tokens: List[str],
    q_norm: str = "",
    q_tokens: Optional[List[str]] = None,
    limit: int = 80,
) -> Dict[str, Tuple[float, str, str, str, int, str]]:
    """Trả về map chunk_id -> (score, workspace_id, document_id, file_name, page_number, content).
    Hậu kiểm dấu tiếng Việt để tránh FTS5 unicode61 khớp nhầm 'đề thi' với 'để thì'.
    """
    if not tokens:
        return {}
    match_query = " OR ".join('"' + tok.replace('"', '""') + '"' for tok in tokens)
    try:
        rows = conn.execute(
            """
            SELECT c.id AS chunk_id, c.document_id, c.workspace_id, c.content,
                   c.page_number, d.file_name, bm25(chunks_fts) AS raw_bm25
            FROM chunks_fts f
            JOIN document_chunks c ON c.id = f.chunk_id
            JOIN documents d ON d.id = c.document_id
            JOIN workspaces w ON w.id = c.workspace_id
            WHERE chunks_fts MATCH ? AND w.owner_user_id = ?
            ORDER BY raw_bm25 ASC
            LIMIT ?
            """,
            (match_query, user_id, limit),
        ).fetchall()
    except Exception:
        return {}

    norm_toks = q_tokens if q_tokens is not None else [_normalize_vi(t) for t in tokens if _normalize_vi(t)]
    norm_str = q_norm or " ".join(norm_toks)
    min_ratio = 0.66 if len(norm_toks) >= 2 else 1.0

    hits: Dict[str, Tuple[float, str, str, str, int, str]] = {}
    for rank, r in enumerate(rows):
        kw_ratio = _keyword_match_score(norm_str, norm_toks, str(r["content"] or ""), tokens)
        if kw_ratio < min_ratio:
            continue
        score = (1.0 / (1.0 + rank * 0.25)) * kw_ratio
        key = r["chunk_id"]
        hits[key] = (
            score,
            r["workspace_id"],
            r["document_id"],
            r["file_name"],
            int(r["page_number"] or 1),
            r["content"],
        )
    return hits


def semantic_search_workspaces(
    user_id: str,
    query: str,
    limit: int = 30,
    precomputed_query_vec: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """Tìm kiếm Workspace đa tầng bằng BGE-M3 + FTS5 + chuẩn hóa từ khóa tiếng Việt."""
    q_clean = (query or "").strip()
    conn = get_db_connection()
    try:
        ws_rows = conn.execute(
            """
            SELECT w.*,
                   (SELECT COUNT(*) FROM documents d WHERE d.workspace_id = w.id) AS doc_count,
                   (SELECT COUNT(*) FROM chat_sessions s WHERE s.workspace_id = w.id) AS conversation_count
            FROM workspaces w
            WHERE w.owner_user_id = ?
            ORDER BY COALESCE(w.updated_at, w.created_at) DESC
            """,
            (user_id,),
        ).fetchall()
        if not ws_rows:
            return {"workspaces": [], "search_mode": "empty"}

        if not q_clean:
            return {"workspaces": [dict(r) for r in ws_rows[:limit]], "search_mode": "all"}

        workspaces_by_id: Dict[str, Dict[str, Any]] = {r["id"]: dict(r) for r in ws_rows}
        ws_ids = list(workspaces_by_id.keys())

        doc_names_by_ws: Dict[str, List[str]] = {ws_id: [] for ws_id in ws_ids}
        for d in conn.execute(
            """
            SELECT d.workspace_id, d.file_name
            FROM documents d
            JOIN workspaces w ON w.id = d.workspace_id
            WHERE w.owner_user_id = ?
            """,
            (user_id,),
        ).fetchall():
            if d["workspace_id"] in doc_names_by_ws:
                doc_names_by_ws[d["workspace_id"]].append(str(d["file_name"]))

        note_text_by_ws: Dict[str, str] = {ws_id: "" for ws_id in ws_ids}
        for n in conn.execute(
            """
            SELECT n.workspace_id, n.title, n.content
            FROM notes n
            JOIN workspaces w ON w.id = n.workspace_id
            WHERE w.owner_user_id = ?
            """,
            (user_id,),
        ).fetchall():
            ws_id = n["workspace_id"]
            if ws_id in note_text_by_ws:
                note_text_by_ws[ws_id] += f" {n['title']} {(n['content'] or '')[:400]}"

        q_vecs = [precomputed_query_vec] if precomputed_query_vec else embed_texts([q_clean])
        q_vec = q_vecs[0] if q_vecs else None
        search_mode = "semantic" if q_vec is not None else "keyword"

        if q_vec is not None:
            _ensure_user_workspace_embeddings(conn, user_id, ws_ids)

        # 1. Tầng Metadata Workspace (BGE-M3 + Keyword tiếng Việt)
        meta_dense_by_ws: Dict[str, float] = {ws_id: 0.0 for ws_id in ws_ids}
        if q_vec is not None:
            placeholders = ",".join("?" for _ in ws_ids)
            we_rows = conn.execute(
                f"""
                SELECT workspace_id, vector, dimensions
                FROM workspace_embeddings
                WHERE workspace_id IN ({placeholders}) AND model = ?
                """,
                (*ws_ids, EMBEDDING_MODEL),
            ).fetchall()
            we_scores = _score_vector_rows(q_vec, we_rows)
            for row, sc in zip(we_rows, we_scores):
                meta_dense_by_ws[row["workspace_id"]] = sc

        # 2. Tầng Nội dung Tài liệu xuyên các Workspace (chunk_embeddings + chunks_fts)
        content_dense_by_ws: Dict[str, float] = {ws_id: 0.0 for ws_id in ws_ids}
        if q_vec is not None:
            chunk_rows = conn.execute(
                """
                SELECT c.workspace_id, c.content, e.vector, e.dimensions
                FROM chunk_embeddings e
                JOIN document_chunks c ON c.id = e.chunk_id
                JOIN workspaces w ON w.id = c.workspace_id
                WHERE w.owner_user_id = ? AND e.model = ?
                """,
                (user_id, EMBEDDING_MODEL),
            ).fetchall()
            chunk_scores = _score_vector_rows(q_vec, chunk_rows)
            ws_top_scores: Dict[str, List[float]] = {}
            for row, sc in zip(chunk_rows, chunk_scores):
                content_len = len((row["content"] or "").strip())
                # Giảm trọng số các chunk tiêu đề/rác quá ngắn (vd 'PHẦN 1 SLIDE')
                adj_sc = sc * 0.80 if content_len < 45 else sc
                ws_top_scores.setdefault(row["workspace_id"], []).append(adj_sc)
            for ws_id, scs in ws_top_scores.items():
                scs.sort(reverse=True)
                best = scs[0]
                top3_avg = sum(scs[:3]) / min(len(scs), 3)
                content_dense_by_ws[ws_id] = 0.75 * best + 0.25 * top3_avg

        q_norm, q_tokens, raw_tokens = _extract_query_tokens(q_clean)

        fts_hits = _query_fts_hits_for_user(
            conn, user_id, raw_tokens, q_norm=q_norm, q_tokens=q_tokens, limit=60
        )
        fts_by_ws: Dict[str, float] = {ws_id: 0.0 for ws_id in ws_ids}
        for hit in fts_hits.values():
            _, ws_id, _, _, _, _ = hit
            if ws_id in fts_by_ws:
                fts_by_ws[ws_id] = max(fts_by_ws[ws_id], hit[0])

        min_kw_ratio = 0.66 if len(q_tokens) >= 2 else 0.99
        scored: List[Tuple[float, bool, Dict[str, Any]]] = []
        for ws_id, ws in workspaces_by_id.items():
            name_kw = _keyword_match_score(q_norm, q_tokens, ws.get("name", ""), raw_tokens)
            desc_kw = _keyword_match_score(
                q_norm,
                q_tokens,
                f"{ws.get('description', '')} {ws.get('category', '')}",
                raw_tokens,
            )
            files_kw = _keyword_match_score(
                q_norm,
                q_tokens,
                " ".join(f"{fn} {_humanize_filename_stem(fn)}" for fn in doc_names_by_ws.get(ws_id, [])),
                raw_tokens,
            )
            note_kw = _keyword_match_score(q_norm, q_tokens, note_text_by_ws.get(ws_id, ""), raw_tokens)

            best_kw_ratio = max(name_kw, desc_kw, files_kw, note_kw)
            meta_kw = max(name_kw * 0.45, desc_kw * 0.30, files_kw * 0.28, note_kw * 0.22)
            m_dense = meta_dense_by_ws.get(ws_id, 0.0)
            c_dense = content_dense_by_ws.get(ws_id, 0.0)
            fts_sc = fts_by_ws.get(ws_id, 0.0)

            best_semantic = max(m_dense, c_dense)
            synergy = min(m_dense, c_dense)
            final_score = best_semantic + 0.15 * synergy + meta_kw + 0.20 * fts_sc

            has_kw = best_kw_ratio >= min_kw_ratio or fts_sc > 0.0
            if q_vec is not None:
                is_relevant = has_kw or best_semantic >= 0.49
            else:
                is_relevant = has_kw

            if is_relevant:
                item = dict(ws)
                item["score"] = round(final_score, 4)
                scored.append((final_score, has_kw, item))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        if scored:
            top_score = scored[0][0]
            if top_score >= 0.65:
                rel_floor = max(0.49, top_score * 0.65)
                scored = [pair for pair in scored if pair[1] or pair[0] >= rel_floor]
        return {
            "workspaces": [pair[2] for pair in scored[:limit]],
            "search_mode": search_mode,
        }
    finally:
        conn.close()


def _score_small_entity_group(
    q_vec: Optional[List[float]],
    q_norm: str,
    q_tokens: List[str],
    raw_tokens: List[str],
    records: List[Dict[str, Any]],
    ws_name_map: Dict[str, str],
    per_group_cap: int,
) -> List[Dict[str, Any]]:
    """Chấm điểm kết hợp từ khóa và vector ngữ nghĩa cho nhóm dữ liệu vừa/nhỏ."""
    if not records:
        return []
    texts = [r["embed_text"] for r in records]
    vecs = embed_texts(texts) if (q_vec is not None and len(records) <= 40) else None
    min_kw_ratio = 0.66 if len(q_tokens) >= 2 else 0.99
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for idx, rec in enumerate(records):
        kw = _keyword_match_score(q_norm, q_tokens, rec["kw_text"], raw_tokens)
        sem = max(0.0, _cosine_plain(q_vec, vecs[idx])) if (q_vec and vecs) else 0.0
        sc = sem + 0.5 * kw
        if kw >= min_kw_ratio or sem >= 0.49:
            ws_name = ws_name_map.get(rec["workspace_id"], "Workspace")
            scored.append((
                sc,
                {
                    "id": rec["id"],
                    "kind": rec["kind"],
                    "workspaceId": rec["workspace_id"],
                    "title": rec["title"],
                    "snippet": rec["snippet"] or ws_name,
                    "path": rec["path"],
                    "trail": ws_name,
                    "score": round(sc, 4),
                },
            ))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [pair[1] for pair in scored[:per_group_cap]]


def semantic_global_search(
    user_id: str,
    query: str,
    kind: str = "all",
    limit: int = 24,
) -> Dict[str, Any]:
    """Tìm kiếm ngữ nghĩa xuyên suốt Workspace, Notebook, Tài liệu, Ghi chú, Hội thoại cho Ctrl+K."""
    q_clean = (query or "").strip()
    if not q_clean:
        return {"hits": [], "search_mode": "empty"}

    q_vecs = embed_texts([q_clean])
    q_vec = q_vecs[0] if q_vecs else None
    search_mode = "semantic" if q_vec is not None else "keyword"

    q_norm, q_tokens, raw_tokens = _extract_query_tokens(q_clean)

    hits: List[Dict[str, Any]] = []
    per_group_cap = limit if kind != "all" else max(3, limit // 5)

    # 1. Workspaces
    if kind in ("all", "workspace"):
        ws_result = semantic_search_workspaces(
            user_id=user_id,
            query=q_clean,
            limit=per_group_cap,
            precomputed_query_vec=q_vec,
        )
        for w in ws_result["workspaces"]:
            hits.append({
                "id": w["id"],
                "kind": "workspace",
                "workspaceId": w["id"],
                "title": w["name"],
                "snippet": w.get("description") or f"{w.get('doc_count', 0)} tài liệu · Workspace",
                "path": f"/knowledge/{w['id']}",
                "trail": w.get("category") or "Workspace",
                "score": float(w.get("score", 0.0)),
            })

    conn = get_db_connection()
    try:
        ws_name_map: Dict[str, str] = {
            r["id"]: r["name"]
            for r in conn.execute(
                "SELECT id, name FROM workspaces WHERE owner_user_id = ?",
                (user_id,),
            ).fetchall()
        }
        if not ws_name_map:
            return {"hits": hits[:limit], "search_mode": search_mode}

        # 2. Documents (tìm cả theo nội dung chunk BGE-M3 + FTS5 + tên file)
        if kind in ("all", "document"):
            doc_rows = conn.execute(
                """
                SELECT d.id, d.workspace_id, d.file_name, d.file_type, d.total_chunks
                FROM documents d
                JOIN workspaces w ON w.id = d.workspace_id
                WHERE w.owner_user_id = ?
                """,
                (user_id,),
            ).fetchall()
            doc_info = {r["id"]: dict(r) for r in doc_rows}
            best_by_doc: Dict[str, Dict[str, Any]] = {}

            if q_vec is not None and doc_info:
                c_rows = conn.execute(
                    """
                    SELECT c.document_id, c.workspace_id, c.content, c.page_number,
                           e.vector, e.dimensions
                    FROM chunk_embeddings e
                    JOIN document_chunks c ON c.id = e.chunk_id
                    JOIN workspaces w ON w.id = c.workspace_id
                    WHERE w.owner_user_id = ? AND e.model = ?
                    """,
                    (user_id, EMBEDDING_MODEL),
                ).fetchall()
                c_scores = _score_vector_rows(q_vec, c_rows)
                for row, sc in zip(c_rows, c_scores):
                    content_str = (row["content"] or "").strip()
                    adj_sc = sc * 0.80 if len(content_str) < 45 else sc
                    doc_id = row["document_id"]
                    prev = best_by_doc.get(doc_id)
                    if prev is None or adj_sc > prev["dense_score"]:
                        best_by_doc[doc_id] = {
                            "dense_score": adj_sc,
                            "fts_score": 0.0,
                            "snippet": content_str,
                            "page": int(row["page_number"] or 1),
                        }

            fts_hits = _query_fts_hits_for_user(
                conn, user_id, raw_tokens, q_norm=q_norm, q_tokens=q_tokens, limit=60
            )
            for fts_sc, _, doc_id, _, page_no, content in fts_hits.values():
                entry = best_by_doc.setdefault(
                    doc_id,
                    {"dense_score": 0.0, "fts_score": 0.0, "snippet": "", "page": page_no},
                )
                if fts_sc > entry["fts_score"]:
                    entry["fts_score"] = fts_sc
                    if not entry["snippet"]:
                        entry["snippet"] = (content or "").strip()
                        entry["page"] = page_no

            min_kw_ratio = 0.66 if len(q_tokens) >= 2 else 0.99
            doc_scored: List[Tuple[float, bool, Dict[str, Any]]] = []
            for doc_id, doc in doc_info.items():
                name_kw = _keyword_match_score(
                    q_norm, q_tokens, f"{doc['file_name']} {_humanize_filename_stem(doc['file_name'])}", raw_tokens
                )
                entry = best_by_doc.get(doc_id, {"dense_score": 0.0, "fts_score": 0.0, "snippet": "", "page": 1})
                dense_sc = float(entry["dense_score"])
                fts_sc = float(entry["fts_score"])
                score = dense_sc + 0.45 * name_kw + 0.25 * fts_sc
                has_kw = name_kw >= min_kw_ratio or fts_sc > 0.0
                is_rel = has_kw or (q_vec is not None and dense_sc >= 0.49)
                if not is_rel:
                    continue

                snippet_raw = entry["snippet"]
                if snippet_raw:
                    snippet_clean = re.sub(r"\s+", " ", snippet_raw)[:140]
                    snippet = f"Tr.{entry['page']}: {snippet_clean}"
                else:
                    snippet = f"{str(doc['file_type']).upper()} · {doc['total_chunks']} chunks"

                ws_name = ws_name_map.get(doc["workspace_id"], "Workspace")
                doc_scored.append((
                    score,
                    has_kw,
                    {
                        "id": doc_id,
                        "kind": "document",
                        "workspaceId": doc["workspace_id"],
                        "title": doc["file_name"],
                        "snippet": snippet,
                        "path": f"/documents/{doc_id}",
                        "trail": ws_name,
                        "score": round(score, 4),
                    },
                ))
            doc_scored.sort(key=lambda pair: pair[0], reverse=True)
            if doc_scored:
                top_doc_sc = doc_scored[0][0]
                if top_doc_sc >= 0.65:
                    doc_floor = max(0.49, top_doc_sc * 0.65)
                    doc_scored = [p for p in doc_scored if p[1] or p[0] >= doc_floor]
            hits.extend(pair[2] for pair in doc_scored[:per_group_cap])

        # 3. Notebooks
        if kind in ("all", "notebook"):
            nb_rows = conn.execute(
                """
                SELECT n.id, n.workspace_id, n.name, n.description
                FROM notebooks n
                JOIN workspaces w ON w.id = n.workspace_id
                WHERE w.owner_user_id = ?
                """,
                (user_id,),
            ).fetchall()
            nb_records = [
                {
                    "id": r["id"],
                    "kind": "notebook",
                    "workspace_id": r["workspace_id"],
                    "title": r["name"],
                    "snippet": r["description"] or f"Thuộc {ws_name_map.get(r['workspace_id'], 'Workspace')}",
                    "path": f"/knowledge/{r['workspace_id']}/notebooks/{r['id']}",
                    "embed_text": f"{r['name']}. {r['description'] or ''}",
                    "kw_text": f"{r['name']} {r['description'] or ''}",
                }
                for r in nb_rows
            ]
            hits.extend(_score_small_entity_group(q_vec, q_norm, q_tokens, raw_tokens, nb_records, ws_name_map, per_group_cap))

        # 4. Notes
        if kind in ("all", "note"):
            note_rows = conn.execute(
                """
                SELECT n.id, n.workspace_id, n.title, n.content
                FROM notes n
                JOIN workspaces w ON w.id = n.workspace_id
                WHERE w.owner_user_id = ?
                ORDER BY n.updated_at DESC
                LIMIT 60
                """,
                (user_id,),
            ).fetchall()
            note_records = [
                {
                    "id": r["id"],
                    "kind": "note",
                    "workspace_id": r["workspace_id"],
                    "title": r["title"],
                    "snippet": re.sub(r"\s+", " ", (r["content"] or ""))[:130] or "Ghi chú",
                    "path": "/study?tab=notes",
                    "embed_text": f"{r['title']}. {(r['content'] or '')[:350]}",
                    "kw_text": f"{r['title']} {r['content'] or ''}",
                }
                for r in note_rows
            ]
            hits.extend(_score_small_entity_group(q_vec, q_norm, q_tokens, raw_tokens, note_records, ws_name_map, per_group_cap))

        # 5. Conversations
        if kind in ("all", "conversation"):
            conv_rows = conn.execute(
                """
                SELECT s.id, s.workspace_id, s.title
                FROM chat_sessions s
                JOIN workspaces w ON w.id = s.workspace_id
                WHERE w.owner_user_id = ?
                ORDER BY COALESCE(s.updated_at, s.created_at) DESC
                LIMIT 50
                """,
                (user_id,),
            ).fetchall()
            msg_by_session: Dict[str, List[str]] = {}
            if conv_rows:
                sess_ids = [r["id"] for r in conv_rows]
                ph = ",".join("?" for _ in sess_ids)
                for mr in conn.execute(
                    f"""
                    SELECT session_id, content
                    FROM chat_messages
                    WHERE session_id IN ({ph})
                    ORDER BY created_at DESC
                    """,
                    tuple(sess_ids),
                ).fetchall():
                    bucket = msg_by_session.setdefault(mr["session_id"], [])
                    if len(bucket) < 4:
                        bucket.append(str(mr["content"] or ""))

            conv_records = []
            for r in conv_rows:
                recent_text = " ".join(msg_by_session.get(r["id"], []))
                conv_records.append({
                    "id": r["id"],
                    "kind": "conversation",
                    "workspace_id": r["workspace_id"],
                    "title": r["title"],
                    "snippet": re.sub(r"\s+", " ", recent_text)[:130] or "Hội thoại AI",
                    "path": f"/chat/{r['id']}",
                    "embed_text": f"{r['title']}. {recent_text[:350]}",
                    "kw_text": f"{r['title']} {recent_text}",
                })
            hits.extend(_score_small_entity_group(q_vec, q_norm, q_tokens, raw_tokens, conv_records, ws_name_map, per_group_cap))

        return {"hits": hits[:limit], "search_mode": search_mode}
    finally:
        conn.close()
