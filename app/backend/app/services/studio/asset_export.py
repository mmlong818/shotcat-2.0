"""项目设定图 ZIP 导出服务。"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.studio import Character, CharacterImage, FileItem, Project, Prop, PropImage, Scene, SceneImage
from app.services.common import entity_not_found
from app.services.studio.entity_image_names import entity_image_default_name
from app.services.studio.keyframe_export import ArchiveItem, _safe_filename_part


ASSET_EXPORT_TYPES = (
    ("角色", Character, CharacterImage, "character_id"),
    ("场景", Scene, SceneImage, "scene_id"),
    ("道具", Prop, PropImage, "prop_id"),
)


async def list_project_asset_export_items(
    db: AsyncSession,
    *,
    project_id: str,
) -> tuple[str, list[ArchiveItem]]:
    """读取项目所有已生成设定图，按资产类型和当前名称生成 ZIP 路径。"""
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=entity_not_found("Project"))

    items: list[ArchiveItem] = []
    used_names: defaultdict[str, int] = defaultdict(int)
    for category, entity_model, image_model, image_entity_id in ASSET_EXPORT_TYPES:
        entity_id = getattr(image_model, image_entity_id)
        rows = (
            await db.execute(
                select(
                    entity_model.name,
                    image_model.view_angle,
                    image_model.id,
                    FileItem.storage_key,
                )
                .join(image_model, entity_id == entity_model.id)
                .join(FileItem, FileItem.id == image_model.file_id)
                .where(entity_model.project_id == project_id, image_model.file_id.is_not(None))
                .order_by(entity_model.name.asc(), image_model.id.asc())
            )
        ).all()
        for entity_name, view_angle, _image_id, storage_key in rows:
            extension = Path(str(storage_key)).suffix.lower() or ".png"
            image_name = _safe_filename_part(
                entity_image_default_name(str(entity_name), view_angle),
                "设定图",
            )
            archive_path = f"{category}/{image_name}{extension}"
            used_names[archive_path] += 1
            if used_names[archive_path] > 1:
                archive_path = f"{category}/{image_name}_{used_names[archive_path]:02d}{extension}"
            items.append(ArchiveItem(filename=archive_path, storage_key=str(storage_key)))

    if not items:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="当前项目没有可导出的设定图")

    archive_name = f"{_safe_filename_part(project.name, '项目')}_设定图.zip"
    return archive_name, items
