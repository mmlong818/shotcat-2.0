from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.studio import (
    AssetViewAngle,
    Character,
    CharacterImage,
    FileItem,
    FileType,
    Project,
    ProjectStyle,
    ProjectVisualStyle,
    Prop,
    PropImage,
    Scene,
    SceneImage,
)
from app.services.studio.asset_export import list_project_asset_export_items


async def _build_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_local(), engine


@pytest.mark.asyncio
async def test_asset_export_uses_type_directories_and_current_asset_names() -> None:
    db, engine = await _build_session()
    async with db:
        style = ProjectStyle.real_people_city
        visual_style = ProjectVisualStyle.live_action
        db.add_all(
            [
                Project(id="p1", name="校园故事", description="", style=style, visual_style=visual_style),
                Character(id="char_1", project_id="p1", name="小雨", description="", style=style, visual_style=visual_style),
                Scene(id="scene_1", project_id="p1", name="教学楼/走廊", description="", style=style, visual_style=visual_style),
                Prop(id="prop_1", project_id="p1", name="旧笔记本", description="", style=style, visual_style=visual_style),
                FileItem(id="f1", type=FileType.image, name="旧名", thumbnail="", tags=[], storage_key="generated/char.webp"),
                FileItem(id="f2", type=FileType.image, name="旧名", thumbnail="", tags=[], storage_key="generated/scene.png"),
                FileItem(id="f3", type=FileType.image, name="旧名", thumbnail="", tags=[], storage_key="generated/prop.png"),
                CharacterImage(character_id="char_1", file_id="f1", view_angle=AssetViewAngle.front),
                SceneImage(scene_id="scene_1", file_id="f2", view_angle=AssetViewAngle.back),
                PropImage(prop_id="prop_1", file_id="f3", view_angle=AssetViewAngle.detail),
            ]
        )
        await db.commit()

        archive_name, items = await list_project_asset_export_items(db, project_id="p1")

        assert archive_name == "校园故事_设定图.zip"
        assert [item.filename for item in items] == [
            "角色/小雨.webp",
            "场景/教学楼_走廊-背面.png",
            "道具/旧笔记本-细节.png",
        ]
    await engine.dispose()
