"""镜头对白服务：ShotDialogLine 的分页查询与 CRUD。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.utils import apply_keyword_filter, apply_order, paginate
from app.models.studio import Character, ShotDetail, ShotDialogLine
from app.schemas.common import ApiResponse, PaginatedData, paginated_response
from app.schemas.studio.shots import ShotDialogLineCreate, ShotDialogLineRead, ShotDialogLineUpdate
from app.services.studio.shot_extracted_dialogue_candidates import mark_pending_by_linked_dialog_line
from app.services.common import (
    create_and_refresh,
    entity_not_found,
    flush_and_refresh,
    get_or_404,
    patch_model,
    require_entity,
    require_optional_entity,
)


async def list_paginated(
    db: AsyncSession,
    *,
    shot_detail_id: str | None,
    q: str | None,
    order: str | None,
    is_desc: bool,
    page: int,
    page_size: int,
    allow_fields: set[str],
) -> ApiResponse[PaginatedData[ShotDialogLineRead]]:
    """分页查询镜头对白。"""
    stmt = select(ShotDialogLine)
    if shot_detail_id is not None:
        stmt = stmt.where(ShotDialogLine.shot_detail_id == shot_detail_id)
    stmt = apply_keyword_filter(stmt, q=q, fields=[ShotDialogLine.text])
    stmt = apply_order(
        stmt,
        model=ShotDialogLine,
        order=order,
        is_desc=is_desc,
        allow_fields=allow_fields,
        default="index",
    )
    items, total = await paginate(db, stmt=stmt, page=page, page_size=page_size)
    return paginated_response(
        [ShotDialogLineRead.model_validate(x) for x in items],
        page=page,
        page_size=page_size,
        total=total,
    )


async def list_by_shot(
    db: AsyncSession,
    *,
    shot_id: str,
) -> list[ShotDialogLine]:
    """按镜头读取全部已保存对白，供准备页聚合状态复用。"""
    stmt = (
        select(ShotDialogLine)
        .where(ShotDialogLine.shot_detail_id == shot_id)
        .order_by(ShotDialogLine.index.asc(), ShotDialogLine.id.asc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def create(
    db: AsyncSession,
    *,
    body: ShotDialogLineCreate,
) -> ShotDialogLine:
    """创建镜头对白。"""
    await require_entity(db, ShotDetail, body.shot_detail_id, detail=entity_not_found("ShotDetail"), status_code=400)
    await require_optional_entity(
        db, Character, body.speaker_character_id, detail=entity_not_found("Character"), status_code=400
    )
    await require_optional_entity(
        db, Character, body.target_character_id, detail=entity_not_found("Character"), status_code=400
    )
    return await create_and_refresh(db, ShotDialogLine(**body.model_dump()))


async def update(
    db: AsyncSession,
    *,
    line_id: int,
    body: ShotDialogLineUpdate,
) -> ShotDialogLine:
    """更新镜头对白。"""
    obj = await get_or_404(db, ShotDialogLine, line_id, detail=entity_not_found("ShotDialogLine"))
    update_data = body.model_dump(exclude_unset=True)
    if "speaker_character_id" in update_data:
        await require_optional_entity(
            db, Character, update_data["speaker_character_id"], detail=entity_not_found("Character"), status_code=400
        )
    if "target_character_id" in update_data:
        await require_optional_entity(
            db, Character, update_data["target_character_id"], detail=entity_not_found("Character"), status_code=400
        )
    patch_model(obj, update_data)
    return await flush_and_refresh(db, obj)


async def delete(
    db: AsyncSession,
    *,
    line_id: int,
) -> None:
    """删除镜头对白。"""
    obj = await db.get(ShotDialogLine, line_id)
    if obj is None:
        return None
    await mark_pending_by_linked_dialog_line(db, dialog_line_id=obj.id)
    await db.delete(obj)
    await db.flush()
    return None
