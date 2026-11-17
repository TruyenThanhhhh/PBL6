"""
Endpoints API cho Bộ công cụ hỗ trợ học tập (Study Tools):
- POST /api/v1/study/summary
- POST /api/v1/study/quiz
- POST /api/v1/study/flashcards
- POST /api/v1/study/mindmap
- POST /api/v1/study/notes
- POST /api/v1/study/plan
- POST /api/v1/study/export
"""
import asyncio
from contextlib import suppress
from typing import Any, Awaitable, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.api.auth import get_current_user_optional
from app.config import DEFAULT_LLM_MODEL
from app.services.export_service import build_content_disposition, build_export_payload
from app.services.study_service import (
    generate_ai_summary,
    generate_ai_quiz,
    generate_ai_flashcards,
    generate_ai_mindmap,
    generate_ai_notes,
    generate_ai_plan,
)

router = APIRouter(prefix="/api/v1/study", tags=["Study Tools (AI Learning)"])

class StudySummaryRequest(BaseModel):
    workspace_id: str
    document_id: Optional[str] = None
    document_ids: Optional[List[str]] = None
    focus_prompt: Optional[str] = None
    model: Optional[str] = None

class StudyQuizRequest(BaseModel):
    workspace_id: str
    document_id: Optional[str] = None
    document_ids: Optional[List[str]] = None
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard)$")
    question_count: int = Field(default=5, ge=1, le=10)
    focus_prompt: Optional[str] = None
    model: Optional[str] = None

class StudyFlashcardsRequest(BaseModel):
    workspace_id: str
    document_id: Optional[str] = None
    document_ids: Optional[List[str]] = None
    count: int = Field(default=6, ge=1, le=12)
    focus_prompt: Optional[str] = None
    model: Optional[str] = None

class StudyMindmapRequest(BaseModel):
    workspace_id: str
    document_id: Optional[str] = None
    document_ids: Optional[List[str]] = None
    focus_prompt: Optional[str] = None
    max_depth: int = Field(default=3, ge=2, le=4)
    model: Optional[str] = None

class StudyNotesRequest(BaseModel):
    workspace_id: str
    document_id: Optional[str] = None
    document_ids: Optional[List[str]] = None
    focus_prompt: Optional[str] = None
    model: Optional[str] = None

class StudyPlanRequest(BaseModel):
    workspace_id: str
    document_id: Optional[str] = None
    document_ids: Optional[List[str]] = None
    start_date: Optional[str] = None
    day_span: int = Field(default=7, ge=1, le=30)
    focus_prompt: Optional[str] = None
    model: Optional[str] = None


class StudyExportRequest(BaseModel):
    title: str = Field(default="Tai_lieu_hoc_tap", max_length=200)
    content: str
    format: str = Field(default="md", pattern="^(md|docx|pdf)$")


async def _run_until_disconnect(
    request: Request,
    coro: Awaitable[Dict[str, Any]],
) -> Dict[str, Any]:
    """Chạy tác vụ AI nhưng hủy ngay nếu client ngắt kết nối (AbortController)."""
    task = asyncio.create_task(coro)
    try:
        while not task.done():
            if await request.is_disconnected():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
                raise HTTPException(status_code=499, detail="Yêu cầu đã bị hủy bởi người dùng.")
            done, _ = await asyncio.wait({task}, timeout=0.25)
            if done:
                break
        return await task
    except asyncio.CancelledError:
        task.cancel()
        raise


@router.post("/summary")
async def create_study_summary(
    req: StudySummaryRequest,
    request: Request,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
):
    """
    Sinh bản tóm tắt học tập định dạng Markdown bằng LLM AI từ tài liệu nguồn thực tế.
    """
    return await _run_until_disconnect(
        request,
        generate_ai_summary(
            workspace_id=req.workspace_id,
            document_id=req.document_id,
            document_ids=req.document_ids,
            focus_prompt=req.focus_prompt,
            model=req.model or DEFAULT_LLM_MODEL,
        ),
    )


@router.post("/quiz")
async def create_study_quiz(
    req: StudyQuizRequest,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
):
    """
    Sinh bài trắc nghiệm trắc nghiệm nhiều lựa chọn (Multiple Choice) bằng AI kèm lời giải thích.
    """
    return await generate_ai_quiz(
        workspace_id=req.workspace_id,
        document_id=req.document_id,
        document_ids=req.document_ids,
        difficulty=req.difficulty,
        question_count=req.question_count,
        focus_prompt=req.focus_prompt,
        model=req.model or DEFAULT_LLM_MODEL,
    )


@router.post("/flashcards")
async def create_study_flashcards(
    req: StudyFlashcardsRequest,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
):
    """
    Trích xuất danh sách thẻ học tập Flashcards (thuật ngữ & định nghĩa) bằng AI từ tài liệu.
    """
    return await generate_ai_flashcards(
        workspace_id=req.workspace_id,
        document_id=req.document_id,
        document_ids=req.document_ids,
        count=req.count,
        focus_prompt=req.focus_prompt,
        model=req.model or DEFAULT_LLM_MODEL,
    )


@router.post("/mindmap")
async def create_study_mindmap(
    req: StudyMindmapRequest,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
):
    """
    Sinh sơ đồ tư duy (Mindmap) phân cấp bằng AI từ tài liệu nguồn.
    """
    return await generate_ai_mindmap(
        workspace_id=req.workspace_id,
        document_id=req.document_id,
        document_ids=req.document_ids,
        focus_prompt=req.focus_prompt,
        max_depth=req.max_depth,
        model=req.model or DEFAULT_LLM_MODEL,
    )


@router.post("/notes")
async def create_study_notes(
    req: StudyNotesRequest,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
):
    """
    Sinh ghi chú học tập có cấu trúc Markdown bằng AI từ tài liệu nguồn.
    """
    return await generate_ai_notes(
        workspace_id=req.workspace_id,
        document_id=req.document_id,
        document_ids=req.document_ids,
        focus_prompt=req.focus_prompt,
        model=req.model or DEFAULT_LLM_MODEL,
    )


@router.post("/plan")
async def create_study_plan(
    req: StudyPlanRequest,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
):
    """
    Sinh lộ trình học tập (danh sách nhiệm vụ kèm hạn) bằng AI từ tài liệu nguồn.
    """
    return await generate_ai_plan(
        workspace_id=req.workspace_id,
        document_id=req.document_id,
        document_ids=req.document_ids,
        start_date=req.start_date,
        day_span=req.day_span,
        focus_prompt=req.focus_prompt,
        model=req.model or DEFAULT_LLM_MODEL,
    )


@router.post("/export")
async def export_study_document(
    req: StudyExportRequest,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
):
    """
    Xuất nội dung học tập / báo cáo Markdown sang định dạng .md, .docx hoặc .pdf.
    """
    if not req.content or not req.content.strip():
        raise HTTPException(status_code=400, detail="Không có nội dung để xuất file.")

    try:
        payload_bytes, media_type, ascii_name, utf8_name = build_export_payload(
            title=req.title,
            content=req.content,
            fmt=req.format,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Không thể tạo file {req.format}: {str(exc)}") from exc

    return Response(
        content=payload_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": build_content_disposition(ascii_name, utf8_name),
        },
    )
