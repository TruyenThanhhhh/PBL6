"""Dịch vụ Nghiên cứu Sâu đa tài liệu (Multi-Doc Evidence Synthesis + Streaming + SQLite Persistence)."""
import json
import logging
import uuid
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Optional

import httpx
from starlette.concurrency import run_in_threadpool

from app.config import DEFAULT_LLM_MODEL, OLLAMA_BASE_URL, OLLAMA_TIMEOUT
from app.database import get_db_connection
from app.services.hardware_profile_service import get_active_profile_config
from app.services.llm_service import check_ollama_status, resolve_available_chat_model
from app.services.retrieval_service import search_relevant_chunks
from app.services.web_search_service import search_web

logger = logging.getLogger(__name__)


def _parse_json_list(raw: Optional[str]) -> List[Any]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _serialize_project_row(row: Any) -> Dict[str, Any]:
    doc_ids = [str(item) for item in _parse_json_list(row["selected_doc_ids"]) if item]
    citations = _parse_json_list(row["citations_json"] if "citations_json" in row.keys() else None)
    return {
        "id": row["id"],
        "workspaceId": row["workspace_id"],
        "notebookId": row["notebook_id"],
        "title": row["title"],
        "question": row["question"],
        "documentIds": doc_ids,
        "allowWeb": bool(row["allow_web"]) if "allow_web" in row.keys() else False,
        "mode": row["mode"] if "mode" in row.keys() and row["mode"] else "local",
        "status": row["status"] or "completed",
        "step": int(row["step"] or (5 if row["status"] == "completed" else 0)) if "step" in row.keys() else 5,
        "report": row["report_markdown"] or "",
        "citations": citations,
        "isMock": False,
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def list_workspace_research_projects(workspace_id: str, user_id: str) -> Optional[List[Dict[str, Any]]]:
    conn = get_db_connection()
    try:
        owned = conn.execute(
            "SELECT 1 FROM workspaces WHERE id = ? AND owner_user_id = ?",
            (workspace_id, user_id),
        ).fetchone()
        if not owned:
            return None
        rows = conn.execute(
            """
            SELECT r.*
            FROM research_projects r
            WHERE r.workspace_id = ?
            ORDER BY COALESCE(r.updated_at, r.created_at) DESC
            """,
            (workspace_id,),
        ).fetchall()
        return [_serialize_project_row(r) for r in rows]
    finally:
        conn.close()


def update_research_project_record(
    project_id: str,
    user_id: str,
    title: Optional[str] = None,
    report: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        row = conn.execute(
            """
            SELECT r.*
            FROM research_projects r
            JOIN workspaces w ON w.id = r.workspace_id
            WHERE r.id = ? AND w.owner_user_id = ?
            """,
            (project_id, user_id),
        ).fetchone()
        if not row:
            return None
        new_title = title.strip() if title is not None and title.strip() else row["title"]
        new_report = report if report is not None else row["report_markdown"]
        conn.execute(
            """
            UPDATE research_projects
            SET title = ?, report_markdown = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_title, new_report, project_id),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM research_projects WHERE id = ?", (project_id,)).fetchone()
        return _serialize_project_row(updated) if updated else None
    finally:
        conn.close()


def delete_research_project_record(project_id: str, user_id: str) -> bool:
    conn = get_db_connection()
    try:
        row = conn.execute(
            """
            SELECT r.id
            FROM research_projects r
            JOIN workspaces w ON w.id = r.workspace_id
            WHERE r.id = ? AND w.owner_user_id = ?
            """,
            (project_id, user_id),
        ).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM research_projects WHERE id = ?", (project_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def _resolve_research_runtime_budget() -> Dict[str, Any]:
    profile = get_active_profile_config()
    profile_id = str(profile.get("id") or "balanced").lower()
    if profile_id == "eco":
        return {
            "profile_id": "eco",
            "max_docs": 4,
            "per_doc_k": 2,
            "cross_k": 3,
            "context_char_budget": 2400,
            "num_ctx": int(profile.get("num_ctx") or 2048),
            "num_predict": min(int(profile.get("num_predict") or 1024), 950),
        }
    if profile_id == "performance":
        return {
            "profile_id": "performance",
            "max_docs": 10,
            "per_doc_k": 3,
            "cross_k": 6,
            "context_char_budget": 6500,
            "num_ctx": int(profile.get("num_ctx") or 6144),
            "num_predict": min(int(profile.get("num_predict") or 2560), 2200),
        }
    return {
        "profile_id": "balanced",
        "max_docs": 6,
        "per_doc_k": 2,
        "cross_k": 4,
        "context_char_budget": 4400,
        "num_ctx": int(profile.get("num_ctx") or 4096),
        "num_predict": min(int(profile.get("num_predict") or 2048), 1500),
    }


def _select_target_documents(
    workspace_id: str,
    notebook_id: Optional[str],
    requested_doc_ids: Optional[List[str]],
    max_docs: int,
) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, file_name, file_type, total_pages, total_chunks, notebook_id, effective_date, version_number
            FROM documents
            WHERE workspace_id = ? AND COALESCE(is_latest, 1) = 1
            ORDER BY created_at DESC
            """,
            (workspace_id,),
        ).fetchall()
        docs = [dict(r) for r in rows]
    finally:
        conn.close()

    if requested_doc_ids:
        by_id = {d["id"]: d for d in docs}
        chosen = [by_id[doc_id] for doc_id in requested_doc_ids if doc_id in by_id]
        return chosen[:max_docs]
    if notebook_id:
        nb_docs = [d for d in docs if d.get("notebook_id") == notebook_id]
        if nb_docs:
            return nb_docs[:max_docs]
    return docs[:max_docs]


def _collect_local_research_evidence(
    workspace_id: str,
    question: str,
    target_docs: List[Dict[str, Any]],
    per_doc_k: int,
    cross_k: int,
) -> List[Dict[str, Any]]:
    seen_chunks = set()
    collected: List[Dict[str, Any]] = []

    for doc in target_docs:
        hits = search_relevant_chunks(
            workspace_id=workspace_id,
            query=question,
            top_k=per_doc_k,
            document_id=doc["id"],
        )
        for ch in hits:
            key = (ch.get("document_id"), ch.get("chunk_index"), ch.get("chunk_id"))
            if key not in seen_chunks:
                seen_chunks.add(key)
                collected.append(ch)

    target_doc_ids = [d["id"] for d in target_docs] if target_docs else None
    cross_hits = search_relevant_chunks(
        workspace_id=workspace_id,
        query=question,
        top_k=cross_k,
        document_ids=target_doc_ids,
    )
    for ch in cross_hits:
        key = (ch.get("document_id"), ch.get("chunk_index"), ch.get("chunk_id"))
        if key not in seen_chunks:
            seen_chunks.add(key)
            collected.append(ch)

    return collected


def _build_research_context_and_citations(
    local_chunks: List[Dict[str, Any]],
    web_sources: List[Dict[str, Any]],
    target_docs: List[Dict[str, Any]],
    char_budget: int,
) -> tuple[str, List[Dict[str, Any]]]:
    citations: List[Dict[str, Any]] = []
    context_lines: List[str] = []
    used_chars = 0

    for idx, ch in enumerate(local_chunks, start=1):
        doc_name = ch.get("document_name") or "Tài liệu"
        page_num = ch.get("page_number") or 1
        snippet = str(ch.get("content") or "").strip()
        citations.append({
            "refId": idx,
            "documentId": ch.get("document_id"),
            "documentName": doc_name,
            "pageNumber": page_num,
            "pageLabel": f"Trang {page_num}",
            "chunkIndex": ch.get("chunk_index"),
            "snippet": snippet[:280],
            "sourceKind": "local",
        })
        block = f"[{idx}] {doc_name} (Trang {page_num}):\n{snippet[:850]}"
        if used_chars + len(block) <= char_budget or not context_lines:
            context_lines.append(block)
            used_chars += len(block) + 2

    start_web_ref = len(citations) + 1
    for offset, w in enumerate(web_sources[:3]):
        ref_id = start_web_ref + offset
        title = str(w.get("title") or w.get("domain") or "Nguồn Web")
        url = str(w.get("url") or "")
        snippet = str(w.get("snippet") or w.get("content") or "").strip()
        citations.append({
            "refId": ref_id,
            "documentId": None,
            "documentName": title,
            "pageNumber": None,
            "pageLabel": w.get("domain") or "Web",
            "chunkIndex": None,
            "snippet": snippet[:280],
            "sourceKind": "web",
            "url": url,
        })
        block = f"[{ref_id}] Nguồn Web - {title} ({url}):\n{snippet[:650]}"
        if used_chars + len(block) <= char_budget:
            context_lines.append(block)
            used_chars += len(block) + 2

    # Nếu chưa truy xuất được chunk nào nhưng có tài liệu được chọn, vẫn đưa danh mục nguồn
    if not citations and target_docs:
        for idx, doc in enumerate(target_docs, start=1):
            citations.append({
                "refId": idx,
                "documentId": doc["id"],
                "documentName": doc["file_name"],
                "pageNumber": 1,
                "pageLabel": "Trang 1",
                "chunkIndex": 0,
                "snippet": f"{str(doc['file_type']).upper()} · {doc.get('total_chunks', 0)} đoạn",
                "sourceKind": "local",
            })

    return "\n\n".join(context_lines), citations


def _build_offline_evidence_report(
    question: str,
    target_docs: List[Dict[str, Any]],
    citations: List[Dict[str, Any]],
    mode: str,
    allow_web: bool,
    reason: str,
) -> str:
    local_cites = [c for c in citations if c.get("sourceKind") == "local"]
    web_cites = [c for c in citations if c.get("sourceKind") == "web"]

    findings_lines = []
    for c in local_cites[:6]:
        clean_snip = str(c.get("snippet") or "").replace("\n", " ").strip()[:240]
        findings_lines.append(f"- **{c['documentName']}** (Trang {c.get('pageNumber') or 1}): \"{clean_snip}...\" [{c['refId']}]")
    for c in web_cites[:3]:
        clean_snip = str(c.get("snippet") or "").replace("\n", " ").strip()[:200]
        findings_lines.append(f"- **Nguồn Web ({c['documentName']})**: {clean_snip} [{c['refId']}]")
    if not findings_lines:
        findings_lines.append("- Chưa tìm thấy đoạn trích khớp trực tiếp với câu hỏi trong các tài liệu đã chọn.")

    table_rows = []
    for idx, doc in enumerate(target_docs, start=1):
        matching_cites = [c for c in local_cites if c.get("documentId") == doc["id"]]
        preview = (
            str(matching_cites[0].get("snippet") or "").replace("\n", " ").strip()[:110]
            if matching_cites
            else "Chưa có đoạn khớp trực tiếp"
        )
        ref_tag = f"[{matching_cites[0]['refId']}]" if matching_cites else ""
        table_rows.append(
            f"| `{doc['file_name']}` | {len(matching_cites)} đoạn liên quan | {preview} {ref_tag} |"
        )
    if not table_rows:
        table_rows.append("| Chưa chọn tài liệu | 0 | Cần tải lên hoặc chọn tài liệu nguồn |")

    ref_lines = [
        f"{c['refId']}. [{c['refId']}] **{c['documentName']}**"
        + (f" ({c['pageLabel']})" if c.get("pageLabel") else "")
        + (f" — {c['url']}" if c.get("url") else "")
        for c in citations
    ] or ["1. Chưa có trích dẫn được thu thập."]

    return (
        f"## 1. Executive Summary\n\n"
        f"Đã thu thập **{len(local_cites)} đoạn bằng chứng nội bộ** từ **{len(target_docs)} tài liệu** "
        f"{'và ' + str(len(web_cites)) + ' nguồn Internet ' if web_cites else ''}"
        f"cho câu hỏi nghiên cứu.\n\n"
        f"> **Lưu ý hệ thống:** {reason} Báo cáo dưới đây tổng hợp trực tiếp các đoạn bằng chứng thực tế vừa truy xuất được.\n\n"
        f"## 2. Research Question\n\n"
        f"**Câu hỏi:** {question}\n\n"
        f"- **Chế độ truy xuất:** `{mode.upper()}` · **Web Search:** {'Bật' if allow_web else 'Tắt'}\n\n"
        f"## 3. Key Findings\n\n"
        + "\n".join(findings_lines)
        + "\n\n## 4. Comparison\n\n"
        "| Tài liệu nguồn | Bằng chứng khớp | Trích đoạn tiêu biểu |\n"
        "| :--- | :--- | :--- |\n"
        + "\n".join(table_rows)
        + "\n\n## 5. Contradictions\n\n"
        "- Cần chạy tổng hợp qua model Ollama để AI phân tích sâu điểm mâu thuẫn ngữ nghĩa giữa các đoạn trích.\n\n"
        "## 6. Research Gaps\n\n"
        "- Nếu dữ liệu thực nghiệm còn thiếu ở một khía cạnh, hãy bật Web Search hoặc tải thêm tài liệu chuyên sâu vào Workspace.\n\n"
        "## 7. Conclusion\n\n"
        "Các bằng chứng liên quan đã được trích xuất và gắn mã tham chiếu `[1]..[n]` sẵn sàng để đối chiếu trực tiếp.\n\n"
        "## 8. References\n\n"
        + "\n".join(ref_lines)
    )


def _upsert_project_start(
    project_id: str,
    workspace_id: str,
    notebook_id: Optional[str],
    title: str,
    question: str,
    document_ids: List[str],
    allow_web: bool,
    mode: str,
) -> Dict[str, Any]:
    conn = get_db_connection()
    try:
        exists = conn.execute("SELECT id FROM research_projects WHERE id = ?", (project_id,)).fetchone()
        doc_ids_json = json.dumps(document_ids, ensure_ascii=False)
        if exists:
            conn.execute(
                """
                UPDATE research_projects
                SET notebook_id = ?, title = ?, question = ?, status = 'running',
                    selected_doc_ids = ?, mode = ?, allow_web = ?, step = 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (notebook_id, title, question, doc_ids_json, mode, int(allow_web), project_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO research_projects (
                    id, workspace_id, notebook_id, title, question, status,
                    selected_doc_ids, report_markdown, mode, allow_web, step
                )
                VALUES (?, ?, ?, ?, ?, 'running', ?, '', ?, ?, 1)
                """,
                (project_id, workspace_id, notebook_id, title, question, doc_ids_json, mode, int(allow_web)),
            )
        conn.commit()
        row = conn.execute("SELECT * FROM research_projects WHERE id = ?", (project_id,)).fetchone()
        return _serialize_project_row(row)
    finally:
        conn.close()


def _finalize_project_record(
    project_id: str,
    report_markdown: str,
    citations: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        conn.execute(
            """
            UPDATE research_projects
            SET status = 'completed', step = 5, report_markdown = ?, citations_json = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (report_markdown, json.dumps(citations, ensure_ascii=False), project_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM research_projects WHERE id = ?", (project_id,)).fetchone()
        return _serialize_project_row(row) if row else None
    finally:
        conn.close()


async def stream_research_synthesis(
    workspace_id: str,
    question: str,
    title: Optional[str] = None,
    project_id: Optional[str] = None,
    notebook_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    allow_web: bool = False,
    mode: str = "local",
    model: Optional[str] = None,
    collector: Optional[Dict[str, Any]] = None,
    is_disconnected: Optional[Callable[[], Awaitable[bool]]] = None,
) -> AsyncGenerator[str, None]:
    """Pipeline 5 bước Nghiên cứu Sâu đa tài liệu kèm SSE streaming theo thời gian thực."""
    clean_q = (question or "").strip()
    proj_id = (project_id or "").strip() or f"rs_{uuid.uuid4().hex[:12]}"
    proj_title = (title or "").strip() or clean_q[:64]
    norm_mode = (mode or "local").strip().lower()
    use_web = bool(allow_web) or norm_mode in {"web", "hybrid"}
    use_local = norm_mode != "web"
    budget = _resolve_research_runtime_budget()

    # Bước 1: Xác định câu hỏi & phạm vi nguồn
    target_docs = await run_in_threadpool(
        _select_target_documents,
        workspace_id,
        notebook_id,
        document_ids,
        int(budget["max_docs"]),
    )
    resolved_doc_ids = [d["id"] for d in target_docs]
    initial_project = await run_in_threadpool(
        _upsert_project_start,
        proj_id,
        workspace_id,
        notebook_id,
        proj_title,
        clean_q,
        resolved_doc_ids,
        use_web,
        norm_mode,
    )
    yield f"data: {json.dumps({'type': 'meta', 'project': initial_project}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'type': 'step', 'step': 1, 'label': 'Xác định câu hỏi', 'detail': clean_q[:120]}, ensure_ascii=False)}\n\n"

    # Bước 2: Thu thập nguồn
    yield f"data: {json.dumps({'type': 'step', 'step': 2, 'label': 'Thu thập nguồn', 'detail': f'{len(target_docs)} tài liệu nội bộ'}, ensure_ascii=False)}\n\n"

    if is_disconnected and await is_disconnected():
        return

    # Bước 3: Truy xuất bằng chứng
    yield f"data: {json.dumps({'type': 'step', 'step': 3, 'label': 'Truy xuất bằng chứng', 'detail': 'Đang đối chiếu Hybrid RAG & nguồn ngoài...'}, ensure_ascii=False)}\n\n"
    local_chunks: List[Dict[str, Any]] = []
    if use_local and target_docs:
        local_chunks = await run_in_threadpool(
            _collect_local_research_evidence,
            workspace_id,
            clean_q,
            target_docs,
            int(budget["per_doc_k"]),
            int(budget["cross_k"]),
        )

    web_sources: List[Dict[str, Any]] = []
    if use_web:
        try:
            web_sources = await search_web(clean_q)
        except Exception:
            logger.debug("Research web search fallback failed", exc_info=True)
            web_sources = []

    evidence_context, citations = _build_research_context_and_citations(
        local_chunks,
        web_sources,
        target_docs,
        int(budget["context_char_budget"]),
    )
    yield f"data: {json.dumps({'type': 'citations', 'citations': citations}, ensure_ascii=False)}\n\n"

    if is_disconnected and await is_disconnected():
        return

    # Bước 4: Tổng hợp đa tài liệu qua LLM
    yield f"data: {json.dumps({'type': 'step', 'step': 4, 'label': 'Tổng hợp', 'detail': 'Đang đối chiếu luận điểm, điểm đồng thuận & mâu thuẫn...'}, ensure_ascii=False)}\n\n"

    ollama_status = await check_ollama_status()
    chosen_model = (
        resolve_available_chat_model(model or DEFAULT_LLM_MODEL, ollama_status.get("available_models") or [])
        if ollama_status.get("running")
        else None
    )

    report_md = ""
    if ollama_status.get("running") and chosen_model and evidence_context.strip():
        doc_overview = "\n".join(
            f"- {d['file_name']} ({str(d['file_type']).upper()}, {d.get('total_pages', 1)} trang)"
            for d in target_docs
        ) or "- Nguồn Internet"

        system_prompt = (
            "Bạn là Trợ lý Nghiên cứu Học thuật AI. Hãy tổng hợp báo cáo đối chiếu đa nguồn hoàn toàn bằng tiếng Việt "
            "dựa STRICTLY trên phần BẰNG CHỨNG được cung cấp (không bịa thêm số liệu ngoài bằng chứng).\n"
            "BẮT BUỘC giữ đúng 8 tiêu đề cấp 2 sau theo đúng thứ tự:\n"
            "## 1. Executive Summary\n"
            "## 2. Research Question\n"
            "## 3. Key Findings\n"
            "## 4. Comparison\n"
            "## 5. Contradictions\n"
            "## 6. Research Gaps\n"
            "## 7. Conclusion\n"
            "## 8. References\n\n"
            "Yêu cầu:\n"
            "- Gắn mã trích dẫn dạng [1], [2]... tương ứng đúng nguồn trong bằng chứng.\n"
            "- Mục ## 4. Comparison phải có bảng Markdown so sánh giữa các tài liệu nguồn.\n"
            "- Mục ## 5. Contradictions chỉ rõ điểm khác biệt, mâu thuẫn hoặc điều kiện loại trừ (nếu không mâu thuẫn ghi rõ).\n"
            "- Mục ## 6. Research Gaps chỉ rõ thông tin còn thiếu trong bộ tài liệu."
        )
        user_prompt = (
            f"CÂU HỎI NGHIÊN CỨU: {clean_q}\n\n"
            f"DANH SÁCH NGUỒN ({len(target_docs)} tài liệu):\n{doc_overview}\n\n"
            f"BẰNG CHỨNG TRÍCH XUẤT:\n{evidence_context}\n\n"
            "Hãy viết báo cáo nghiên cứu hoàn chỉnh theo đúng cấu trúc 8 mục ở trên:"
        )

        yield f"data: {json.dumps({'type': 'step', 'step': 5, 'label': 'Tạo báo cáo', 'detail': f'Đang viết báo cáo bằng {chosen_model}...'}, ensure_ascii=False)}\n\n"

        payload = {
            "model": chosen_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": True,
            "keep_alive": "30m",
            "options": {
                "num_ctx": int(budget["num_ctx"]),
                "num_predict": int(budget["num_predict"]),
                "temperature": 0.35,
                "repeat_penalty": 1.12,
            },
        }
        collected_tokens: List[str] = []
        try:
            timeout = httpx.Timeout(OLLAMA_TIMEOUT, connect=10.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", f"{OLLAMA_BASE_URL}/api/chat", json=payload) as resp:
                    if resp.status_code >= 400:
                        raise RuntimeError(f"Ollama HTTP {resp.status_code}")
                    async for raw_line in resp.aiter_lines():
                        if is_disconnected and await is_disconnected():
                            return
                        if not raw_line:
                            continue
                        try:
                            chunk_data = json.loads(raw_line)
                        except Exception:
                            continue
                        token = str(chunk_data.get("message", {}).get("content") or "")
                        if token:
                            collected_tokens.append(token)
                            yield f"data: {json.dumps({'type': 'delta', 'content': token}, ensure_ascii=False)}\n\n"
                        if chunk_data.get("done"):
                            break
            report_md = "".join(collected_tokens).strip()
        except Exception:
            logger.exception("Research LLM streaming failed, falling back to structured evidence summary")
            report_md = ""

    if not report_md:
        yield f"data: {json.dumps({'type': 'step', 'step': 5, 'label': 'Tạo báo cáo', 'detail': 'Đang hoàn thiện báo cáo từ bằng chứng đã truy xuất...'}, ensure_ascii=False)}\n\n"
        fallback_reason = (
            "Không tìm thấy đoạn văn bản khớp trong phạm vi tài liệu."
            if not evidence_context.strip()
            else (
                "Ollama chưa sẵn sàng nên AI chưa viết phần diễn giải tự do."
                if not chosen_model
                else "Quá trình gọi model AI cục bộ bị gián đoạn."
            )
        )
        report_md = _build_offline_evidence_report(
            clean_q, target_docs, citations, norm_mode, use_web, fallback_reason
        )
        yield f"data: {json.dumps({'type': 'delta', 'content': report_md}, ensure_ascii=False)}\n\n"

    final_project = await run_in_threadpool(
        _finalize_project_record,
        proj_id,
        report_md,
        citations,
    )
    if collector is not None and final_project is not None:
        collector["project"] = final_project

    yield f"data: {json.dumps({'type': 'done', 'project': final_project}, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


async def synthesize_research_project_sync(
    workspace_id: str,
    question: str,
    title: Optional[str] = None,
    project_id: Optional[str] = None,
    notebook_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    allow_web: bool = False,
    mode: str = "local",
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Thực thi pipeline nghiên cứu sâu đồng bộ và trả về object ResearchProject đã lưu."""
    collector: Dict[str, Any] = {}
    async for _ in stream_research_synthesis(
        workspace_id=workspace_id,
        question=question,
        title=title,
        project_id=project_id,
        notebook_id=notebook_id,
        document_ids=document_ids,
        allow_web=allow_web,
        mode=mode,
        model=model,
        collector=collector,
    ):
        pass
    if "project" not in collector:
        raise RuntimeError("Không thể tổng hợp dự án nghiên cứu")
    return collector["project"]
