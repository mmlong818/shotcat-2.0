from __future__ import annotations

import re

from app.models.studio import ShotFrameType
from app.schemas.studio.shots import ShotFramePromptMappingRead, ShotLinkedAssetItem
from app.services.studio.generation.shared.types import GenerationContext


def _clean_reference_name(name: str | None, fallback: str) -> str:
    value = str(name or "").strip() or fallback
    value = re.sub(r"[-－_ ]?默认服装[（(][^）)]+[）)]", "", value)
    for token in ("-默认服装", "－默认服装", "_默认服装", " 默认服装", "默认服装"):
        value = value.replace(token, "")
    return value.strip(" -_－") or fallback


def _is_generic_crowd_character(name: str | None) -> bool:
    value = str(name or "").strip()
    if not value:
        return False
    generic_names = {
        "学生们",
        "同学们",
        "前排学生们",
        "后排学生们",
        "路人",
        "路人们",
        "人群",
        "群众",
        "围观者",
        "其他学生",
        "其他同学",
    }
    if value in generic_names:
        return True
    return bool(re.fullmatch(r"(前排|后排|周围|旁边|附近)?(学生|同学|路人|群众|人群|观众|乘客|行人)们?", value))


def build_ordered_shot_frame_references(
    *,
    items: list[ShotLinkedAssetItem],
) -> list[ShotFramePromptMappingRead]:
    """按请求入参顺序构造稳定的图片映射关系。"""
    mappings: list[ShotFramePromptMappingRead] = []
    seen_file_ids: set[str] = set()
    for item in items or []:
        file_id = (item.file_id or "").strip()
        if str(item.type) == "character" and _is_generic_crowd_character(item.name):
            continue
        if not file_id or file_id in seen_file_ids:
            continue
        seen_file_ids.add(file_id)
        mappings.append(
            ShotFramePromptMappingRead(
                token=f"图{len(mappings) + 1}",
                type=item.type,
                id=item.id,
                name=_clean_reference_name(item.name, item.id),
                file_id=file_id,
            )
        )
    return mappings


class FrameGenerationContext(GenerationContext):
    """分镜帧图片生成的动态上下文。"""

    kind: str = "frame"
    shot_id: str
    frame_type: ShotFrameType
    images: list[ShotLinkedAssetItem]
    ordered_refs: list[ShotFramePromptMappingRead]


def build_frame_context(
    *,
    shot_id: str,
    frame_type: ShotFrameType,
    items: list[ShotLinkedAssetItem],
) -> FrameGenerationContext:
    return FrameGenerationContext(
        shot_id=shot_id,
        frame_type=frame_type,
        images=items or [],
        ordered_refs=build_ordered_shot_frame_references(items=items),
    )

