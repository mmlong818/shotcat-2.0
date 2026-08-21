from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.studio_project_brain import ProjectBrainCategory, ProjectBrainOrigin, ProjectBrainStatus


class ProjectBrainEntryBase(BaseModel):
    category: ProjectBrainCategory
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    origin: ProjectBrainOrigin = ProjectBrainOrigin.user
    status: ProjectBrainStatus = ProjectBrainStatus.draft
    source_ref: str = Field("", max_length=512)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    locked: bool = False


class ProjectBrainEntryCreate(ProjectBrainEntryBase):
    pass


class ProjectBrainEntryUpdate(BaseModel):
    category: ProjectBrainCategory | None = None
    title: str | None = Field(None, min_length=1, max_length=255)
    content: str | None = Field(None, min_length=1)
    origin: ProjectBrainOrigin | None = None
    status: ProjectBrainStatus | None = None
    source_ref: str | None = Field(None, max_length=512)
    evidence: list[dict[str, Any]] | None = None
    locked: bool | None = None
    expected_version: int = Field(..., ge=1, description="客户端最后读取的版本，防止静默覆盖")


class ProjectBrainEntryRead(ProjectBrainEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    version: int


class ProjectBrainSummaryRead(BaseModel):
    total: int
    confirmed: int
    locked: int
    ai_drafts: int
    by_category: dict[str, int]


__all__ = [
    "ProjectBrainEntryCreate",
    "ProjectBrainEntryUpdate",
    "ProjectBrainEntryRead",
    "ProjectBrainSummaryRead",
]
