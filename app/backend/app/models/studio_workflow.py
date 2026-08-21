from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin


class ProjectWorkflowRevision(Base, TimestampMixin):
    """重做上游步骤前保存的项目快照，可用于审计和恢复。"""

    __tablename__ = "project_workflow_revisions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_step: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    restored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    invalidations: Mapped[list["ProjectWorkflowInvalidation"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        Index("ix_workflow_revisions_project_step_revision", "project_id", "source_step", "revision"),
    )


class ProjectWorkflowInvalidation(Base, TimestampMixin):
    """上游重做后，需要用户重新确认或生成的下游步骤。"""

    __tablename__ = "project_workflow_invalidations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("project_workflow_revisions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    downstream_step: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    affected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)

    revision: Mapped[ProjectWorkflowRevision] = relationship(back_populates="invalidations")

    __table_args__ = (
        Index("ix_workflow_invalidations_project_status", "project_id", "status"),
    )


__all__ = ["ProjectWorkflowRevision", "ProjectWorkflowInvalidation"]
