from __future__ import annotations

from app.services.studio.generation.asset_image.build_base import AssetImageBaseDraft
from app.services.studio.generation.asset_image.build_context import AssetImageContext
from app.services.studio.generation.shared.types import GenerationDerivedPreview


class AssetImageDerivedPreview(GenerationDerivedPreview):
    """资产图片生成预览。"""

    kind: str = "asset_image"
    entity_type: str
    entity_id: str
    relation_type: str
    relation_entity_id: str
    prompt: str
    images: list[str]


def derive_asset_image_preview(
    *,
    base: AssetImageBaseDraft,
    context: AssetImageContext,
) -> AssetImageDerivedPreview:
    return AssetImageDerivedPreview(
        entity_type=base.entity_type,
        entity_id=base.entity_id,
        relation_type=base.relation_type,
        relation_entity_id=base.relation_entity_id,
        prompt=(base.prompt or "").strip(),
        images=context.images,
    )

