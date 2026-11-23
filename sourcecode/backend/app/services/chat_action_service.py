"""Thực thi hành động trực tiếp từ Chat: Tạo Quiz/Flashcards/Mindmap/Plan, Soạn thảo Văn bản & Đối chiếu Phiên bản."""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Optional

from app.config import DEFAULT_LLM_MODEL
from app.database import get_db_connection
from app.services.document_diff_service import compute_document_diff, summarize_diff_with_llm
from app.services.hardware_profile_service import get_active_profile_config
from app.services.llm_service import (
    _build_bounded_history_messages,
    _prepare_rag_prompts_and_citations,
    _resolve_model_for_chat,
    _stream_ollama_chat,
    check_ollama_status,
)
from app.services.study_service import (
    generate_ai_flashcards,
    generate_ai_mindmap,
    generate_ai_plan,
    generate_ai_quiz,
)

logger = logging.getLogger(__name__)


def _persist_study_artifact(
    workspace_id: str,
    document_id: Optional[str],
    artifact_type: str,
    title: str,
    data: Dict[str, Any],
) -> Optional[str]:
    """Lưu học liệu sinh ra từ Chat vào bảng study_artifacts để mở dùng ngay ở trang /study."""
    conn = get_db_connection()
    try:
        doc_id = document_id
        if doc_id:
            exists = conn.execute(
                "SELECT 1 FROM documents WHERE id = ? AND workspace_id = ?",
                (doc_id, workspace_id),
            ).fetchone()
            if not exists:
                doc_id = None
        artifact_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute(
            """
            INSERT INTO study_artifacts (id, workspace_id, document_id, artifact_type, title, data_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact_id,
                workspace_id,
                doc_id,
                artifact_type,
                title[:200],
                json.dumps(data, ensure_ascii=False),
                created_at,
            ),
        )
        conn.commit()
        return artifact_id
    except Exception:
        logger.exception("Không thể lưu study_artifact từ Chat")
        return None
    finally:
        conn.close()


def _extract_markdown_title(markdown_text: str, fallback: str) -> str:
    for line in (markdown_text or "").splitlines():
        clean = line.strip()
        if clean.startswith("#"):
            title = clean.lstrip("#").strip()
            if title:
                return title[:120]
    return fallback[:120]


async def _run_study_action(
    action_kind: str,
    params: Dict[str, Any],
    workspace_id: str,
    query: str,
    model_name: str,
    selected_document_id: Optional[str],
    document_ids: Optional[List[str]],
    collector: Optional[Dict[str, Any]],
) -> AsyncGenerator[str, None]:
    target_doc_id = selected_document_id or (document_ids[0] if document_ids and len(document_ids) == 1 else None)
    label_map = {
        "create_quiz": f"Đang tạo đề trắc nghiệm ({params.get('question_count', 5)} câu)...",
        "create_flashcards": f"Đang tạo bộ Flashcards ({params.get('count', 10)} thẻ)...",
        "create_mindmap": "Đang xây dựng Sơ đồ tư duy từ tài liệu...",
        "create_plan": f"Đang lập lộ trình học tập ({params.get('day_span', 7)} ngày)...",
    }
    yield f"data: {json.dumps({'stage': 'executing_action', 'stage_label': label_map.get(action_kind, 'Đang tạo học liệu...')}, ensure_ascii=False)}\n\n"

    action_payload: Dict[str, Any] = {}
    reply_md = ""

    if action_kind == "create_quiz":
        res = await generate_ai_quiz(
            workspace_id=workspace_id,
            document_id=target_doc_id,
            document_ids=document_ids,
            difficulty=str(params.get("difficulty") or "medium"),
            question_count=int(params.get("question_count") or 5),
            focus_prompt=str(params.get("focus_prompt") or query),
            model=model_name,
        )
        questions = res.get("questions") or []
        if res.get("error") or res.get("is_mock") or not questions:
            reply_md = f"Chưa thể tạo bài trắc nghiệm: **{res.get('error') or 'Không tìm thấy đủ nội dung tài liệu.'}**"
        else:
            title = str(res.get("title") or "Quiz từ Chat AI")
            doc_name = questions[0].get("citation", {}).get("documentName") if isinstance(questions[0].get("citation"), dict) else None
            artifact_id = _persist_study_artifact(
                workspace_id,
                target_doc_id,
                "quiz",
                title,
                {
                    "difficulty": str(params.get("difficulty") or "medium"),
                    "questions": questions,
                    "answers": {},
                    "submitted": False,
                    "attempts": [],
                    "focusPrompt": query[:120],
                    "documentName": doc_name,
                    "isMock": False,
                },
            )
            preview = [
                f"**Câu {idx + 1}:** {q.get('prompt', '')}"
                for idx, q in enumerate(questions[:3])
            ]
            reply_md = (
                f"Đã tạo thành công bộ đề **{title}** gồm **{len(questions)} câu hỏi trắc nghiệm** "
                "và lưu vào mục **Học liệu**.\n\n"
                + "\n".join(f"- {line}" for line in preview)
                + (f"\n- *...cùng {len(questions) - 3} câu hỏi khác.*" if len(questions) > 3 else "")
                + "\n\n---GỢI Ý TIẾP THEO---\n"
                "- Tạo thêm 10 câu hỏi mức độ khó hơn\n"
                "- Tạo bộ Flashcards ôn tập các ý vừa kiểm tra\n"
                "- Tóm tắt lý thuyết trọng tâm trước khi làm bài"
            )
            action_payload = {
                "action_type": "create_quiz",
                "artifact_id": artifact_id,
                "title": title,
                "study_tab": "quiz",
                "summary": f"{len(questions)} câu trắc nghiệm · Độ khó: {params.get('difficulty', 'medium')}",
                "preview_items": [q.get("prompt", "") for q in questions[:4]],
                "quiz": {
                    "id": artifact_id,
                    "title": title,
                    "difficulty": str(params.get("difficulty") or "medium"),
                    "documentId": target_doc_id,
                    "documentName": doc_name,
                    "questions": questions,
                },
            }

    elif action_kind == "create_flashcards":
        res = await generate_ai_flashcards(
            workspace_id=workspace_id,
            document_id=target_doc_id,
            document_ids=document_ids,
            count=int(params.get("count") or 10),
            focus_prompt=str(params.get("focus_prompt") or query),
            model=model_name,
            card_style=str(params.get("card_style") or "term_definition"),
        )
        cards = res.get("flashcards") or []
        if res.get("error") or res.get("is_mock") or not cards:
            reply_md = f"Chưa thể tạo Flashcards: **{res.get('error') or 'Không có đủ dữ liệu tài liệu.'}**"
        else:
            title = str(res.get("title") or "Bộ thẻ Flashcards AI")
            doc_name = cards[0].get("citation", {}).get("documentName") if isinstance(cards[0].get("citation"), dict) else None
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            artifact_id = _persist_study_artifact(
                workspace_id,
                target_doc_id,
                "flashcard_deck",
                title,
                {
                    "documentName": doc_name,
                    "cardStyle": res.get("card_style", "term_definition"),
                    "focusPrompt": query[:120],
                    "cards": cards,
                    "updatedAt": now_iso,
                    "lastStudiedAt": None,
                    "isMock": False,
                },
            )
            preview = [f"**{c.get('front', '')}** → {c.get('back', '')}" for c in cards[:4]]
            reply_md = (
                f"Đã tạo bộ **{title}** gồm **{len(cards)} thẻ ghi nhớ** và lưu vào **Học liệu**.\n\n"
                + "\n".join(f"- {line}" for line in preview)
                + (f"\n- *...cùng {len(cards) - 4} thẻ khác.*" if len(cards) > 4 else "")
                + "\n\n---GỢI Ý TIẾP THEO---\n"
                "- Tạo bài Quiz kiểm tra các thẻ vừa lập\n"
                "- Giải thích sâu hơn các thẻ khó\n"
                "- Mở rộng thêm thẻ ví dụ thực tế"
            )
            action_payload = {
                "action_type": "create_flashcards",
                "artifact_id": artifact_id,
                "title": title,
                "study_tab": "flashcards",
                "summary": f"{len(cards)} thẻ Flashcards · Kiểu: {res.get('card_style', 'term_definition')}",
                "preview_items": preview,
                "deck": {
                    "id": artifact_id,
                    "title": title,
                    "cardStyle": res.get("card_style", "term_definition"),
                    "documentId": target_doc_id,
                    "documentName": doc_name,
                    "cards": cards,
                },
            }

    elif action_kind == "create_mindmap":
        res = await generate_ai_mindmap(
            workspace_id=workspace_id,
            document_id=target_doc_id,
            document_ids=document_ids,
            focus_prompt=str(params.get("focus_prompt") or query),
            model=model_name,
        )
        root = res.get("root")
        if res.get("error") or res.get("is_mock") or not root:
            reply_md = f"Chưa thể tạo Sơ đồ tư duy: **{res.get('error') or 'Không có đủ dữ liệu.'}**"
        else:
            title = str(root.get("label") or "Sơ đồ tư duy AI")
            artifact_id = _persist_study_artifact(
                workspace_id,
                target_doc_id,
                "mindmap",
                title,
                {"root": root, "focusPrompt": query[:120], "isMock": False},
            )
            children_labels = [str(ch.get("label") or "") for ch in (root.get("children") or []) if isinstance(ch, dict)]
            reply_md = (
                f"Đã kiến tạo sơ đồ tư duy **{title}** với **{len(children_labels)} nhánh chính**.\n\n"
                + "\n".join(f"- **{lbl}**" for lbl in children_labels if lbl)
                + "\n\n---GỢI Ý TIẾP THEO---\n"
                "- Phân tích chi tiết nhánh đầu tiên\n"
                "- Tạo đề trắc nghiệm bao quát sơ đồ này\n"
                "- Xuất ghi chú tóm tắt từ sơ đồ"
            )
            action_payload = {
                "action_type": "create_mindmap",
                "artifact_id": artifact_id,
                "title": title,
                "study_tab": "mindmap",
                "summary": f"{len(children_labels)} nhánh kiến thức chính",
                "preview_items": children_labels[:5],
            }

    elif action_kind == "create_plan":
        res = await generate_ai_plan(
            workspace_id=workspace_id,
            document_id=target_doc_id,
            document_ids=document_ids,
            day_span=int(params.get("day_span") or 7),
            focus_prompt=str(params.get("focus_prompt") or query),
            model=model_name,
        )
        tasks = res.get("tasks") or []
        if res.get("error") or res.get("is_mock") or not tasks:
            reply_md = f"Chưa thể lập lộ trình học: **{res.get('error') or 'Không có đủ dữ liệu.'}**"
        else:
            title = f"Lộ trình học tập {params.get('day_span', 7)} ngày"
            artifact_id = _persist_study_artifact(
                workspace_id,
                target_doc_id,
                "plan",
                title,
                {"tasks": tasks, "focusPrompt": query[:120], "isMock": False},
            )
            preview = [f"**{t.get('due_date', '')}:** {t.get('title', '')}" for t in tasks[:5]]
            reply_md = (
                f"Đã lập **{title}** gồm **{len(tasks)} nhiệm vụ** theo sát tài liệu.\n\n"
                + "\n".join(f"- {line}" for line in preview)
                + "\n\n---GỢI Ý TIẾP THEO---\n"
                "- Tạo đề Quiz cho nhiệm vụ ngày đầu tiên\n"
                "- Rút ngắn lộ trình thành 3 ngày ôn cấp tốc\n"
                "- Tạo Flashcards cho các chủ đề trọng tâm"
            )
            action_payload = {
                "action_type": "create_plan",
                "artifact_id": artifact_id,
                "title": title,
                "study_tab": "plan",
                "summary": f"{len(tasks)} nhiệm vụ học tập có hạn hoàn thành",
                "preview_items": preview,
            }

    meta: Dict[str, Any] = {
        "citations": [],
        "model_used": model_name,
        "engine": "action_engine",
        "stage": "completed",
    }
    if action_payload:
        meta["action_result"] = action_payload
    yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'delta': reply_md}, ensure_ascii=False)}\n\n"
    if collector is not None:
        collector["full_answer"] = reply_md
        collector["citations"] = []
        collector["model_used"] = model_name
        collector["engine"] = "action_engine"
        if action_payload:
            collector["action_result"] = action_payload
    yield f"data: {json.dumps({'answer': reply_md, 'done': True, 'action_result': action_payload or None}, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


async def _run_compose_document(
    params: Dict[str, Any],
    workspace_id: str,
    query: str,
    model_name: str,
    context_chunks: List[Dict[str, Any]],
    history: Optional[List[Dict[str, str]]],
    collector: Optional[Dict[str, Any]],
    is_disconnected: Optional[Callable[[], Awaitable[bool]]],
) -> AsyncGenerator[str, None]:
    profile = get_active_profile_config()
    _, user_context_prompt, citations = _prepare_rag_prompts_and_citations(
        query,
        context_chunks,
        web_sources=None,
        max_context_tokens=int(profile.get("max_context_tokens") or 2200),
    )

    ollama_status = await check_ollama_status()
    chosen_model, model_available = _resolve_model_for_chat(model_name, ollama_status, None)
    engine_name = "action_composer" if (ollama_status["running"] and model_available) else "fallback_pipeline"

    yield f"data: {json.dumps({'stage': 'composing', 'stage_label': 'Đang soạn thảo văn bản chuẩn thể thức...', 'citations': citations, 'model_used': chosen_model, 'engine': engine_name}, ensure_ascii=False)}\n\n"

    system_prompt = (
        "Bạn là Chuyên gia Soạn thảo Văn bản & Báo cáo chuyên nghiệp. Dựa trên tài liệu nguồn được cung cấp (nếu có) "
        "và yêu cầu người dùng, hãy soạn một VĂN BẢN HOÀN CHỈNH bằng Markdown tiếng Việt sạch, mạch lạc, đúng thể thức hành chính/chuyên môn.\n"
        "YÊU CẦU ĐỊNH DẠNG:\n"
        "- Bắt đầu bằng tiêu đề chính `# <Tiêu đề văn bản>` rõ ràng.\n"
        "- Chia mục `## 1.`, `## 2.`..., dùng bảng Markdown nếu có số liệu/đối chiếu, gắn trích dẫn `[1]`, `[2]` cho thông tin lấy từ tài liệu nguồn.\n"
        "- Nội dung phải đầy đủ, dùng được ngay để xuất ra file Word (.docx) hoặc PDF (.pdf); không viết lan man lời chào mở đầu hay chú thích thừa."
    )
    compose_user_prompt = (
        f"{user_context_prompt}\n\n"
        if context_chunks
        else f"Yêu cầu soạn thảo văn bản:\n{query}\n\nHãy trình bày bản văn bản hoàn chỉnh từ dòng đầu tiên (`# Tiêu đề`):"
    )

    full_doc = ""
    if ollama_status["running"] and model_available:
        history_messages = _build_bounded_history_messages(history)
        local_collector: Dict[str, Any] = {}
        try:
            async for raw_evt in _stream_ollama_chat(
                payload={
                    "model": chosen_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        *history_messages,
                        {"role": "user", "content": compose_user_prompt},
                    ],
                    "stream": True,
                    "keep_alive": "30m",
                    "options": {
                        "num_ctx": int(profile.get("num_ctx") or 4096),
                        "num_predict": int(profile.get("num_predict") or 2048),
                        "temperature": 0.35,
                        "repeat_penalty": 1.12,
                    },
                },
                citations=citations,
                model_name=chosen_model,
                engine_name="action_composer",
                collector=local_collector,
                is_disconnected=is_disconnected,
            ):
                # Chặn [DONE] tạm để chèn action_result cho UI xuất file DOCX/PDF/MD
                if raw_evt.startswith("data: [DONE]"):
                    continue
                if raw_evt.startswith("data: "):
                    try:
                        parsed = json.loads(raw_evt[6:].strip())
                        if parsed.get("done"):
                            full_doc = str(parsed.get("answer") or local_collector.get("full_answer") or "")
                            continue
                    except Exception:
                        pass
                yield raw_evt
        except Exception:
            logger.exception("Document composer failed")

    if not full_doc:
        excerpt_lines = [f"## Nguồn tham khảo {c['ref_id']}: {c['document_name']}\n{c['snippet']}" for c in citations[:4]]
        full_doc = (
            f"# Văn bản dự thảo: {query[:80]}\n\n"
            + ("\n\n".join(excerpt_lines) if excerpt_lines else "*(Ollama hiện chưa bật nên chưa thể tự động biên soạn nội dung chi tiết.)*")
        )
        yield f"data: {json.dumps({'delta': full_doc}, ensure_ascii=False)}\n\n"

    clean_md = full_doc.split("---GỢI Ý TIẾP THEO---")[0].strip()
    doc_title = _extract_markdown_title(clean_md, fallback=query[:80] or "Văn bản AI soạn thảo")
    action_payload = {
        "action_type": "compose_document",
        "title": doc_title,
        "markdown": clean_md,
        "default_format": str(params.get("default_export_format") or "docx"),
        "export_formats": ["docx", "pdf", "md"],
        "summary": f"Sẵn sàng xuất ra Word (.docx), PDF hoặc Markdown ({len(clean_md)} ký tự)",
    }

    if collector is not None:
        collector["full_answer"] = full_doc
        collector["citations"] = citations
        collector["model_used"] = chosen_model
        collector["engine"] = engine_name
        collector["action_result"] = action_payload

    yield f"data: {json.dumps({'answer': full_doc, 'done': True, 'action_result': action_payload}, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


async def _run_version_diff_action(
    workspace_id: str,
    model_name: str,
    selected_document_id: Optional[str],
    document_ids: Optional[List[str]],
    collector: Optional[Dict[str, Any]],
) -> AsyncGenerator[str, None]:
    yield f"data: {json.dumps({'stage': 'comparing', 'stage_label': 'Đang đối chiếu sự thay đổi giữa các phiên bản tài liệu...'}, ensure_ascii=False)}\n\n"

    diff_res = compute_document_diff(
        workspace_id=workspace_id,
        new_document_id=selected_document_id,
        document_ids=document_ids,
    )
    summary_md = await summarize_diff_with_llm(diff_res, model=model_name)

    action_payload: Optional[Dict[str, Any]] = None
    if diff_res.get("ok"):
        old_doc = diff_res["old_document"]
        new_doc = diff_res["new_document"]
        action_payload = {
            "action_type": "version_diff",
            "title": f"Đối chiếu {old_doc['file_name']} (v{old_doc.get('version_number', 1)} -> v{new_doc.get('version_number', 1)})",
            "similarity_percent": diff_res.get("similarity_percent"),
            "total_changes": diff_res.get("total_changes"),
            "changes": diff_res.get("changes", [])[:8],
            "markdown": summary_md,
        }

    meta: Dict[str, Any] = {
        "citations": [],
        "model_used": model_name,
        "engine": "version_diff_engine",
        "stage": "completed",
    }
    if action_payload:
        meta["action_result"] = action_payload
    yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'delta': summary_md}, ensure_ascii=False)}\n\n"

    if collector is not None:
        collector["full_answer"] = summary_md
        collector["citations"] = []
        collector["model_used"] = model_name
        collector["engine"] = "version_diff_engine"
        if action_payload:
            collector["action_result"] = action_payload

    yield f"data: {json.dumps({'answer': summary_md, 'done': True, 'action_result': action_payload}, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


async def stream_chat_action(
    action_kind: str,
    params: Dict[str, Any],
    workspace_id: str,
    query: str,
    model_name: str = DEFAULT_LLM_MODEL,
    context_chunks: Optional[List[Dict[str, Any]]] = None,
    history: Optional[List[Dict[str, str]]] = None,
    selected_document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    collector: Optional[Dict[str, Any]] = None,
    is_disconnected: Optional[Callable[[], Awaitable[bool]]] = None,
) -> AsyncGenerator[str, None]:
    """Điều phối và thực thi hành động chat theo intent đã phân loại."""
    if action_kind in {"create_quiz", "create_flashcards", "create_mindmap", "create_plan"}:
        async for evt in _run_study_action(
            action_kind=action_kind,
            params=params,
            workspace_id=workspace_id,
            query=query,
            model_name=model_name,
            selected_document_id=selected_document_id,
            document_ids=document_ids,
            collector=collector,
        ):
            yield evt
        return

    if action_kind == "compose_document":
        async for evt in _run_compose_document(
            params=params,
            workspace_id=workspace_id,
            query=query,
            model_name=model_name,
            context_chunks=context_chunks or [],
            history=history,
            collector=collector,
            is_disconnected=is_disconnected,
        ):
            yield evt
        return

    if action_kind == "version_diff":
        async for evt in _run_version_diff_action(
            workspace_id=workspace_id,
            model_name=model_name,
            selected_document_id=selected_document_id,
            document_ids=document_ids,
            collector=collector,
        ):
            yield evt
