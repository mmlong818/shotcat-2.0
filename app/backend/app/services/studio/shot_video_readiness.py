"""镜头视频生成准备度聚合服务。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm import Model, ModelCategoryKey, ModelSettings, Provider
from app.models.studio import (
    Shot,
    ShotCandidateStatus,
    ShotDialogueCandidateStatus,
    ShotDetail,
    ShotExtractedCandidate,
    ShotExtractedDialogueCandidate,
    ShotFrameType,
    ShotFrameImage,
)
from app.models.task import GenerationTask, GenerationTaskStatus
from app.models.task_links import GenerationTaskLink
from app.schemas.studio.shots import ShotVideoReadinessCheck, ShotVideoReadinessRead
from app.bootstrap import bootstrap_all_registries
from app.core.integrations.video_capabilities import resolve_video_capability
from app.services.common import entity_not_found
from app.services.llm.provider_registry import resolve_provider_key_from_name
from app.services.studio.generation.video import (
    build_video_base_draft,
    build_video_context,
    derive_video_preview,
)


REQUIRED_FRAMES_BY_MODE: dict[str, tuple[ShotFrameType, ...]] = {
    "first": (ShotFrameType.first,),
    "last": (ShotFrameType.last,),
    "key": (ShotFrameType.key,),
    "first_last": (ShotFrameType.first, ShotFrameType.last),
    "first_last_key": (ShotFrameType.first, ShotFrameType.last, ShotFrameType.key),
    "text_only": (),
}

_ACTIVE_TASK_STATUSES = (
    GenerationTaskStatus.pending,
    GenerationTaskStatus.running,
    GenerationTaskStatus.streaming,
)


def _check(key: str, ok: bool, message: str) -> ShotVideoReadinessCheck:
    return ShotVideoReadinessCheck(key=key, ok=ok, message=message)


async def _count_pending_candidates(db: AsyncSession, *, shot_id: str) -> tuple[int, int]:
    asset_stmt = (
        select(func.count(ShotExtractedCandidate.id))
        .where(ShotExtractedCandidate.shot_id == shot_id)
        .where(ShotExtractedCandidate.candidate_status == ShotCandidateStatus.pending)
    )
    dialogue_stmt = (
        select(func.count(ShotExtractedDialogueCandidate.id))
        .where(ShotExtractedDialogueCandidate.shot_id == shot_id)
        .where(ShotExtractedDialogueCandidate.candidate_status == ShotDialogueCandidateStatus.pending)
    )
    return int(await db.scalar(asset_stmt) or 0), int(await db.scalar(dialogue_stmt) or 0)


async def _has_active_video_task(db: AsyncSession, *, shot_id: str) -> bool:
    stmt = (
        select(func.count(GenerationTask.id))
        .select_from(GenerationTaskLink)
        .join(GenerationTask, GenerationTask.id == GenerationTaskLink.task_id)
        .where(GenerationTaskLink.resource_type == "video")
        .where(GenerationTaskLink.relation_type == "video")
        .where(GenerationTaskLink.relation_entity_id == shot_id)
        .where(GenerationTask.status.in_(_ACTIVE_TASK_STATUSES))
    )
    return bool(await db.scalar(stmt))


async def _reference_frames_ready(
    db: AsyncSession,
    *,
    shot_id: str,
    reference_mode: str,
) -> ShotVideoReadinessCheck:
    required_frames = REQUIRED_FRAMES_BY_MODE.get(reference_mode)
    if required_frames is None:
        return _check("reference_frames_ready", False, f"未知参考模式：{reference_mode}")
    if not required_frames:
        return _check("reference_frames_ready", True, "当前参考模式不需要参考帧")

    stmt = select(ShotFrameImage).where(
        ShotFrameImage.shot_detail_id == shot_id,
        ShotFrameImage.frame_type.in_(required_frames),
    )
    rows = (await db.execute(stmt)).scalars().all()
    frame_map = {row.frame_type: row for row in rows}
    missing = [frame.value for frame in required_frames if not frame_map.get(frame) or not frame_map[frame].file_id]
    if missing:
        return _check("reference_frames_ready", False, f"缺少参考帧：{', '.join(missing)}")
    return _check("reference_frames_ready", True, "参考帧已就绪")


async def _video_model_and_provider_ready(
    db: AsyncSession,
    *,
    reference_mode: str,
    duration: int,
) -> tuple[ShotVideoReadinessCheck, ShotVideoReadinessCheck, ShotVideoReadinessCheck]:
    settings = await db.get(ModelSettings, 1)
    model_id = settings.default_video_model_id if settings else None
    if not model_id:
        return (
            _check("video_model_ready", False, "未配置默认视频模型"),
            _check("provider_ready", False, "未配置默认视频模型，无法检查供应商"),
            _check("model_constraints_ready", False, "未配置默认视频模型，无法检查生成规格"),
        )
    model = await db.get(Model, model_id)
    if model is None:
        return (
            _check("video_model_ready", False, f"默认视频模型不存在：{model_id}"),
            _check("provider_ready", False, "默认视频模型不存在，无法检查供应商"),
            _check("model_constraints_ready", False, "默认视频模型不存在，无法检查生成规格"),
        )
    if model.category != ModelCategoryKey.video:
        return (
            _check("video_model_ready", False, f"默认模型不是视频类别：{model_id}"),
            _check("provider_ready", False, "默认模型不是视频类别，无法检查供应商"),
            _check("model_constraints_ready", False, "默认模型类别错误，无法检查生成规格"),
        )
    provider = await db.get(Provider, model.provider_id)
    if provider is None:
        return (
            _check("video_model_ready", True, "默认视频模型可用"),
            _check("provider_ready", False, f"视频模型供应商不存在：{model.provider_id}"),
            _check("model_constraints_ready", False, "视频模型供应商不存在，无法检查生成规格"),
        )
    if not (provider.api_key or "").strip():
        return (
            _check("video_model_ready", True, "默认视频模型可用"),
            _check("provider_ready", False, f"视频模型供应商缺少 api_key：{provider.id}"),
            _check("model_constraints_ready", False, "供应商连接未完成，无法检查生成规格"),
        )
    bootstrap_all_registries()
    try:
        provider_key = resolve_provider_key_from_name(provider.name)
        capability = resolve_video_capability(provider=provider_key, model=model.name)
    except Exception as exc:  # noqa: BLE001
        return (
            _check("video_model_ready", True, "默认视频模型可用"),
            _check("provider_ready", False, f"视频模型供应商无法解析：{exc}"),
            _check("model_constraints_ready", False, "无法读取当前模型的生成规格"),
        )

    problems: list[str] = []
    if capability.supported_reference_modes is not None and reference_mode not in capability.supported_reference_modes:
        problems.append(f"不支持参考方式 {reference_mode}")
    if duration > 0 and capability.min_seconds is not None and duration < capability.min_seconds:
        problems.append(f"时长不能少于 {capability.min_seconds} 秒")
    if duration > 0 and capability.max_seconds is not None and duration > capability.max_seconds:
        problems.append(f"时长不能超过 {capability.max_seconds} 秒")
    return (
        _check("video_model_ready", True, "默认视频模型可用"),
        _check("provider_ready", True, "视频模型供应商可用"),
        _check(
            "model_constraints_ready",
            not problems,
            "当前参考方式和时长符合模型要求" if not problems else "；".join(problems),
        ),
    )


async def get_shot_video_readiness(
    db: AsyncSession,
    *,
    shot_id: str,
    reference_mode: str,
) -> ShotVideoReadinessRead:
    """实时聚合镜头视频生成准备度，不写入数据库状态。"""
    shot = await db.get(Shot, shot_id)
    if shot is None:
        raise ValueError(entity_not_found("Shot"))
    detail = await db.get(ShotDetail, shot_id)

    pending_assets, pending_dialogues = await _count_pending_candidates(db, shot_id=shot_id)
    extraction_ok = bool(shot.skip_extraction) or (
        shot.last_extracted_at is not None and pending_assets == 0 and pending_dialogues == 0
    )
    if extraction_ok:
        extraction_msg = "信息提取确认已完成" if not shot.skip_extraction else "当前镜头已标记为无需提取"
    else:
        extraction_msg = f"仍有待确认项：资产 {pending_assets} 项，对白 {pending_dialogues} 项"

    if detail is None:
        duration_check = _check("duration_ready", False, "缺少镜头详情，无法读取时长")
    else:
        duration = int(detail.duration or 0)
        duration_check = _check(
            "duration_ready",
            duration > 0,
            "镜头时长已配置" if duration > 0 else "请先配置镜头时长",
        )

    try:
        preview = await derive_video_preview(
            db,
            base=build_video_base_draft(shot_id=shot_id, prompt=None),
            context=await build_video_context(
                db,
                shot_id=shot_id,
                reference_mode="text_only",
                images=[],
            ),
        )
        prompt_ok = bool(preview.rendered_prompt.strip())
        prompt_message = "视频提示词可用" if prompt_ok else "视频提示词为空"
    except Exception as exc:  # noqa: BLE001
        prompt_ok = False
        prompt_message = f"视频提示词渲染失败：{exc}"

    active_video_task = await _has_active_video_task(db, shot_id=shot_id)
    duration = int(detail.duration or 0) if detail is not None else 0
    model_check, provider_check, constraints_check = await _video_model_and_provider_ready(
        db,
        reference_mode=reference_mode,
        duration=duration,
    )
    checks = [
        _check("extraction_ready", extraction_ok, extraction_msg),
        duration_check,
        _check("prompt_ready", prompt_ok, prompt_message),
        await _reference_frames_ready(db, shot_id=shot_id, reference_mode=reference_mode),
        model_check,
        provider_check,
        constraints_check,
        _check(
            "no_active_video_task",
            not active_video_task,
            "当前没有进行中的视频任务" if not active_video_task else "当前已有视频生成任务进行中",
        ),
    ]
    return ShotVideoReadinessRead(
        shot_id=shot_id,
        reference_mode=reference_mode,
        ready=all(item.ok for item in checks),
        checks=checks,
    )
