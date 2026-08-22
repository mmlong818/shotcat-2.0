from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.schemas.common import ApiResponse, created_response, success_response
from app.schemas.studio.asset_references import (
    AssetReferenceCreate, AssetReferenceRead, AssetReferenceUpdate,
)
from app.services.studio.asset_references import (
    list_asset_references, register_asset_reference, update_asset_reference,
)

router = APIRouter()


@router.get("", response_model=ApiResponse[list[AssetReferenceRead]], summary="读取项目参考资产轨")
async def list_references(
    project_id: str = Query(..., min_length=1),
    entity_type: str | None = Query(None),
    q: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[AssetReferenceRead]]:
    rows = await list_asset_references(db, project_id=project_id, entity_type=entity_type, q=q)
    return success_response([AssetReferenceRead.model_validate(row) for row in rows])


@router.post("", response_model=ApiResponse[AssetReferenceRead], status_code=status.HTTP_201_CREATED, summary="登记参考资产版本")
async def create_reference(
    project_id: str,
    body: AssetReferenceCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AssetReferenceRead]:
    row = await register_asset_reference(db, project_id=project_id, body=body)
    return created_response(AssetReferenceRead.model_validate(row))


@router.patch("/{reference_id}", response_model=ApiResponse[AssetReferenceRead], summary="命名、采用或锁定参考版本")
async def patch_reference(
    reference_id: str,
    project_id: str,
    body: AssetReferenceUpdate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AssetReferenceRead]:
    row = await update_asset_reference(db, project_id=project_id, reference_id=reference_id, body=body)
    return success_response(AssetReferenceRead.model_validate(row))
