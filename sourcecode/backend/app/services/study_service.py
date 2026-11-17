"""
Service AI chuyên trách sinh nội dung học tập: Tóm tắt, Quiz trắc nghiệm, Flashcards và Mindmap.
Sử dụng LLM cục bộ (Ollama) kết hợp nội dung tài liệu thực tế trong kho tri thức.
"""
import json
import logging
import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4
import httpx

from app.config import DEFAULT_LLM_MODEL, OLLAMA_BASE_URL, OLLAMA_TIMEOUT
from app.database import get_db_connection
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
        "SELECT DISTINCT document_id FROM document_chunks WHERE workspace_id = ? ORDER BY document_id",
        (workspace_id,),
    ).fetchall()
    return [row["document_id"] for row in rows]


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
        if not clean_text:
            return True
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
            }
        )
        return total_len < max_chars

    # 1. Nếu có yêu cầu trọng tâm, sử dụng Hybrid Search
    if focus_prompt and focus_prompt.strip():
        try:
            from app.services.retrieval_service import search_relevant_chunks

            relevant = search_relevant_chunks(
                workspace_id=workspace_id,
                query=focus_prompt.strip(),
                top_k=max_chunks,
                document_id=document_id,
                document_ids=document_ids,
            )
            if relevant:
                for r in relevant:
                    ok = _append_chunk(
                        str(r.get("content") or ""),
                        r.get("document_id"),
                        str(r.get("document_name") or "Tài liệu"),
                        int(r.get("page_number") or 1),
                        r.get("chunk_index"),
                    )
                    if not ok:
                        break
                if parts:
                    return "\n\n".join(parts), source_refs
        except Exception as exc:
            logger.warning("Truy xuất theo trọng tâm thất bại, chuyển về spanning sampling: %s", exc)
            source_refs.clear()
            parts.clear()
            total_len = 0

    # 2. Spanning Sampling: Lấy mẫu trải đều qua toàn bộ tài liệu
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        resolved_ids = _resolve_document_ids(cursor, workspace_id, document_id, document_ids)
        if not resolved_ids:
            return "", []

        per_doc = max(1, max_chunks // len(resolved_ids))

        for doc_id in resolved_ids:
            if total_len >= max_chars:
                break

            total_row = cursor.execute(
                "SELECT COUNT(*) FROM document_chunks WHERE workspace_id = ? AND document_id = ?",
                (workspace_id, doc_id),
            ).fetchone()
            total_doc_chunks = total_row[0] if total_row else 0
            if total_doc_chunks == 0:
                continue

            if total_doc_chunks <= per_doc:
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
                step = (total_doc_chunks - 1) / max(1, per_doc - 1)
                sampled_indices = sorted(list({round(i * step) for i in range(per_doc)}))
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


async def _call_ollama_chat(
    system_prompt: str,
    user_prompt: str,
    model: str = DEFAULT_LLM_MODEL,
    json_mode: bool = False,
    timeout_sec: float = OLLAMA_TIMEOUT,
    num_predict: int = 1200,
) -> str:
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "keep_alive": "30m",
        "options": {
            "temperature": 0.4 if json_mode else 0.7,
            "top_p": 0.9,
            "num_predict": num_predict,
            "num_ctx": 4096,
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


async def generate_ai_summary(
    workspace_id: str,
    document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    focus_prompt: Optional[str] = None,
    model: str = DEFAULT_LLM_MODEL,
) -> Dict[str, Any]:
    """
    Sinh bản tóm tắt học tập có cấu trúc Markdown từ tài liệu thực.
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

    system_prompt = (
        "Bạn là Trợ lý Học tập và Nghiên cứu AI thông thái. "
        "Nhiệm vụ của bạn là đọc hiểu sâu sắc ngữ cảnh tài liệu được cung cấp và sinh một bản tóm tắt học tập "
        "toàn diện, rõ ràng, có cấu trúc chặt chẽ bằng định dạng Markdown (tiếng Việt).\n\n"
        "CẤU TRÚC BẢN TÓM TẮT:\n"
        "# 📌 Tổng Quan Cốt Lõi (1-2 đoạn văn súc tích, nắm bắt bản chất vấn đề)\n"
        "## 🔑 Các Khái Niệm / Luận Điểm Then Chốt (gạch đầu dòng phân tích rõ nguyên nhân, bản chất và ý nghĩa)\n"
        "## 💡 Phân Tích & Điểm Cần Lưu Ý (nếu có các bước, phân loại hoặc công thức/nguyên tắc)\n"
        "## 🎯 Kết Luận & Ứng Dụng Thực Tiễn"
    )

    clean_focus = (focus_prompt or "").strip()
    user_prompt = f"TÀI LIỆU NGUỒN THAM KHẢO:\n{context}\n\n"
    if clean_focus:
        user_prompt += f"YÊU CẦU TRỌNG TÂM ĐẶC BIỆT CỦA NGƯỜI DÙNG: {clean_focus}\n\n"
    user_prompt += "Hãy tạo bản tóm tắt học tập theo cấu trúc trên:"

    try:
        markdown_res = await _call_ollama_chat(system_prompt, user_prompt, model=chosen_model)
        title_suffix = (clean_focus[:40] + "...") if len(clean_focus) > 40 else (clean_focus or "Tài liệu học tập")
        return {
            "title": f"Tóm tắt AI · {title_suffix}",
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
        q_terms = {t for t in re.findall(r"[\w]{3,}", q_text, flags=re.UNICODE)}
        best_score = -1
        for ref in source_refs:
            haystack = ref.get("_search_text") or ""
            score = sum(1 for term in q_terms if term in haystack)
            if score > best_score:
                best_score = score
                chosen = ref

    if chosen is None:
        chosen = source_refs[0]

    return {
        "documentId": chosen.get("documentId"),
        "documentName": chosen.get("documentName") or "Tài liệu",
        "pageNumber": chosen.get("pageNumber") or 1,
        "chunkIndex": chosen.get("chunkIndex"),
        "snippet": chosen.get("snippet") or "",
    }


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
    """
    count = min(max(question_count, 1), 20)
    max_chunks = min(22, max(14, count + 2))
    max_chars = 9500 if count > 10 else 7500
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

    system_prompt = (
        "Bạn là Chuyên gia Khảo thí và Thiết kế đề thi giáo dục. "
        "Nhiệm vụ của bạn là đọc kỹ các đoạn nguồn [Nguồn 1], [Nguồn 2]... và soạn một bộ câu hỏi trắc nghiệm "
        "(Multiple Choice Questions) bằng tiếng Việt.\n\n"
        "BẠN PHẢI TRẢ VỀ DUY NHẤT MỘT JSON OBJECT CÓ DẠNG:\n"
        "{\n"
        '  "questions": [\n'
        "    {\n"
        '      "prompt": "Nội dung câu hỏi trắc nghiệm?",\n'
        '      "options": ["Lựa chọn A", "Lựa chọn B", "Lựa chọn C", "Lựa chọn D"],\n'
        '      "answerIndex": 0,\n'
        '      "explanation": "Giải thích chi tiết vì sao đáp án này đúng dựa trên tài liệu",\n'
        '      "sourceIndex": 1\n'
        "    }\n"
        "  ]\n"
        "}\n"
        f"LƯU Ý: answerIndex là số nguyên từ 0 đến 3, sourceIndex là số thứ tự của [Nguồn N] chứa thông tin câu hỏi. "
        f"Hãy tạo đúng {count} câu hỏi."
    )

    clean_focus = (focus_prompt or "").strip()
    user_prompt = f"TÀI LIỆU NGUỒN:\n{context}\n\n"
    if clean_focus:
        user_prompt += f"TRỌNG TÂM KIẾN THỨC CẦN HỎI: {clean_focus}\n\n"
    user_prompt += f"Hãy tạo đúng {count} câu hỏi trắc nghiệm độ khó {difficulty} dưới dạng JSON object có key 'questions':"

    try:
        predict_tokens = min(3200, max(1200, count * 220))
        raw_res = await _call_ollama_chat(
            system_prompt,
            user_prompt,
            model=chosen_model,
            json_mode=True,
            num_predict=predict_tokens,
        )
        data = _parse_json_response(raw_res)

        questions = []
        if isinstance(data, list):
            questions = data
        elif isinstance(data, dict):
            for k in ("questions", "quiz", "data", "items"):
                if isinstance(data.get(k), list):
                    questions = data[k]
                    break
            if not questions and "prompt" in data:
                questions = [data]
        valid_questions = []
        for i, q in enumerate(questions):
            if isinstance(q, dict) and "prompt" in q and "options" in q:
                options = [str(opt) for opt in q["options"]][:4]
                if len(options) >= 2:
                    ans_idx = int(q.get("answerIndex", 0))
                    if ans_idx < 0 or ans_idx >= len(options):
                        ans_idx = 0
                    item_q: Dict[str, Any] = {
                        "id": f"ai-q-{i+1}",
                        "prompt": str(q["prompt"]),
                        "options": options,
                        "answerIndex": ans_idx,
                        "explanation": str(q.get("explanation", "Theo nội dung bài học trong tài liệu.")),
                    }
                    citation = _resolve_question_citation(q, source_refs)
                    if citation:
                        item_q["citation"] = citation
                    valid_questions.append(item_q)

        primary_doc_name = source_refs[0]["documentName"] if source_refs else "Tài liệu học tập"
        title_topic = clean_focus[:48] if clean_focus else primary_doc_name[:48]
        return {
            "title": f"Quiz · {title_topic}",
            "questions": valid_questions,
            "difficulty": difficulty,
            "is_mock": False,
        }
    except Exception as exc:
        logger.exception("Lỗi khi sinh Quiz bằng AI: %s", exc)
        return {
            "title": "Quiz trắc nghiệm",
            "questions": [],
            "error": f"Không thể sinh câu hỏi: {str(exc)}",
            "is_mock": True,
        }


async def generate_ai_flashcards(
    workspace_id: str,
    document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    count: int = 6,
    focus_prompt: Optional[str] = None,
    model: str = DEFAULT_LLM_MODEL,
) -> Dict[str, Any]:
    """
    Sinh bộ thẻ Flashcard (mặt trước: thuật ngữ/khái niệm/câu hỏi; mặt sau: giải nghĩa/bản chất).
    """
    context = _get_document_context(workspace_id, document_id, document_ids, max_chunks=14, max_chars=7000, focus_prompt=focus_prompt)
    if not context:
        return {
            "flashcards": [],
            "error": "Chưa có nội dung tài liệu để tạo Flashcards.",
            "is_mock": False,
        }

    chosen_model, model_error = await _ensure_ollama_chat_model(model)
    if model_error or not chosen_model:
        return {
            "flashcards": [],
            "error": model_error or "Ollama chưa được khởi động.",
            "is_mock": True,
        }

    card_count = min(max(count, 3), 12)
    system_prompt = (
        "Bạn là Trợ lý Học tập thông minh. Hãy đọc hiểu tài liệu và trích xuất các thuật ngữ, nguyên lý, "
        "công thức hoặc khái niệm quan trọng nhất thành một bộ thẻ Flashcards học tập bằng tiếng Việt.\n\n"
        "YÊU CẦU ĐỊNH DẠNG JSON:\n"
        "Trả về một JSON OBJECT có key 'flashcards' là mảng các thẻ:\n"
        "{\n"
        '  "flashcards": [\n'
        "    {\n"
        '      "front": "Tên thuật ngữ, khái niệm hoặc câu hỏi gợi mở ngắn gọn",\n'
        '      "back": "Giải thích ngắn gọn, rõ ràng, nhấn mạnh bản chất vấn đề và ý nghĩa then chốt (1-3 câu)"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        f"Hãy tạo đúng {card_count} thẻ Flashcards giá trị nhất."
    )

    user_prompt = f"TÀI LIỆU NGUỒN:\n{context}\n\n"
    if focus_prompt and focus_prompt.strip():
        user_prompt += f"TRỌNG TÂM THUẬT NGỮ / KHÁI NIỆM CẦN ÔN TẬP: {focus_prompt.strip()}\n\n"
    user_prompt += f"Hãy tạo danh sách {card_count} Flashcards dạng JSON:"

    try:
        raw_res = await _call_ollama_chat(system_prompt, user_prompt, model=chosen_model, json_mode=True)
        data = _parse_json_response(raw_res)

        if isinstance(data, list):
            cards = data
        elif isinstance(data, dict):
            cards = []
            for key in ("flashcards", "cards", "items", "data", "results"):
                value = data.get(key)
                if isinstance(value, list):
                    cards = value
                    break
            if not cards and "front" in data and "back" in data:
                cards = [data]
        else:
            cards = []

        valid_cards = []
        for i, c in enumerate(cards):
            if not isinstance(c, dict) or "front" not in c or "back" not in c:
                continue
            front = str(c["front"]).strip()
            back = str(c["back"]).strip()
            if not front or not back:
                continue
            valid_cards.append({
                "id": f"ai-fc-{len(valid_cards)+1}",
                "front": front,
                "back": back,
                "status": "new",
                "is_mock": False,
            })

        return {
            "flashcards": valid_cards,
            "is_mock": False,
        }
    except Exception as exc:
        logger.exception("Lỗi khi sinh Flashcards bằng AI: %s", exc)
        return {
            "flashcards": [],
            "error": f"Không thể sinh Flashcards: {str(exc)}",
            "is_mock": True,
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
