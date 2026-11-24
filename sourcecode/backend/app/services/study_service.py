"""
Service AI chuyên trách sinh nội dung học tập: Tóm tắt, Quiz trắc nghiệm, Flashcards và Mindmap.
Sử dụng LLM cục bộ (Ollama) kết hợp nội dung tài liệu thực tế trong kho tri thức.
"""
import json
import logging
import os
import re
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
    return False


def _is_low_value_header_chunk(text: str) -> bool:
    """Phát hiện các chunk chỉ chứa tiêu đề cột lặp lại hoặc mục lục số lượng dòng trong bảng Excel."""
    clean = (text or "").strip()
    if not clean:
        return True
    lower = clean.lower()
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
        clean_text = (c_text or "").strip()
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

    # 1. Nếu có yêu cầu trọng tâm thực sự, ưu tiên Positional (đầu/cuối) hoặc FTS5 (BM25 < 5ms) để tránh trễ CPU
    semantic_focus = (
        focus_prompt.strip()
        if focus_prompt and not _is_generic_focus_prompt(focus_prompt)
        else None
    )
    if semantic_focus:
        try:
            from app.services.retrieval_service import (
                detect_positional_intent,
                search_positional_chunks,
            )

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
                if t.lower() not in {"tóm", "tắt", "nội", "dung", "tài", "liệu", "trong", "của", "các", "những"}
            ]
            if tokens:
                fts_query = " OR ".join(f'"{t}"' for t in tokens[:8])
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
                            (workspace_id, *resolved_fts_ids, fts_query, max_chunks),
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

            if len(source_refs) >= min(5, max_chunks) or total_len >= int(max_chars * 0.65):
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
) -> str:
    budget = _get_study_runtime_budget()
    effective_num_predict = (
        min(num_predict, budget["num_predict"])
        if budget["profile_id"] == "eco" and num_predict > budget["num_predict"]
        else num_predict
    )
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "keep_alive": get_recommended_keep_alive(),
        "options": {
            "temperature": 0.4 if json_mode else 0.7,
            "top_p": 0.9,
            "num_predict": effective_num_predict,
            "num_ctx": budget["num_ctx"],
        },
    }
    if json_mode:
        payload["format"] = "json"

    timeout = httpx.Timeout(timeout_sec, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
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
        effective_context = "\n".join(sampled_lines)
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
    "cách đọc",
    "cach doc",
    "word",
    "reading",
}


def _make_citation_from_ref(ref: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "documentId": ref.get("documentId"),
        "documentName": ref.get("documentName") or "Tài liệu",
        "pageNumber": ref.get("pageNumber") or 1,
        "chunkIndex": ref.get("chunkIndex"),
        "snippet": ref.get("snippet") or "",
    }


def _extract_vocab_entries(source_refs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Trích xuất các mục từ vựng dạng bảng (STT | Từ | Cách đọc | Nghĩa) từ các đoạn nguồn."""
    entries: List[Dict[str, Any]] = []
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
            key = (term, reading, meaning.lower())
            if key in seen:
                continue
            seen.add(key)
            entries.append(
                {
                    "term": term,
                    "reading": reading,
                    "meaning": meaning,
                    "ref": ref,
                }
            )
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

    for key in ("answer", "correctAnswer", "correct_answer", "dap_an"):
        ans_val = raw_q.get(key)
        if ans_val is None:
            continue
        ans_str = str(ans_val).strip()
        if not ans_str:
            continue
        upper = ans_str.upper()
        if upper in letter_map and letter_map[upper] < len(options):
            return letter_map[upper]
        for idx, opt in enumerate(options):
            opt_clean = opt.strip()
            if opt_clean.lower() == ans_str.lower():
                return idx
        for idx, opt in enumerate(options):
            if ans_str.lower() in opt.lower() or opt.lower() in ans_str.lower():
                return idx

    return 0


def _extract_and_normalize_llm_questions(
    raw_res: str,
    source_refs: List[Dict[str, Any]],
    vocab_entries: List[Dict[str, Any]],
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
    seen_prompts: set[str] = set()

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
        if len(prompt_str) < 8:
            continue
        prompt_key = prompt_str.lower()
        if prompt_key in seen_prompts:
            continue

        # Loại bỏ các câu hỏi lạc đề về hệ thống RAG hoặc câu hỏi tiếng Anh hỏi số dòng bảng
        if re.search(r"(?i)\b(?:number of entries|provided data|hybrid rag|sparse retrieval|bm25|reciprocal rank)\b", prompt_str):
            if not any("hybrid rag" in (r.get("_search_text") or "") for r in source_refs):
                continue

        raw_opts = q.get("options") or q.get("choices") or q.get("answers") or q.get("lua_chon")
        if not isinstance(raw_opts, list) and all(k in q for k in ("A", "B", "C", "D")):
            raw_opts = [q["A"], q["B"], q["C"], q["D"]]
        if not isinstance(raw_opts, list):
            continue

        cleaned_opts: List[str] = []
        for opt in raw_opts:
            opt_s = re.sub(r"^[A-Da-d][\.\)\:\-]\s*", "", str(opt or "").strip()).strip()
            if opt_s and opt_s not in cleaned_opts:
                cleaned_opts.append(opt_s)
        options = cleaned_opts[:4]
        if len(options) < 2:
            continue

        ans_idx = _resolve_answer_index(q, options)

        if is_vocab_doc:
            # Với tài liệu bảng từ vựng, đảm bảo câu hỏi tiếng Việt và chứa từ/nghĩa thực trong tài liệu
            if not re.search(
                r"[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]",
                prompt_str.lower(),
            ):
                continue
            combined_q = f"{prompt_str} {options[ans_idx]}".lower()
            if not any(tok in combined_q for tok in vocab_known_tokens if len(tok) >= 1):
                continue

        seen_prompts.add(prompt_key)
        explanation = str(
            q.get("explanation")
            or q.get("giai_thich")
            or q.get("reason")
            or "Theo nội dung kiến thức trong tài liệu nguồn."
        ).strip()

        item_q: Dict[str, Any] = {
            "id": f"ai-q-{len(valid_questions) + 1}",
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
    """Chọn các phương án nhiễu khác biệt hoàn toàn với đáp án đúng từ tập dữ liệu tài liệu."""
    distractors: List[str] = []
    correct_norm = correct_val.strip().lower()
    n = len(pool)
    if n == 0:
        return distractors

    for step in range(n):
        cand = pool[(seed_offset + step * 7) % n].strip()
        cand_norm = cand.lower()
        if not cand or cand_norm == correct_norm:
            continue
        if any(d.lower() == cand_norm for d in distractors):
            continue
        distractors.append(cand)
        if len(distractors) >= needed:
            break
    return distractors


def _build_vocab_grounded_questions(
    vocab_entries: List[Dict[str, Any]],
    needed: int,
    existing_prompts: set[str],
    semantic_focus: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Tạo câu hỏi trắc nghiệm từ vựng chuẩn xác 100% từ bảng từ vựng trong tài liệu nguồn."""
    if len(vocab_entries) < 4 or needed <= 0:
        return []

    ordered_entries = list(vocab_entries)
    if semantic_focus:
        focus_l = semantic_focus.lower()
        prioritized = [
            e
            for e in ordered_entries
            if focus_l in e["term"].lower()
            or focus_l in e["reading"].lower()
            or focus_l in e["meaning"].lower()
        ]
        others = [e for e in ordered_entries if e not in prioritized]
        ordered_entries = prioritized + others

    # Lấy mẫu trải đều trên toàn bộ danh sách từ vựng để đề thi đa dạng
    total_entries = len(ordered_entries)
    sampled_entries: List[Dict[str, Any]] = []
    used_indices: set[int] = set()
    sample_target = min(total_entries, max(needed * 2, 12))
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
    readings_pool = list(
        dict.fromkeys([e["reading"] for e in ordered_entries if e["term"] != e["reading"] and e["reading"]])
    )

    generated: List[Dict[str, Any]] = []
    for idx, entry in enumerate(sampled_entries):
        if len(generated) >= needed:
            break
        term = entry["term"]
        reading = entry["reading"]
        meaning = entry["meaning"]
        ref = entry["ref"]
        doc_name = ref.get("documentName") or "Tài liệu từ vựng"
        page_num = ref.get("pageNumber") or 1

        has_distinct_reading = term != reading and len(readings_pool) >= 4
        q_mode = idx % (3 if has_distinct_reading else 2)

        if q_mode == 0:
            display_word = f"「{term}」 ({reading})" if term != reading else f"「{term}」"
            prompt = f"Trong tài liệu từ vựng, từ {display_word} có nghĩa tiếng Việt là gì?"
            correct_opt = meaning
            distractors = _pick_distinct_distractors(meanings_pool, correct_opt, 3, idx * 5 + 3)
            explanation = (
                f"Theo bảng từ vựng trong {doc_name} (Trang {page_num}), "
                f"từ {display_word} có nghĩa là \"{meaning}\"."
            )
        elif q_mode == 1:
            prompt = f"Từ vựng nào trong tài liệu mang nghĩa là \"{meaning}\"?"
            correct_opt = f"{term} ({reading})" if term != reading else term
            distractors = _pick_distinct_distractors(terms_pool, correct_opt, 3, idx * 5 + 5)
            explanation = (
                f"Theo {doc_name} (Trang {page_num}), nghĩa \"{meaning}\" "
                f"tương ứng với từ 「{term}」 ({reading})."
            )
        else:
            prompt = f"Cách đọc Hiragana đúng của từ 「{term}」 (nghĩa: \"{meaning}\") trong tài liệu là gì?"
            correct_opt = reading
            distractors = _pick_distinct_distractors(readings_pool, correct_opt, 3, idx * 5 + 7)
            explanation = (
                f"Theo bảng từ vựng trong {doc_name} (Trang {page_num}), "
                f"từ 「{term}」 (nghĩa: \"{meaning}\") được đọc là 「{reading}」."
            )

        if prompt.lower() in existing_prompts or len(distractors) < 3:
            continue

        ans_idx = (len(existing_prompts) + len(generated) * 3 + 1) % 4
        options = list(distractors[:3])
        options.insert(ans_idx, correct_opt)

        existing_prompts.add(prompt.lower())
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


def _extract_prose_statements(
    source_refs: List[Dict[str, Any]],
    min_len: int = 35,
    max_len: int = 190,
) -> List[tuple[str, Dict[str, Any]]]:
    """Tách các câu/mệnh đề có nghĩa từ các đoạn văn bản nguồn để làm câu hỏi hoặc flashcard."""
    statements: List[tuple[str, Dict[str, Any]]] = []
    seen_stmts: set[str] = set()

    for ref in source_refs:
        raw = str(ref.get("_raw_text") or ref.get("snippet") or "")
        for part in re.split(r"(?<=[\.\!\?\n])\s+", raw):
            clean = re.sub(r"\s+", " ", part).strip(" -•*\t\r\n")
            if min_len <= len(clean) <= max_len and clean.lower() not in seen_stmts:
                seen_stmts.add(clean.lower())
                statements.append((clean, ref))
    return statements


def _build_prose_grounded_questions(
    source_refs: List[Dict[str, Any]],
    needed: int,
    existing_prompts: set[str],
) -> List[Dict[str, Any]]:
    """Tạo câu hỏi trắc nghiệm bám sát các mệnh đề thực tế trong tài liệu văn bản khi cần bổ sung đủ số câu."""
    if not source_refs or needed <= 0:
        return []

    statements = _extract_prose_statements(source_refs)
    if len(statements) < 2:
        return []

    stmt_texts = [s[0] for s in statements]
    fallback_distractors = [
        "Thông tin này không được đề cập hoặc trái ngược với nội dung tài liệu nguồn.",
        "Nội dung chỉ áp dụng ngoài phạm vi tài liệu đang xét.",
        "Nhận định suy diễn không có bằng chứng trong các trang tài liệu.",
    ]

    generated: List[Dict[str, Any]] = []
    total_stmts = len(statements)
    for i in range(needed * 2):
        if len(generated) >= needed:
            break
        stmt, ref = statements[(i * max(1, total_stmts // max(1, needed))) % total_stmts]
        doc_name = ref.get("documentName") or "Tài liệu"
        page_num = ref.get("pageNumber") or 1

        prompt = (
            f"Theo nội dung tài liệu \"{doc_name}\" (Trang {page_num} - Đoạn #{(ref.get('chunkIndex') or 0) + 1}), "
            f"nhận định hay thông tin nào sau đây được nêu chính xác?"
        )
        if prompt.lower() in existing_prompts:
            prompt = (
                f"Trong tài liệu \"{doc_name}\" (Trang {page_num}), "
                f"chi tiết nào dưới đây phản ánh đúng nội dung bài học (câu #{len(generated) + 1})?"
            )
        if prompt.lower() in existing_prompts:
            continue

        other_pool = [
            f"Không đề cập trong đoạn này: {t[:120]}"
            for t in stmt_texts
            if t.lower() != stmt.lower()
        ] + fallback_distractors
        distractors = _pick_distinct_distractors(other_pool, stmt, 3, i * 3 + 1)
        if len(distractors) < 3:
            continue

        ans_idx = (len(existing_prompts) + len(generated) + 1) % 4
        options = list(distractors[:3])
        options.insert(ans_idx, stmt)

        existing_prompts.add(prompt.lower())
        generated.append(
            {
                "id": f"ai-q-doc-{len(generated) + 1}",
                "prompt": prompt,
                "options": options,
                "answerIndex": ans_idx,
                "explanation": f"Theo nội dung gốc tại {doc_name} (Trang {page_num}): \"{stmt}\".",
                "citation": _make_citation_from_ref(ref),
            }
        )

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


async def generate_ai_quiz(
    workspace_id: str,
    document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    difficulty: str = "medium",
    question_count: int = 5,
    focus_prompt: Optional[str] = None,
    model: str = DEFAULT_LLM_MODEL,
) -> Dict[str, Any]:
    """
    Sinh danh sách câu hỏi trắc nghiệm kiểm tra kiến thức dựa trên nội dung tài liệu kèm citation.
    Đảm bảo trả về đúng số lượng câu hỏi (question_count) và bám sát 100% phạm vi tài liệu đã chọn.
    """
    count = min(max(question_count, 1), 20)
    max_chunks = min(20, max(12, count + 4))
    max_chars = 4800
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
    vocab_entries = _extract_vocab_entries(source_refs)

    # Nếu tài liệu là bảng từ vựng (Excel/CSV), định dạng lại ngữ cảnh gọn rõ để LLM đọc nhanh và chính xác
    llm_context = context
    if len(vocab_entries) >= 8:
        sampled_vocab_lines: List[str] = []
        step = max(1, len(vocab_entries) // 12)
        for idx in range(0, len(vocab_entries), step):
            ve = vocab_entries[idx]
            ref_idx = ve["ref"].get("ref_index", 1)
            sampled_vocab_lines.append(
                f"[Nguồn {ref_idx}] Từ vựng: {ve['term']} | Cách đọc: {ve['reading']} | Nghĩa tiếng Việt: {ve['meaning']}"
            )
            if len(sampled_vocab_lines) >= 12:
                break
        llm_context = "\n".join(sampled_vocab_lines)
        llm_ask_count = min(count, 3)
        llm_timeout = min(OLLAMA_TIMEOUT, 25.0)
        predict_tokens = 550
    else:
        llm_context = context[:2800]
        llm_ask_count = min(count, 6)
        llm_timeout = min(OLLAMA_TIMEOUT, 60.0)
        predict_tokens = min(1400, max(650, llm_ask_count * 180))

    system_prompt = (
        "Bạn là Chuyên gia Khảo thí và Thiết kế đề thi giáo dục. "
        "Nhiệm vụ của bạn là đọc kỹ các đoạn nguồn [Nguồn 1], [Nguồn 2]... và soạn câu hỏi trắc nghiệm "
        "(Multiple Choice Questions) bằng tiếng Việt kiểm tra trực tiếp kiến thức/từ vựng có trong tài liệu.\n"
        "TUYỆT ĐỐI KHÔNG hỏi các câu ngoài phạm vi tài liệu nguồn, KHÔNG hỏi bằng tiếng Anh.\n\n"
        "BẠN PHẢI TRẢ VỀ DUY NHẤT MỘT JSON OBJECT CÓ DẠNG:\n"
        "{\n"
        '  "questions": [\n'
        "    {\n"
        '      "prompt": "Nội dung câu hỏi trắc nghiệm bằng tiếng Việt?",\n'
        '      "options": ["Lựa chọn A", "Lựa chọn B", "Lựa chọn C", "Lựa chọn D"],\n'
        '      "answerIndex": 0,\n'
        '      "explanation": "Giải thích chi tiết vì sao đáp án này đúng dựa trên tài liệu",\n'
        '      "sourceIndex": 1\n'
        "    }\n"
        "  ]\n"
        "}\n"
        f"LƯU Ý: Mỗi câu phải có đúng 4 lựa chọn trong mảng 'options', 'answerIndex' là số nguyên từ 0 đến 3, "
        f"'sourceIndex' là số thứ tự của [Nguồn N]. Hãy tạo đúng {llm_ask_count} câu hỏi."
    )

    user_prompt = f"TÀI LIỆU NGUỒN:\n{llm_context}\n\n"
    if semantic_focus:
        user_prompt += f"TRỌNG TÂM KIẾN THỨC CẦN HỎI: {semantic_focus}\n\n"
    user_prompt += (
        f"Hãy tạo đúng {llm_ask_count} câu hỏi trắc nghiệm tiếng Việt (độ khó {difficulty}) "
        'bám sát nội dung TÀI LIỆU NGUỒN ở trên. Trả về JSON object có key "questions" chứa các phần tử '
        'gồm {"prompt", "options" (4 phương án), "answerIndex" (0-3), "explanation", "sourceIndex"}:'
    )

    valid_questions: List[Dict[str, Any]] = []
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
        valid_questions = _extract_and_normalize_llm_questions(raw_res, source_refs, vocab_entries)
    except Exception as exc:
        llm_error = exc
        logger.warning("LLM sinh Quiz gặp lỗi hoặc quá thời gian, kiểm tra bổ sung từ tài liệu: %s", exc)

    # Bổ sung câu hỏi trực tiếp từ tài liệu nguồn nếu LLM trả về thiếu số lượng (vd: chọn 10 câu nhưng LLM chỉ sinh 5 câu)
    needed = count - len(valid_questions)
    if needed > 0:
        existing_prompts = {q["prompt"].lower() for q in valid_questions}
        if len(vocab_entries) >= 4:
            vocab_topup = _build_vocab_grounded_questions(
                vocab_entries,
                needed=needed,
                existing_prompts=existing_prompts,
                semantic_focus=semantic_focus,
            )
            valid_questions.extend(vocab_topup)

        needed = count - len(valid_questions)
        total_raw_chars = sum(len(str(r.get("_raw_text") or "")) for r in source_refs)
        if needed > 0 and (total_raw_chars >= 160 or not valid_questions):
            prose_topup = _build_prose_grounded_questions(
                source_refs,
                needed=needed,
                existing_prompts=existing_prompts,
            )
            valid_questions.extend(prose_topup)

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
    title_topic = clean_focus[:48] if clean_focus else primary_doc_name[:48]
    return {
        "title": f"Quiz · {title_topic}",
        "questions": final_questions,
        "difficulty": difficulty,
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
