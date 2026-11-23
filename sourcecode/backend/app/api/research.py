"""API router cho Chế độ Nghiên cứu Sâu đa tài liệu (Deep Research & Synthesis)."""
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.auth import get_current_user
from app.database import get_db_connection
from app.services.research_service import (
    delete_research_project_record,
    list_workspace_research_projects,
    stream_research_synthesis,
    synthesize_research_project_sync,
    update_research_project_record,
)

router = APIRouter(prefix="/api/v1", tags=["Deep Research"])


class ResearchSynthesizeRequest(BaseModel):
    project_id: Optional[str] = Field(default=None, max_length=100)
    notebook_id: Optional[str] = Field(default=None, max_length=100)
    title: Optional[str] = Field(default=None, max_length=200)
    question: str = Field(min_length=2, max_length=6000)
    document_ids: Optional[List[str]] = None
    allow_web: bool = False
    mode: Literal["auto", "local", "web", "hybrid"] = "local"
    model: Optional[str] = None


class ResearchUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    report: Optional[str] = Field(default=None, max_length=150000)


def _assert_workspace_owner(workspace_id: str, user_id: str) -> None:
    conn = get_db_connection()
    try:
        owned = conn.execute(
            "SELECT 1 FROM workspaces WHERE id = ? AND owner_user_id = ?",
            (workspace_id, user_id),
        ).fetchone()
        if not owned:
            raise HTTPException(status_code=404, detail="Không tìm thấy workspace")
    finally:
        conn.close()


@router.get("/workspaces/{workspace_id}/research")
def get_workspace_research_projects(
    workspace_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    projects = list_workspace_research_projects(workspace_id, user["id"])
    if projects is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy workspace")
    return {"projects": projects}


@router.post("/workspaces/{workspace_id}/research/stream")
async def stream_workspace_research(
    workspace_id: str,
    req: ResearchSynthesizeRequest,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
):
    _assert_workspace_owner(workspace_id, user["id"])

    async def event_gen():
        async for chunk in stream_research_synthesis(
            workspace_id=workspace_id,
            question=req.question,
            title=req.title,
            project_id=req.project_id,
            notebook_id=req.notebook_id,
            document_ids=req.document_ids,
            allow_web=req.allow_web,
            mode=req.mode,
            model=req.model,
            is_disconnected=request.is_disconnected,
        ):
            yield chunk

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/workspaces/{workspace_id}/research")
async def synthesize_workspace_research(
    workspace_id: str,
    req: ResearchSynthesizeRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    _assert_workspace_owner(workspace_id, user["id"])
    project = await synthesize_research_project_sync(
        workspace_id=workspace_id,
        question=req.question,
        title=req.title,
        project_id=req.project_id,
        notebook_id=req.notebook_id,
        document_ids=req.document_ids,
        allow_web=req.allow_web,
        mode=req.mode,
        model=req.model,
    )
    return {"project": project}


@router.patch("/research/{project_id}")
def patch_research_project(
    project_id: str,
    req: ResearchUpdateRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    updated = update_research_project_record(
        project_id=project_id,
        user_id=user["id"],
        title=req.title,
        report=req.report,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án nghiên cứu")
    return {"project": updated}


@router.delete("/research/{project_id}")
def delete_research_project(
    project_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ok = delete_research_project_record(project_id, user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án nghiên cứu")
    return {"deleted": True, "id": project_id}
