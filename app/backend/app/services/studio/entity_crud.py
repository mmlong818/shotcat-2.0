"""Studio 实体主资源 CRUD。"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.utils import apply_keyword_filter, apply_order, paginate
from app.models.studio import (
    Actor,
    Chapter,
    Costume,
    Project,
    Shot,
    ShotCharacterLink,
    ShotDetail,
    ShotDialogLine,
    ShotExtractedCandidate,
)
from app.schemas.studio.cast import ShotCharacterLinkCreate
from app.services.common import entity_already_exists, entity_not_found
from app.services.studio.entity_image_names import sync_entity_image_file_names
from app.services.studio.entity_specs import DEFAULT_VIEW_ANGLES, LINK_MODEL_BY_ENTITY, entity_spec, normalize_entity_type
from app.services.studio.entity_thumbnails import resolve_thumbnails
from app.services.studio.shot_character_links import upsert as upsert_shot_character_link
from app.utils.project_links import upsert_project_link

ENTITY_ORDER_FIELDS = {"name", "style", "visual_style", "created_at", "updated_at"}
STATE_BASE_PREFIX = "【状态关系】派生自："


def _asset_read_payload(obj: Any, thumbnail: str) -> dict[str, Any]:
    return {
        "id": obj.id,
        "name": obj.name,
        "description": obj.description,
        "tags": obj.tags or [],
        "prompt_template_id": obj.prompt_template_id,
        "view_count": obj.view_count,
        "style": obj.style,
        "visual_style": obj.visual_style,
        "thumbnail": thumbnail,
    }


def _repair_legacy_description_line(value: str) -> str:
    """恢复少量旧项目中被按 Latin-1 误存的一至两层 UTF-8 文本。"""
    repaired = value or ""
    if not any(marker in repaired for marker in ("Ã", "Â", "â", "ã")):
        return repaired
    for _ in range(2):
        try:
            decoded = repaired.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if not decoded or "\ufffd" in decoded or decoded == repaired:
            break
        repaired = decoded
        if any("\u4e00" <= char <= "\u9fff" or char in "【】" for char in repaired):
            break
    return repaired


def _derived_base_name(description: str | None) -> str:
    """从状态说明中读取派生资产的基准名称，兼容旧项目乱码。"""
    for raw_line in (description or "").splitlines():
        line = _repair_legacy_description_line(raw_line).strip()
        if line.startswith(STATE_BASE_PREFIX):
            return line.removeprefix(STATE_BASE_PREFIX).strip()
    return ""


async def _replace_project_asset_links(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
    fallback_entity_id: str,
) -> set[str]:
    """把场景/道具等项目关联改为基准资产，并合并同一镜头内的重复关联。"""
    link_spec = LINK_MODEL_BY_ENTITY.get(entity_type)
    if link_spec is None:
        return set()
    link_model, asset_field = link_spec
    rows = list(
        (await db.execute(select(link_model).where(getattr(link_model, asset_field) == entity_id))).scalars().all()
    )
    affected_shot_ids: set[str] = set()
    for row in rows:
        if row.shot_id:
            affected_shot_ids.add(str(row.shot_id))
        scope_conditions = [
            getattr(link_model, field_name) == getattr(row, field_name)
            for field_name in ("project_id", "chapter_id", "shot_id")
        ]
        existing = (
            await db.execute(
                select(link_model).where(
                    getattr(link_model, asset_field) == fallback_entity_id,
                    *scope_conditions,
                )
            )
        ).scalars().first()
        if existing is not None:
            await db.delete(row)
        else:
            setattr(row, asset_field, fallback_entity_id)
    return affected_shot_ids


async def _replace_character_links(
    db: AsyncSession,
    *,
    entity_id: str,
    fallback_entity_id: str,
) -> set[str]:
    """把镜头角色、对白与候选引用改为基准角色，保留镜头内排序。"""
    rows = list(
        (await db.execute(select(ShotCharacterLink).where(ShotCharacterLink.character_id == entity_id))).scalars().all()
    )
    affected_shot_ids: set[str] = set()
    for row in rows:
        affected_shot_ids.add(str(row.shot_id))
        existing = (
            await db.execute(
                select(ShotCharacterLink).where(
                    ShotCharacterLink.shot_id == row.shot_id,
                    ShotCharacterLink.character_id == fallback_entity_id,
                )
            )
        ).scalars().first()
        if existing is not None:
            await db.delete(row)
        else:
            row.character_id = fallback_entity_id

    dialogue_rows = list(
        (
            await db.execute(
                select(ShotDialogLine).where(
                    (ShotDialogLine.speaker_character_id == entity_id)
                    | (ShotDialogLine.target_character_id == entity_id)
                )
            )
        ).scalars().all()
    )
    for row in dialogue_rows:
        if row.speaker_character_id == entity_id:
            row.speaker_character_id = fallback_entity_id
        if row.target_character_id == entity_id:
            row.target_character_id = fallback_entity_id
    return affected_shot_ids


async def _replace_extracted_candidate_links(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
    fallback_entity_id: str,
) -> None:
    """同步镜头提取候选的已确认实体，避免编辑页回到已删除状态。"""
    rows = list(
        (
            await db.execute(
                select(ShotExtractedCandidate).where(
                    ShotExtractedCandidate.candidate_type == entity_type,
                    ShotExtractedCandidate.linked_entity_id == entity_id,
                )
            )
        ).scalars().all()
    )
    for row in rows:
        row.linked_entity_id = fallback_entity_id


async def list_entity_usage_summaries(
    db: AsyncSession,
    *,
    entity_type: str,
    project_id: str,
) -> list[dict[str, Any]]:
    """汇总项目内每张造型卡被哪些镜头使用，供造型页一次性标注。"""
    entity_type_norm = normalize_entity_type(entity_type)
    spec = entity_spec(entity_type_norm)
    entity_ids = list(
        (await db.execute(select(spec.model.id).where(spec.model.project_id == project_id))).scalars().all()
    )
    usage_by_entity: dict[str, dict[str, dict[str, Any]]] = {str(entity_id): {} for entity_id in entity_ids}
    if not entity_ids:
        return []

    def add_usage(entity_id: str, shot_id: str, chapter_id: str, shot_index: int, title: str) -> None:
        if entity_id not in usage_by_entity:
            return
        usage_by_entity[entity_id][shot_id] = {
            "shot_id": shot_id,
            "chapter_id": chapter_id,
            "shot_index": shot_index,
            "title": title,
        }

    if entity_type_norm == "character":
        rows = (
            await db.execute(
                select(
                    ShotCharacterLink.character_id,
                    Shot.id,
                    Shot.chapter_id,
                    Shot.index,
                    Shot.title,
                )
                .join(Shot, Shot.id == ShotCharacterLink.shot_id)
                .join(Chapter, Chapter.id == Shot.chapter_id)
                .where(
                    ShotCharacterLink.character_id.in_(entity_ids),
                    Chapter.project_id == project_id,
                )
            )
        ).all()
        for entity_id, shot_id, chapter_id, shot_index, title in rows:
            add_usage(str(entity_id), str(shot_id), str(chapter_id), int(shot_index), str(title))
    elif entity_type_norm in LINK_MODEL_BY_ENTITY:
        link_model, asset_field = LINK_MODEL_BY_ENTITY[entity_type_norm]
        rows = (
            await db.execute(
                select(
                    getattr(link_model, asset_field),
                    Shot.id,
                    Shot.chapter_id,
                    Shot.index,
                    Shot.title,
                )
                .join(Shot, Shot.id == link_model.shot_id)
                .where(
                    getattr(link_model, asset_field).in_(entity_ids),
                    link_model.project_id == project_id,
                )
            )
        ).all()
        for entity_id, shot_id, chapter_id, shot_index, title in rows:
            add_usage(str(entity_id), str(shot_id), str(chapter_id), int(shot_index), str(title))

    if entity_type_norm == "scene":
        detail_rows = (
            await db.execute(
                select(
                    ShotDetail.scene_id,
                    Shot.id,
                    Shot.chapter_id,
                    Shot.index,
                    Shot.title,
                )
                .join(Shot, Shot.id == ShotDetail.id)
                .join(Chapter, Chapter.id == Shot.chapter_id)
                .where(
                    ShotDetail.scene_id.in_(entity_ids),
                    Chapter.project_id == project_id,
                )
            )
        ).all()
        for entity_id, shot_id, chapter_id, shot_index, title in detail_rows:
            add_usage(str(entity_id), str(shot_id), str(chapter_id), int(shot_index), str(title))

    return [
        {
            "entity_id": entity_id,
            "shots": sorted(shots.values(), key=lambda shot: (shot["chapter_id"], shot["shot_index"], shot["shot_id"])),
        }
        for entity_id, shots in usage_by_entity.items()
    ]


async def list_entities_paginated(
    db: AsyncSession,
    *,
    entity_type: str,
    q: str | None,
    style: str | None,
    visual_style: str | None,
    order: str | None,
    is_desc: bool,
    page: int,
    page_size: int,
    project_id: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    entity_type_norm = normalize_entity_type(entity_type)
    spec = entity_spec(entity_type_norm)
    stmt = select(spec.model)
    if project_id:
        # 项目级隔离：所有实体（角色/场景/道具/服装/演员）都按 project_id 过滤
        stmt = stmt.where(spec.model.project_id == project_id)
    stmt = apply_keyword_filter(stmt, q=q, fields=[spec.model.name, spec.model.description])
    if style:
        stmt = stmt.where(getattr(spec.model, "style") == style)
    if visual_style:
        stmt = stmt.where(getattr(spec.model, "visual_style") == visual_style)
    stmt = apply_order(
        stmt,
        model=spec.model,
        order=order,
        is_desc=is_desc,
        allow_fields=ENTITY_ORDER_FIELDS,
        default="created_at",
    )
    items, total = await paginate(db, stmt=stmt, page=page, page_size=page_size)

    thumbnails = await resolve_thumbnails(
        db,
        image_model=spec.image_model,
        parent_field_name=spec.id_field,
        parent_ids=[item.id for item in items],
    )
    payload: list[dict[str, Any]] = []
    for item in items:
        thumbnail = thumbnails.get(item.id, "")
        if entity_type_norm in {"actor", "character"}:
            read_model = spec.read_model
            payload.append(read_model.model_validate(item).model_copy(update={"thumbnail": thumbnail}).model_dump())
        else:
            payload.append(_asset_read_payload(item, thumbnail))
    return payload, total


async def create_entity(
    db: AsyncSession,
    *,
    entity_type: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    entity_type_norm = normalize_entity_type(entity_type)
    spec = entity_spec(entity_type_norm)
    parsed = spec.create_model.model_validate(body)
    data = parsed.model_dump()

    link_project_id: str | None = None
    link_chapter_id: str | None = None
    link_shot_id: str | None = None
    if entity_type_norm in LINK_MODEL_BY_ENTITY:
        # 项目级隔离：project_id 既写到实体本身（列），也用于建 link；仅 pop 掉实体无此列的 chapter/shot
        link_project_id = data.get("project_id")
        link_chapter_id = data.pop("chapter_id", None)
        link_shot_id = data.pop("shot_id", None)
    elif entity_type_norm == "character":
        link_project_id = data.get("project_id")
        link_chapter_id = data.pop("chapter_id", None)
        link_shot_id = data.pop("shot_id", None)

    exists = await db.get(spec.model, data["id"])
    if exists is not None:
        raise HTTPException(status_code=400, detail=entity_already_exists(spec.model.__name__))

    if entity_type_norm == "character":
        if await db.get(Project, data["project_id"]) is None:
            raise HTTPException(status_code=400, detail=entity_not_found("Project"))
        if data.get("actor_id") and await db.get(Actor, data["actor_id"]) is None:
            raise HTTPException(status_code=400, detail=entity_not_found("Actor"))
        if data.get("costume_id") and await db.get(Costume, data["costume_id"]) is None:
            raise HTTPException(status_code=400, detail=entity_not_found("Costume"))
        chapter: Chapter | None = None
        shot: Shot | None = None
        if link_chapter_id is not None:
            chapter = await db.get(Chapter, link_chapter_id)
            if chapter is None:
                raise HTTPException(status_code=400, detail=entity_not_found("Chapter"))
            if chapter.project_id != data["project_id"]:
                raise HTTPException(status_code=400, detail="Chapter does not belong to the same project")
        if link_shot_id is not None:
            shot = await db.get(Shot, link_shot_id)
            if shot is None:
                raise HTTPException(status_code=400, detail=entity_not_found("Shot"))
            shot_chapter = await db.get(Chapter, shot.chapter_id)
            if shot_chapter is None:
                raise HTTPException(status_code=400, detail=f"{entity_not_found('Chapter')} for shot")
            if shot_chapter.project_id != data["project_id"]:
                raise HTTPException(status_code=400, detail="Shot does not belong to the same project")
            if chapter is not None and shot.chapter_id != chapter.id:
                raise HTTPException(status_code=400, detail="Shot does not belong to the specified chapter")

    obj = spec.model(**data)
    db.add(obj)
    await db.flush()
    await db.refresh(obj)

    if entity_type_norm in {"actor", "scene", "prop", "costume"}:
        count = int(getattr(obj, "view_count", 1) or 1)
        angles = list(DEFAULT_VIEW_ANGLES[: min(max(count, 0), len(DEFAULT_VIEW_ANGLES))])
        for angle in angles:
            db.add(spec.image_model(**{spec.id_field: obj.id, "view_angle": angle}))
        if angles:
            await db.flush()

    if link_project_id is not None and entity_type_norm in LINK_MODEL_BY_ENTITY:
        link_model, asset_field = LINK_MODEL_BY_ENTITY[entity_type_norm]
        await upsert_project_link(
            db,
            model=link_model,
            asset_field=asset_field,  # type: ignore[arg-type]
            asset_id=obj.id,
            project_id=link_project_id,
            chapter_id=link_chapter_id,
            shot_id=link_shot_id,
        )

    if entity_type_norm == "character" and link_shot_id is not None:
        existing_indexes_stmt = (
            select(ShotCharacterLink.index)
            .where(ShotCharacterLink.shot_id == link_shot_id)
            .order_by(ShotCharacterLink.index.desc())
            .limit(1)
        )
        max_index = (await db.execute(existing_indexes_stmt)).scalars().first()
        await upsert_shot_character_link(
            db,
            body=ShotCharacterLinkCreate(
                shot_id=link_shot_id,
                character_id=obj.id,
                index=(max_index if isinstance(max_index, int) else -1) + 1,
                note="",
            ),
        )

    if entity_type_norm in {"actor", "character"}:
        read_model = spec.read_model
        payload = read_model.model_validate(obj).model_dump()
        payload["thumbnail"] = ""
        return payload
    return _asset_read_payload(obj, "")


async def get_entity(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
) -> dict[str, Any]:
    entity_type_norm = normalize_entity_type(entity_type)
    spec = entity_spec(entity_type_norm)
    obj = await db.get(spec.model, entity_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=entity_not_found(spec.model.__name__))

    thumbnails = await resolve_thumbnails(
        db,
        image_model=spec.image_model,
        parent_field_name=spec.id_field,
        parent_ids=[entity_id],
    )
    thumbnail = thumbnails.get(entity_id, "")
    if entity_type_norm in {"actor", "character"}:
        read_model = spec.read_model
        return read_model.model_validate(obj).model_copy(update={"thumbnail": thumbnail}).model_dump()
    return _asset_read_payload(obj, thumbnail)


async def update_entity(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    entity_type_norm = normalize_entity_type(entity_type)
    spec = entity_spec(entity_type_norm)
    obj = await db.get(spec.model, entity_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=entity_not_found(spec.model.__name__))

    update_data = spec.update_model.model_validate(body).model_dump(exclude_unset=True)
    if entity_type_norm == "character":
        if "project_id" in update_data and await db.get(Project, update_data["project_id"]) is None:
            raise HTTPException(status_code=400, detail=entity_not_found("Project"))
        if "actor_id" in update_data and update_data["actor_id"] is not None and await db.get(Actor, update_data["actor_id"]) is None:
            raise HTTPException(status_code=400, detail=entity_not_found("Actor"))
        if "costume_id" in update_data and update_data["costume_id"] is not None and await db.get(Costume, update_data["costume_id"]) is None:
            raise HTTPException(status_code=400, detail=entity_not_found("Costume"))

    for key, value in update_data.items():
        setattr(obj, key, value)
    await db.flush()
    await db.refresh(obj)
    if "name" in update_data:
        await sync_entity_image_file_names(db, entity_type=entity_type_norm, entity_id=entity_id)
        await db.flush()

    if entity_type_norm in {"actor", "character"}:
        read_model = spec.read_model
        payload = read_model.model_validate(obj).model_dump()
        payload["thumbnail"] = ""
        return payload
    return _asset_read_payload(obj, "")


async def delete_entity(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
) -> dict[str, Any]:
    """删除资产；派生状态先把所有镜头引用安全回退到对应基准资产。"""
    entity_type_norm = normalize_entity_type(entity_type)
    spec = entity_spec(entity_type_norm)
    obj = await db.get(spec.model, entity_id)
    if obj is None:
        return {
            "deleted_entity_id": entity_id,
            "fallback_entity_id": None,
            "fallback_entity_name": None,
            "reassigned_shot_count": 0,
        }

    fallback_entity_id: str | None = None
    fallback_entity_name: str | None = None
    affected_shot_ids: set[str] = set()
    fallback_name = _derived_base_name(getattr(obj, "description", ""))
    if fallback_name:
        fallback = (
            await db.execute(
                select(spec.model).where(
                    spec.model.project_id == obj.project_id,
                    spec.model.name == fallback_name,
                )
            )
        ).scalars().first()
        if fallback is None or fallback.id == entity_id:
            raise HTTPException(status_code=409, detail="派生状态的基准造型不存在，无法安全删除")
        fallback_entity_id = str(fallback.id)
        fallback_entity_name = str(fallback.name)
        if entity_type_norm == "character":
            affected_shot_ids = await _replace_character_links(
                db,
                entity_id=entity_id,
                fallback_entity_id=fallback_entity_id,
            )
        else:
            affected_shot_ids = await _replace_project_asset_links(
                db,
                entity_type=entity_type_norm,
                entity_id=entity_id,
                fallback_entity_id=fallback_entity_id,
            )
            if entity_type_norm == "scene":
                details = list(
                    (await db.execute(select(ShotDetail).where(ShotDetail.scene_id == entity_id))).scalars().all()
                )
                for detail in details:
                    detail.scene_id = fallback_entity_id
                    affected_shot_ids.add(str(detail.id))
        await _replace_extracted_candidate_links(
            db,
            entity_type=entity_type_norm,
            entity_id=entity_id,
            fallback_entity_id=fallback_entity_id,
        )
    # 先显式删除图片槽位，再由数据库外键清理其余关联。这样即使历史 SQLite
    # 连接未开启 foreign_keys，也不会留下阻塞同 ID 资产重建的孤立槽位。
    await db.execute(
        delete(spec.image_model).where(getattr(spec.image_model, spec.id_field) == entity_id)
    )
    await db.delete(obj)
    await db.flush()
    return {
        "deleted_entity_id": entity_id,
        "fallback_entity_id": fallback_entity_id,
        "fallback_entity_name": fallback_entity_name,
        "reassigned_shot_count": len(affected_shot_ids),
    }
