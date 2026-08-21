from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base, _configure_sqlite_connection
from app.models.studio import Project, ProjectStyle, ProjectVisualStyle, SceneImage
from app.services.studio.entity_crud import create_entity, delete_entity


@pytest.mark.asyncio
async def test_sqlite_entity_delete_cascades_image_slot_and_allows_same_id_recreate(tmp_path) -> None:
    """验证 SQLite 外键已开启，且删除后的资产 ID 可以安全重建。"""
    db_path = tmp_path / "entity-cascade.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    _configure_sqlite_connection(engine)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        foreign_keys = await conn.exec_driver_sql("PRAGMA foreign_keys")
        assert foreign_keys.scalar_one() == 1

    async with session_local() as db:
        db.add(
            Project(
                id="project-1",
                name="项目一",
                description="",
                style=ProjectStyle.real_people_city,
                visual_style=ProjectVisualStyle.live_action,
            )
        )
        await db.commit()

        body = {
            "id": "scene-1",
            "name": "旧宅",
            "description": "老宅室内",
            "project_id": "project-1",
            "style": ProjectStyle.real_people_city,
            "visual_style": ProjectVisualStyle.live_action,
        }
        await create_entity(db, entity_type="scene", body=body)
        await db.commit()

        await delete_entity(db, entity_type="scene", entity_id="scene-1")
        await db.commit()
        image_count = await db.scalar(
            select(func.count()).select_from(SceneImage).where(SceneImage.scene_id == "scene-1")
        )
        assert image_count == 0

        recreated = await create_entity(db, entity_type="scene", body=body)
        await db.commit()
        assert recreated["id"] == "scene-1"

    await engine.dispose()
