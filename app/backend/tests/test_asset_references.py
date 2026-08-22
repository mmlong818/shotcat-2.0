from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.studio import Character, FileItem, Project
from app.schemas.studio.asset_references import AssetReferenceCreate, AssetReferenceUpdate
from app.services.studio.asset_references import (
    list_asset_references, register_asset_reference, update_asset_reference,
)
from app.services.studio.entity_crud import delete_entity


async def _build_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_local(), engine


@pytest.mark.asyncio
async def test_reference_versions_adopt_and_respect_lock() -> None:
    db, engine = await _build_session()
    async with db:
        db.add(Project(id="p1", name="项目", style="drama"))
        db.add(Character(id="c1", project_id="p1", name="周诚", style="drama"))
        db.add_all([
            FileItem(id="f1", type="image", name="初稿", thumbnail="", tags=[], storage_key="f1.png"),
            FileItem(id="f2", type="image", name="二稿", thumbnail="", tags=[], storage_key="f2.png"),
            FileItem(id="f3", type="image", name="上传稿", thumbnail="", tags=[], storage_key="f3.png"),
        ])
        await db.flush()

        first = await register_asset_reference(db, project_id="p1", body=AssetReferenceCreate(
            entity_type="character", entity_id="c1", file_id="f1", source="generated",
        ))
        second = await register_asset_reference(db, project_id="p1", body=AssetReferenceCreate(
            entity_type="character", entity_id="c1", file_id="f2", source="generated",
        ))
        await update_asset_reference(db, project_id="p1", reference_id=second.id, body=AssetReferenceUpdate(is_locked=True))
        upload = await register_asset_reference(db, project_id="p1", body=AssetReferenceCreate(
            entity_type="character", entity_id="c1", file_id="f3", display_name="我认可的旧宅便装",
            source="upload",
        ))

        rows = await list_asset_references(db, project_id="p1")
        assert [row.version for row in sorted(rows, key=lambda row: row.version)] == [1, 2, 3]
        assert first.is_adopted is False
        assert second.is_adopted is True and second.is_locked is True
        assert upload.is_adopted is False

        adopted = await update_asset_reference(
            db, project_id="p1", reference_id=upload.id,
            body=AssetReferenceUpdate(is_adopted=True, is_locked=True),
        )
        assert adopted.display_name == "我认可的旧宅便装"
        assert adopted.is_adopted is True and adopted.is_locked is True
        assert second.is_adopted is False and second.is_locked is False

        await delete_entity(db, entity_type="character", entity_id="c1")
        assert await list_asset_references(db, project_id="p1") == []
    await engine.dispose()
