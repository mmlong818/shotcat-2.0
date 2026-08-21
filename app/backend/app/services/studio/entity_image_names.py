from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.studio import FileItem
from app.services.studio.entity_specs import entity_spec, normalize_entity_type

ANGLE_LABELS = {
    "FRONT": "",
    "LEFT": "左侧",
    "RIGHT": "右侧",
    "BACK": "背面",
    "THREE_QUARTER": "四分之三侧面",
    "TOP": "俯视",
    "DETAIL": "细节",
}

RELATION_ENTITY_TYPES = {
    "actor_image": "actor",
    "character_image": "character",
    "scene_image": "scene",
    "prop_image": "prop",
    "costume_image": "costume",
}


def _angle_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().upper()


def entity_image_default_name(entity_name: str, view_angle: Any) -> str:
    base = (entity_name or "").strip()
    label = ANGLE_LABELS.get(_angle_value(view_angle), _angle_value(view_angle))
    if not base:
        return label or "造型图"
    return f"{base}-{label}" if label else base


async def resolve_entity_image_default_names(
    db: AsyncSession,
    *,
    entity_type: str,
    image_rows: list[Any],
) -> dict[int, str]:
    entity_type_norm = normalize_entity_type(entity_type)
    spec = entity_spec(entity_type_norm)
    parent_ids = [getattr(row, spec.id_field, None) for row in image_rows]
    parent_ids = [str(x) for x in dict.fromkeys(parent_ids) if x]
    if not parent_ids:
        return {}

    parent_rows = (
        await db.execute(select(spec.model.id, spec.model.name).where(spec.model.id.in_(parent_ids)))
    ).all()
    names = {str(row[0]): str(row[1] or "") for row in parent_rows}
    result: dict[int, str] = {}
    for row in image_rows:
        parent_id = str(getattr(row, spec.id_field, "") or "")
        result[int(row.id)] = entity_image_default_name(names.get(parent_id, ""), getattr(row, "view_angle", ""))
    return result


async def sync_entity_image_file_names(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
) -> None:
    entity_type_norm = normalize_entity_type(entity_type)
    spec = entity_spec(entity_type_norm)
    parent = await db.get(spec.model, entity_id)
    if parent is None:
        return

    parent_field = getattr(spec.image_model, spec.id_field)
    rows = (
        await db.execute(
            select(spec.image_model).where(parent_field == entity_id, spec.image_model.file_id.is_not(None))
        )
    ).scalars().all()
    for row in rows:
        if not row.file_id:
            continue
        file_obj = await db.get(FileItem, row.file_id)
        if file_obj is not None:
            file_obj.name = entity_image_default_name(str(parent.name or ""), getattr(row, "view_angle", ""))


async def default_name_for_relation_image(
    db: AsyncSession,
    *,
    relation_type: str,
    relation_entity_id: str,
) -> str:
    entity_type = RELATION_ENTITY_TYPES.get(relation_type)
    if not entity_type:
        return f"{relation_type}-{relation_entity_id}"
    spec = entity_spec(entity_type)
    try:
        image_id = int(relation_entity_id)
    except ValueError:
        return f"{relation_type}-{relation_entity_id}"
    image_row = await db.get(spec.image_model, image_id)
    if image_row is None:
        return f"{relation_type}-{relation_entity_id}"
    parent_id = getattr(image_row, spec.id_field, None)
    parent = await db.get(spec.model, parent_id) if parent_id else None
    if parent is None:
        return f"{relation_type}-{relation_entity_id}"
    return entity_image_default_name(str(parent.name or ""), getattr(image_row, "view_angle", ""))
