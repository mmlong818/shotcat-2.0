"""项目参考资产轨：版本登记、采用和锁定。"""

from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.studio import AssetReferenceVersion, FileItem
from app.schemas.studio.asset_references import AssetReferenceCreate, AssetReferenceUpdate
from app.services.studio.entity_specs import entity_spec, normalize_entity_type


async def _require_project_entity(
    db: AsyncSession, *, project_id: str, entity_type: str, entity_id: str
):
    spec = entity_spec(entity_type)
    entity = await db.get(spec.model, entity_id)
    if entity is None or getattr(entity, "project_id", None) != project_id:
        raise HTTPException(status_code=404, detail="项目资产不存在")
    return entity


async def register_asset_reference(
    db: AsyncSession, *, project_id: str, body: AssetReferenceCreate
) -> AssetReferenceVersion:
    entity_type = normalize_entity_type(body.entity_type)
    entity = await _require_project_entity(
        db, project_id=project_id, entity_type=entity_type, entity_id=body.entity_id
    )
    if await db.get(FileItem, body.file_id) is None:
        raise HTTPException(status_code=404, detail="参考图片文件不存在")

    latest = int((await db.execute(select(func.max(AssetReferenceVersion.version)).where(
        AssetReferenceVersion.project_id == project_id,
        AssetReferenceVersion.entity_type == entity_type,
        AssetReferenceVersion.entity_id == body.entity_id,
    ))).scalar() or 0)
    locked_adopted = (await db.execute(select(AssetReferenceVersion.id).where(
        AssetReferenceVersion.project_id == project_id,
        AssetReferenceVersion.entity_type == entity_type,
        AssetReferenceVersion.entity_id == body.entity_id,
        AssetReferenceVersion.is_adopted.is_(True),
        AssetReferenceVersion.is_locked.is_(True),
    ).limit(1))).scalar_one_or_none()
    should_adopt = bool(body.adopt or body.lock or locked_adopted is None)
    if should_adopt:
        await db.execute(update(AssetReferenceVersion).where(
            AssetReferenceVersion.project_id == project_id,
            AssetReferenceVersion.entity_type == entity_type,
            AssetReferenceVersion.entity_id == body.entity_id,
        ).values(is_adopted=False))

    row = AssetReferenceVersion(
        id=f"assetref_{uuid4().hex}", project_id=project_id,
        entity_type=entity_type, entity_id=body.entity_id, image_id=body.image_id,
        file_id=body.file_id,
        display_name=(body.display_name or getattr(entity, "name", "参考设计")).strip(),
        version=latest + 1, source=body.source,
        is_adopted=should_adopt, is_locked=bool(body.lock),
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


async def list_asset_references(
    db: AsyncSession, *, project_id: str, entity_type: str | None = None, q: str | None = None
) -> list[AssetReferenceVersion]:
    stmt = select(AssetReferenceVersion).where(AssetReferenceVersion.project_id == project_id)
    if entity_type:
        stmt = stmt.where(AssetReferenceVersion.entity_type == normalize_entity_type(entity_type))
    if q and q.strip():
        stmt = stmt.where(AssetReferenceVersion.display_name.ilike(f"%{q.strip()}%"))
    return list((await db.execute(stmt.order_by(
        AssetReferenceVersion.is_adopted.desc(),
        AssetReferenceVersion.is_locked.desc(),
        AssetReferenceVersion.updated_at.desc(),
    ))).scalars().all())


async def update_asset_reference(
    db: AsyncSession, *, project_id: str, reference_id: str, body: AssetReferenceUpdate
) -> AssetReferenceVersion:
    row = await db.get(AssetReferenceVersion, reference_id)
    if row is None or row.project_id != project_id:
        raise HTTPException(status_code=404, detail="参考版本不存在")
    patch = body.model_dump(exclude_unset=True)
    if patch.get("is_locked") is True:
        patch["is_adopted"] = True
    if patch.get("is_adopted") is True:
        await db.execute(update(AssetReferenceVersion).where(
            AssetReferenceVersion.project_id == project_id,
            AssetReferenceVersion.entity_type == row.entity_type,
            AssetReferenceVersion.entity_id == row.entity_id,
            AssetReferenceVersion.id != row.id,
        ).values(is_adopted=False, is_locked=False))
    for key, value in patch.items():
        if value is not None:
            setattr(row, key, value.strip() if key == "display_name" else value)
    await db.flush()
    await db.refresh(row)
    return row


async def adopted_reference_map(
    db: AsyncSession, *, project_id: str, entities: list[tuple[str, str]]
) -> dict[tuple[str, str], AssetReferenceVersion]:
    if not entities:
        return {}
    rows = (await db.execute(select(AssetReferenceVersion).where(
        AssetReferenceVersion.project_id == project_id,
        AssetReferenceVersion.is_adopted.is_(True),
    ))).scalars().all()
    wanted = set(entities)
    return {(row.entity_type, row.entity_id): row for row in rows if (row.entity_type, row.entity_id) in wanted}


__all__ = [
    "adopted_reference_map", "list_asset_references",
    "register_asset_reference", "update_asset_reference",
]
