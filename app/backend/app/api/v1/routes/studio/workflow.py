from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.studio import Project, ProjectWorkflowInvalidation, ProjectWorkflowRevision
from app.schemas.common import ApiResponse, created_response, success_response
from app.schemas.studio.workflow import (
    WorkflowImpactRead, WorkflowInvalidationRead, WorkflowInvalidationResolve,
    WorkflowRevisionCreate, WorkflowRevisionRead,
    WorkflowRevisionSnapshotRead,
    WorkflowStepComplete,
)
from app.services.common import entity_not_found, get_or_404
from app.services.studio.workflow import capture_revision, project_impact

router = APIRouter()


@router.post("/complete", response_model=ApiResponse[int], summary="标记一个工作流步骤已重新完成")
async def complete_workflow_step(
    project_id: str,
    body: WorkflowStepComplete,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[int]:
    rows = list((await db.execute(select(ProjectWorkflowInvalidation).where(
        ProjectWorkflowInvalidation.project_id == project_id,
        ProjectWorkflowInvalidation.downstream_step == body.step,
        ProjectWorkflowInvalidation.status == "pending",
    ))).scalars().all())
    for row in rows:
        row.status = "resolved"
    await db.flush()
    return success_response(len(rows))


@router.get("/impact", response_model=ApiResponse[WorkflowImpactRead], summary="预览重做步骤的下游影响")
async def get_workflow_impact(
    project_id: str,
    source_step: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[WorkflowImpactRead]:
    await get_or_404(db, Project, project_id, detail=entity_not_found("Project"))
    try:
        impact = await project_impact(db, project_id=project_id, source_step=source_step)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return success_response(impact)


@router.post("/revisions", response_model=ApiResponse[WorkflowRevisionRead], status_code=status.HTTP_201_CREATED, summary="保存重做前快照并标记下游失效")
async def create_workflow_revision(
    project_id: str,
    body: WorkflowRevisionCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[WorkflowRevisionRead]:
    await get_or_404(db, Project, project_id, detail=entity_not_found("Project"))
    try:
        revision, _ = await capture_revision(
            db, project_id=project_id, source_step=body.source_step,
            reason=body.reason, source_task_id=body.source_task_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return created_response(WorkflowRevisionRead.model_validate(revision))


@router.get("/revisions", response_model=ApiResponse[list[WorkflowRevisionRead]], summary="读取项目重做快照历史")
async def list_workflow_revisions(
    project_id: str,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[WorkflowRevisionRead]]:
    rows = list((await db.execute(
        select(ProjectWorkflowRevision).where(ProjectWorkflowRevision.project_id == project_id)
        .order_by(ProjectWorkflowRevision.created_at.desc()).limit(limit)
    )).scalars().all())
    return success_response([WorkflowRevisionRead.model_validate(row) for row in rows])


@router.get("/revisions/{revision_id}/snapshot", response_model=ApiResponse[WorkflowRevisionSnapshotRead], summary="读取可恢复的项目快照")
async def get_workflow_revision_snapshot(
    project_id: str,
    revision_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[WorkflowRevisionSnapshotRead]:
    row = await get_or_404(db, ProjectWorkflowRevision, revision_id, detail="Workflow revision not found")
    if row.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow revision not found")
    return success_response(WorkflowRevisionSnapshotRead(
        id=row.id,
        project_id=row.project_id,
        source_step=row.source_step,
        revision=row.revision,
        snapshot=dict(row.snapshot or {}),
    ))


@router.get("/invalidations", response_model=ApiResponse[list[WorkflowInvalidationRead]], summary="读取待重做的下游步骤")
async def list_workflow_invalidations(
    project_id: str,
    pending_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[WorkflowInvalidationRead]]:
    stmt = select(ProjectWorkflowInvalidation).where(ProjectWorkflowInvalidation.project_id == project_id)
    if pending_only:
        stmt = stmt.where(ProjectWorkflowInvalidation.status == "pending")
    rows = list((await db.execute(stmt.order_by(ProjectWorkflowInvalidation.created_at.desc()))).scalars().all())
    return success_response([WorkflowInvalidationRead.model_validate(row) for row in rows])


@router.patch("/invalidations/{invalidation_id}", response_model=ApiResponse[WorkflowInvalidationRead], summary="确认下游步骤已处理")
async def resolve_workflow_invalidation(
    project_id: str,
    invalidation_id: int,
    body: WorkflowInvalidationResolve,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[WorkflowInvalidationRead]:
    row = await get_or_404(db, ProjectWorkflowInvalidation, invalidation_id, detail="Workflow invalidation not found")
    if row.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow invalidation not found")
    row.status = body.status
    await db.flush()
    await db.refresh(row)
    return success_response(WorkflowInvalidationRead.model_validate(row))


__all__ = ["router"]
