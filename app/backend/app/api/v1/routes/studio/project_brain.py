from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.studio import Project, ProjectBrainEntry
from app.models.studio_project_brain import ProjectBrainCategory, ProjectBrainOrigin, ProjectBrainStatus
from app.schemas.common import ApiResponse, created_response, empty_response, success_response
from app.schemas.studio.project_brain import (
    ProjectBrainEntryCreate,
    ProjectBrainEntryRead,
    ProjectBrainEntryUpdate,
    ProjectBrainSummaryRead,
)
from app.services.common import entity_not_found, flush_and_refresh, get_or_404, patch_model

router = APIRouter()


async def _get_entry(db: AsyncSession, *, project_id: str, entry_id: str) -> ProjectBrainEntry:
    entry = await get_or_404(
        db, ProjectBrainEntry, entry_id, detail=entity_not_found("Project brain entry")
    )
    if entry.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project brain entry not found")
    return entry


@router.get("", response_model=ApiResponse[list[ProjectBrainEntryRead]], summary="读取项目大脑")
async def list_project_brain_entries(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    category: ProjectBrainCategory | None = Query(None),
    entry_status: ProjectBrainStatus | None = Query(None, alias="status"),
) -> ApiResponse[list[ProjectBrainEntryRead]]:
    await get_or_404(db, Project, project_id, detail=entity_not_found("Project"))
    stmt = select(ProjectBrainEntry).where(ProjectBrainEntry.project_id == project_id)
    if category is not None:
        stmt = stmt.where(ProjectBrainEntry.category == category)
    if entry_status is not None:
        stmt = stmt.where(ProjectBrainEntry.status == entry_status)
    stmt = stmt.order_by(ProjectBrainEntry.category, ProjectBrainEntry.locked.desc(), ProjectBrainEntry.updated_at.desc())
    result = await db.execute(stmt)
    return success_response([ProjectBrainEntryRead.model_validate(item) for item in result.scalars().all()])


@router.get("/summary", response_model=ApiResponse[ProjectBrainSummaryRead], summary="项目大脑概况")
async def get_project_brain_summary(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProjectBrainSummaryRead]:
    await get_or_404(db, Project, project_id, detail=entity_not_found("Project"))
    result = await db.execute(select(ProjectBrainEntry).where(ProjectBrainEntry.project_id == project_id))
    entries = list(result.scalars().all())
    by_category: dict[str, int] = {}
    for entry in entries:
        key = entry.category.value if isinstance(entry.category, ProjectBrainCategory) else str(entry.category)
        by_category[key] = by_category.get(key, 0) + 1
    return success_response(ProjectBrainSummaryRead(
        total=len(entries),
        confirmed=sum(entry.status == ProjectBrainStatus.confirmed for entry in entries),
        locked=sum(entry.locked for entry in entries),
        ai_drafts=sum(
            entry.origin == ProjectBrainOrigin.ai and entry.status == ProjectBrainStatus.draft
            for entry in entries
        ),
        by_category=by_category,
    ))


@router.post("", response_model=ApiResponse[ProjectBrainEntryRead], status_code=status.HTTP_201_CREATED, summary="新增项目事实或规则")
async def create_project_brain_entry(
    project_id: str,
    body: ProjectBrainEntryCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProjectBrainEntryRead]:
    await get_or_404(db, Project, project_id, detail=entity_not_found("Project"))
    entry = ProjectBrainEntry(
        id=f"brain_{uuid4().hex}",
        project_id=project_id,
        version=1,
        **body.model_dump(),
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return created_response(ProjectBrainEntryRead.model_validate(entry))


@router.patch("/{entry_id}", response_model=ApiResponse[ProjectBrainEntryRead], summary="更新项目事实或规则")
async def update_project_brain_entry(
    project_id: str,
    entry_id: str,
    body: ProjectBrainEntryUpdate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProjectBrainEntryRead]:
    entry = await _get_entry(db, project_id=project_id, entry_id=entry_id)
    if entry.version != body.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"项目大脑条目已更新，请刷新后重试（当前版本 {entry.version}）",
        )
    changes = body.model_dump(exclude_unset=True, exclude={"expected_version"})
    patch_model(entry, changes)
    entry.version += 1
    await flush_and_refresh(db, entry)
    return success_response(ProjectBrainEntryRead.model_validate(entry))


@router.delete("/{entry_id}", response_model=ApiResponse[None], summary="删除未锁定的项目大脑条目")
async def delete_project_brain_entry(
    project_id: str,
    entry_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    entry = await _get_entry(db, project_id=project_id, entry_id=entry_id)
    if entry.locked:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已锁定条目不能删除，请先解除锁定")
    await db.delete(entry)
    await db.flush()
    return empty_response()


__all__ = ["router"]
