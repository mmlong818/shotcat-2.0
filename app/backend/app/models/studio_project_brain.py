from __future__ import annotations

from enum import Enum
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin


class ProjectBrainCategory(str, Enum):
    fact = "fact"
    character = "character"
    environment = "environment"
    prop = "prop"
    style = "style"
    narrative = "narrative"
    continuity = "continuity"


class ProjectBrainOrigin(str, Enum):
    source = "source"
    user = "user"
    ai = "ai"


class ProjectBrainStatus(str, Enum):
    draft = "draft"
    confirmed = "confirmed"
    rejected = "rejected"


class ProjectBrainEntry(Base, TimestampMixin):
    """项目级创作事实与规则。

    `origin` 和 `status` 明确区分原文事实、用户决定和 AI 推断；`locked`
    表示后续自动分析不得覆盖这条规则。`version` 用于防止多个页面互相覆盖。
    """

    __tablename__ = "project_brain_entries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="项目大脑条目 ID")
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属项目 ID",
    )
    category: Mapped[ProjectBrainCategory] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="简短标题")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="事实或规则正文")
    origin: Mapped[ProjectBrainOrigin] = mapped_column(String(16), nullable=False, index=True)
    status: Mapped[ProjectBrainStatus] = mapped_column(
        String(16), nullable=False, default=ProjectBrainStatus.draft, index=True
    )
    source_ref: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", comment="来源位置，如章节、段落或用户说明"
    )
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list, comment="支持该条目的证据片段"
    )
    locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True, comment="是否禁止自动流程覆盖"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="乐观锁版本号")

    project: Mapped["Project"] = relationship(back_populates="brain_entries")

    __table_args__ = (
        Index("ix_project_brain_project_category_status", "project_id", "category", "status"),
        Index("ix_project_brain_project_locked", "project_id", "locked"),
    )


__all__ = [
    "ProjectBrainCategory",
    "ProjectBrainOrigin",
    "ProjectBrainStatus",
    "ProjectBrainEntry",
]
