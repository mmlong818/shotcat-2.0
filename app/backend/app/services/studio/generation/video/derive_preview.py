from __future__ import annotations

from app.schemas.studio.shots import ShotVideoPromptPackRead, ShotVideoPromptPreviewRead, VideoExecutionPlanRead
from app.services.studio.generation.shared.types import GenerationDerivedPreview
from app.services.studio.generation.video.build_base import VideoBaseDraft
from app.services.studio.generation.video.build_context import VideoGenerationContext
from app.services.studio.generation.video.execution_plan import (
    build_video_execution_plan,
    enrich_prompt_with_execution_plan,
)
from app.services.studio.shot_video_prompt_pack import (
    _fallback_video_prompt,
    _pack_variables,
    _render_template,
    _resolve_video_prompt_template,
    build_shot_video_prompt_pack,
    enrich_rendered_video_prompt,
)


class VideoDerivedPreview(GenerationDerivedPreview):
    """视频生成预览结果。"""

    kind: str = "video"
    shot_id: str
    reference_mode: str
    rendered_prompt: str
    images: list[str]
    pack: ShotVideoPromptPackRead
    execution_plan: VideoExecutionPlanRead
    template_id: str | None = None
    template_name: str | None = None


async def derive_video_preview(
    db,
    *,
    base: VideoBaseDraft,
    context: VideoGenerationContext,
) -> VideoDerivedPreview:
    pack = await build_shot_video_prompt_pack(db, shot_id=base.shot_id)
    execution_plan = build_video_execution_plan(
        pack=pack,
        reference_mode=context.reference_mode,
        images=context.images,
    )
    if base.prompt:
        rendered_prompt = enrich_rendered_video_prompt(
            rendered_prompt=base.prompt,
            pack=pack,
        )
        rendered_prompt = enrich_prompt_with_execution_plan(
            rendered_prompt=rendered_prompt,
            plan=execution_plan,
        )
        return VideoDerivedPreview(
            shot_id=base.shot_id,
            reference_mode=context.reference_mode,
            rendered_prompt=rendered_prompt,
            images=context.images,
            pack=pack,
            execution_plan=execution_plan,
            template_id=context.template_id,
            template_name=None,
            warnings=[],
        )

    template = await _resolve_video_prompt_template(db, template_id=context.template_id)
    warnings: list[str] = []
    if template is None:
        warnings.append("未配置视频提示词模板，已使用系统默认拼装提示词")
        rendered_prompt = _fallback_video_prompt(pack)
    else:
        rendered_prompt = _render_template(template.content, _pack_variables(pack))
        if not rendered_prompt:
            warnings.append("视频提示词模板渲染结果为空，已使用系统默认拼装提示词")
            rendered_prompt = _fallback_video_prompt(pack)
        else:
            rendered_prompt = enrich_rendered_video_prompt(
                rendered_prompt=rendered_prompt,
                pack=pack,
            )

    rendered_prompt = enrich_prompt_with_execution_plan(
        rendered_prompt=rendered_prompt,
        plan=execution_plan,
    )

    return VideoDerivedPreview(
        shot_id=base.shot_id,
        reference_mode=context.reference_mode,
        rendered_prompt=rendered_prompt.strip(),
        images=context.images,
        pack=pack,
        execution_plan=execution_plan,
        template_id=template.id if template else None,
        template_name=template.name if template else None,
        warnings=warnings,
    )


def to_shot_video_prompt_preview_read(
    *,
    derived: VideoDerivedPreview,
) -> ShotVideoPromptPreviewRead:
    return ShotVideoPromptPreviewRead(
        shot_id=derived.shot_id,
        template_id=derived.template_id,
        template_name=derived.template_name,
        rendered_prompt=derived.rendered_prompt,
        pack=derived.pack,
        execution_plan=derived.execution_plan,
        warnings=derived.warnings,
    )
