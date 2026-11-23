"""Đối chiếu thay đổi giữa các phiên bản tài liệu (v1 -> v2) bằng difflib + tóm tắt LLM."""
import difflib
import re
from typing import Any, Dict, List, Optional, Tuple

from app.config import DEFAULT_LLM_MODEL
from app.database import get_db_connection
from app.services.llm_service import check_ollama_status, resolve_available_chat_model

_SECTION_HEADING_RE = re.compile(
    r"^(?:Điều|Khoản|Mục|Chương|Phần|Article|Section|Chapter)\s+\d+[^\n]*",
    re.IGNORECASE | re.UNICODE,
)


def _split_meaningful_units(text: str) -> List[str]:
    """Tách văn bản thành các đơn vị Điều/Khoản hoặc đoạn văn có ý nghĩa để so sánh chính xác."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    units: List[str] = []
    buffer: List[str] = []
    for ln in lines:
        if _SECTION_HEADING_RE.match(ln) and buffer:
            units.append(" ".join(buffer))
            buffer = [ln]
        else:
            buffer.append(ln)
            if len(" ".join(buffer)) >= 280 or ln.endswith((".", "!", "?", ";", ":")):
                units.append(" ".join(buffer))
                buffer = []
    if buffer:
        units.append(" ".join(buffer))
    return units


def _load_document_full_text(conn: Any, doc_id: str) -> Tuple[Optional[Dict[str, Any]], str]:
    doc_row = conn.execute(
        """
        SELECT id, workspace_id, file_name, version_group_id,
               COALESCE(version_number, 1) AS version_number,
               COALESCE(is_latest, 1) AS is_latest,
               effective_date, created_at
        FROM documents WHERE id = ?
        """,
        (doc_id,),
    ).fetchone()
    if not doc_row:
        return None, ""
    chunks = conn.execute(
        "SELECT content FROM document_chunks WHERE document_id = ? ORDER BY chunk_index ASC",
        (doc_id,),
    ).fetchall()
    return dict(doc_row), "\n".join(str(r["content"]) for r in chunks)


def resolve_version_pair(
    workspace_id: str,
    old_document_id: Optional[str] = None,
    new_document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """Xác định cặp (bản cũ, bản mới) để so sánh trong Workspace."""
    conn = get_db_connection()
    try:
        if old_document_id and new_document_id:
            old_doc, _ = _load_document_full_text(conn, old_document_id)
            new_doc, _ = _load_document_full_text(conn, new_document_id)
            if old_doc and new_doc:
                return old_doc, new_doc
            return None

        if document_ids and len(document_ids) >= 2:
            rows = conn.execute(
                f"""
                SELECT id, workspace_id, file_name, version_group_id,
                       COALESCE(version_number, 1) AS version_number,
                       COALESCE(is_latest, 1) AS is_latest,
                       effective_date, created_at
                FROM documents
                WHERE workspace_id = ? AND id IN ({','.join('?' for _ in document_ids[:2])})
                ORDER BY COALESCE(version_number, 1) ASC, created_at ASC
                """,
                (workspace_id, *document_ids[:2]),
            ).fetchall()
            if len(rows) >= 2:
                return dict(rows[0]), dict(rows[1])

        target_id = new_document_id or old_document_id or (document_ids[0] if document_ids else None)
        if target_id:
            row = conn.execute(
                "SELECT version_group_id FROM documents WHERE id = ? AND workspace_id = ?",
                (target_id, workspace_id),
            ).fetchone()
            if row and row["version_group_id"]:
                versions = conn.execute(
                    """
                    SELECT id, workspace_id, file_name, version_group_id,
                           COALESCE(version_number, 1) AS version_number,
                           COALESCE(is_latest, 1) AS is_latest,
                           effective_date, created_at
                    FROM documents
                    WHERE workspace_id = ? AND version_group_id = ?
                    ORDER BY COALESCE(version_number, 1) ASC, created_at ASC
                    """,
                    (workspace_id, row["version_group_id"]),
                ).fetchall()
                if len(versions) >= 2:
                    return dict(versions[-2]), dict(versions[-1])

        # Tự tìm nhóm phiên bản mới nhất trong Workspace có từ 2 phiên bản trở lên
        groups = conn.execute(
            """
            SELECT version_group_id
            FROM documents
            WHERE workspace_id = ? AND version_group_id IS NOT NULL
            GROUP BY version_group_id
            HAVING COUNT(*) >= 2
            ORDER BY MAX(created_at) DESC
            LIMIT 1
            """,
            (workspace_id,),
        ).fetchall()
        if groups:
            vg_id = groups[0]["version_group_id"]
            versions = conn.execute(
                """
                SELECT id, workspace_id, file_name, version_group_id,
                       COALESCE(version_number, 1) AS version_number,
                       COALESCE(is_latest, 1) AS is_latest,
                       effective_date, created_at
                FROM documents
                WHERE workspace_id = ? AND version_group_id = ?
                ORDER BY COALESCE(version_number, 1) ASC, created_at ASC
                """,
                (workspace_id, vg_id),
            ).fetchall()
            if len(versions) >= 2:
                return dict(versions[-2]), dict(versions[-1])

        # Fallback: nếu user vừa upload 2 tài liệu gần nhất để đối chiếu
        recent = conn.execute(
            """
            SELECT id, workspace_id, file_name, version_group_id,
                   COALESCE(version_number, 1) AS version_number,
                   COALESCE(is_latest, 1) AS is_latest,
                   effective_date, created_at
            FROM documents
            WHERE workspace_id = ?
            ORDER BY created_at DESC
            LIMIT 2
            """,
            (workspace_id,),
        ).fetchall()
        if len(recent) == 2:
            return dict(recent[1]), dict(recent[0])
        return None
    finally:
        conn.close()


def compute_document_diff(
    workspace_id: str,
    old_document_id: Optional[str] = None,
    new_document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """So sánh chi tiết nội dung giữa hai phiên bản tài liệu bằng SequenceMatcher."""
    pair = resolve_version_pair(
        workspace_id,
        old_document_id=old_document_id,
        new_document_id=new_document_id,
        document_ids=document_ids,
    )
    if not pair:
        return {
            "ok": False,
            "error": "Chưa có đủ 2 phiên bản tài liệu trong không gian này để đối chiếu thay đổi.",
            "changes": [],
        }

    old_meta, new_meta = pair
    conn = get_db_connection()
    try:
        _, old_text = _load_document_full_text(conn, old_meta["id"])
        _, new_text = _load_document_full_text(conn, new_meta["id"])
    finally:
        conn.close()

    old_units = _split_meaningful_units(old_text)
    new_units = _split_meaningful_units(new_text)

    matcher = difflib.SequenceMatcher(None, old_units, new_units, autojunk=False)
    changes: List[Dict[str, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        before_txt = " ".join(old_units[i1:i2]).strip()
        after_txt = " ".join(new_units[j1:j2]).strip()
        if before_txt == after_txt:
            continue
        kind = "modified" if tag == "replace" else ("added" if tag == "insert" else "removed")
        changes.append({
            "kind": kind,
            "before": before_txt[:600],
            "after": after_txt[:600],
        })
        if len(changes) >= 18:
            break

    similarity_pct = round(matcher.ratio() * 100, 1)
    return {
        "ok": True,
        "old_document": old_meta,
        "new_document": new_meta,
        "similarity_percent": similarity_pct,
        "changes": changes,
        "total_changes": len(changes),
    }


def format_diff_markdown(diff_result: Dict[str, Any]) -> str:
    """Định dạng kết quả đối chiếu thành Markdown sạch ngay cả khi không cần LLM."""
    if not diff_result.get("ok"):
        return str(diff_result.get("error") or "Không tìm thấy cặp tài liệu để đối chiếu.")

    old_doc = diff_result["old_document"]
    new_doc = diff_result["new_document"]
    changes = diff_result.get("changes", [])

    old_label = f"{old_doc['file_name']} (v{old_doc.get('version_number', 1)})"
    new_label = f"{new_doc['file_name']} (v{new_doc.get('version_number', 1)})"
    lines = [
        f"## Đối chiếu thay đổi: {old_label} -> {new_label}",
        "",
        f"- **Mức độ tương đồng tổng thể:** {diff_result.get('similarity_percent', 100)}%",
        f"- **Số điểm khác biệt phát hiện:** {len(changes)}",
        "",
    ]
    if not changes:
        lines.append("Hai phiên bản có nội dung văn bản trùng khớp hoàn toàn, không phát hiện thay đổi.")
        return "\n".join(lines)

    lines.append("| STT | Loại thay đổi | Nội dung cũ | Nội dung mới |")
    lines.append("| :--- | :--- | :--- | :--- |")
    kind_labels = {"modified": "Sửa đổi", "added": "Bổ sung mới", "removed": "Loại bỏ"}
    for idx, ch in enumerate(changes[:12], start=1):
        before_cell = (ch.get("before") or "*(Không có)*").replace("|", "\\|").replace("\n", " ")[:220]
        after_cell = (ch.get("after") or "*(Đã xóa)*").replace("|", "\\|").replace("\n", " ")[:220]
        lines.append(f"| {idx} | **{kind_labels.get(ch['kind'], ch['kind'])}** | {before_cell} | {after_cell} |")

    return "\n".join(lines)


async def summarize_diff_with_llm(diff_result: Dict[str, Any], model: str = DEFAULT_LLM_MODEL) -> str:
    """Tạo bảng tóm tắt thay đổi tự nhiên bằng Ollama (fallback về format_diff_markdown nếu offline)."""
    deterministic_md = format_diff_markdown(diff_result)
    if not diff_result.get("ok") or not diff_result.get("changes"):
        return deterministic_md

    ollama_status = await check_ollama_status()
    if not ollama_status.get("running"):
        return deterministic_md

    chosen = resolve_available_chat_model(model, ollama_status.get("available_models", []))
    if not chosen:
        return deterministic_md

    import httpx
    from app.config import OLLAMA_BASE_URL, OLLAMA_TIMEOUT

    sys_prompt = (
        "Bạn là chuyên gia đối chiếu văn bản & pháp lý. Hãy đọc các điểm khác biệt giữa bản cũ và bản mới dưới đây "
        "rồi tóm tắt ngắn gọn, chính xác bằng tiếng Việt: Điểm nào giữ nguyên, Điều/Mục nào sửa đổi hoặc bổ sung mới "
        "(kèm bảng đối chiếu 'Nội dung cũ -> Nội dung mới'). Tuyệt đối không bịa thêm thay đổi không có trong dữ liệu."
    )
    user_prompt = f"{deterministic_md}\n\nHãy tóm tắt các thay đổi quan trọng nhất theo bảng đối chiếu và gạch đầu dòng dễ hiểu:"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(OLLAMA_TIMEOUT, connect=10.0)) as client:
            resp = await client.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": chosen,
                    "messages": [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": False,
                    "keep_alive": "30m",
                    "options": {"num_ctx": 3072, "num_predict": 1200, "temperature": 0.25},
                },
            )
            if resp.status_code == 200:
                txt = resp.json().get("message", {}).get("content", "").strip()
                if txt:
                    return txt
    except Exception:
        pass
    return deterministic_md
