from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin


class AssetReferenceVersion(Base, TimestampMixin):
    """可追溯的设定参考图版本；实体名称变化不会改变稳定引用 ID。"""

    __tablename__ = "asset_reference_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    image_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="generated")
    is_adopted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    __table_args__ = (
        UniqueConstraint(
            "project_id", "entity_type", "entity_id", "version",
            name="uq_asset_reference_entity_version",
        ),
        Index(
            "ix_asset_reference_project_entity",
            "project_id", "entity_type", "entity_id",
        ),
    )


__all__ = ["AssetReferenceVersion"]
