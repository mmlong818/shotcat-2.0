"""修复旧版 SQLite 未启用外键时遗留的 Studio 数据。"""

from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import async_session_maker
from app.models.studio import (
    Actor,
    ActorImage,
    Character,
    CharacterImage,
    Costume,
    CostumeImage,
    Prop,
    PropImage,
    Scene,
    SceneImage,
)

logger = logging.getLogger(__name__)

_IMAGE_PARENT_SPECS = (
    (ActorImage, Actor, "actor_id"),
    (CharacterImage, Character, "character_id"),
    (SceneImage, Scene, "scene_id"),
    (PropImage, Prop, "prop_id"),
    (CostumeImage, Costume, "costume_id"),
)


async def cleanup_orphaned_entity_image_slots(
    session_factory: Callable[[], AsyncSession] = async_session_maker,
) -> int:
    """删除不存在父实体的图片槽位，并返回清理数量。"""
    removed = 0
    async with session_factory() as db:
        for image_model, parent_model, parent_field in _IMAGE_PARENT_SPECS:
            parent_id = getattr(image_model, parent_field)
            result = await db.execute(
                delete(image_model).where(parent_id.not_in(select(parent_model.id)))
            )
            removed += max(int(result.rowcount or 0), 0)
        if removed:
            await db.commit()

    if removed:
        logger.warning("removed orphaned entity image slots on startup: count=%s", removed)
    return removed
