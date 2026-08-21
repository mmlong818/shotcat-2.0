from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WorkflowImpactItem(BaseModel):
    step: str
    label: str
    affected_count: int = 0


class WorkflowImpactRead(BaseModel):
    project_id: str
    source_step: str
    total_affected: int
    items: list[WorkflowImpactItem] = Field(default_factory=list)


class WorkflowRevisionCreate(BaseModel):
    source_step: str
    reason: str = ""
    source_task_id: str | None = None


class WorkflowRevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    source_step: str
    revision: int
    reason: str
    source_task_id: str | None
    restored: bool
    snapshot_available: bool = True
    created_at: datetime


class WorkflowRevisionSnapshotRead(BaseModel):
    id: str
    project_id: str
    source_step: str
    revision: int
    snapshot: dict


class WorkflowInvalidationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: str
    revision_id: str
    downstream_step: str
    affected_count: int
    reason: str
    status: str
    created_at: datetime


class WorkflowInvalidationResolve(BaseModel):
    status: str = Field("resolved", pattern="^(resolved|dismissed)$")


class WorkflowStepComplete(BaseModel):
    step: str


__all__ = [
    "WorkflowImpactItem", "WorkflowImpactRead", "WorkflowRevisionCreate",
    "WorkflowRevisionRead", "WorkflowInvalidationRead", "WorkflowInvalidationResolve", "WorkflowStepComplete",
    "WorkflowRevisionSnapshotRead",
]
