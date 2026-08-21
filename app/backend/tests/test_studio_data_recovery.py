from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.studio import AssetQualityLevel, AssetViewAngle, SceneImage
from app.services.studio.data_recovery import cleanup_orphaned_entity_image_slots


@pytest.mark.asyncio
async def test_cleanup_orphaned_entity_image_slots_removes_legacy_slot() -> None:
    """验证旧数据库中没有父场景的图片槽位会被清理。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_local() as db:
        db.add(
            SceneImage(
                scene_id="missing-scene",
                quality_level=AssetQualityLevel.low,
                view_angle=AssetViewAngle.front,
            )
        )
        await db.commit()

    assert await cleanup_orphaned_entity_image_slots(session_local) == 1

    async with session_local() as db:
        count = await db.scalar(select(func.count()).select_from(SceneImage))
        assert count == 0

    await engine.dispose()
