from __future__ import annotations

"""资产与镜头相关的图片生成任务 API。

通过 TaskManager 调用 `ImageGenerationTask`，并使用 `GenerationTaskLink`
将任务与上层业务实体（演员形象/道具/场景/服装/角色/镜头分镜帧）建立关联。
"""

import asyncio
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.contracts.image_generation import ImageResolutionProfile, ImageTargetRatio
from app.core.db import async_session_maker
from app.core.task_manager import DeliveryMode, SqlAlchemyTaskStore, TaskManager
from app.core.task_manager.types import TaskStatus
from app.dependencies import get_db
from app.models.studio import (
    ActorImage,
    CharacterImage,
    CostumeImage,
    PropImage,
    SceneImage,
    Shot,
    ShotDetail,
    ShotFrameType,
    ShotFrameImage,
)
from app.schemas.common import ApiResponse, created_response, success_response
from app.schemas.studio.shots import RenderedShotFramePromptRead, ShotLinkedAssetItem
from app.api.v1.routes.film.common import TaskCreated, _CreateOnlyTask
from app.models.task_links import GenerationTaskLink
from app.services.studio.image_task_references import (
    resolve_reference_image_refs_by_file_ids as _resolve_reference_image_refs_by_file_ids_service,
)
from app.services.studio.generation.asset_image import (
    build_actor_image_base_draft as _build_actor_image_base_draft_service,
    build_actor_image_submission_payload as _build_actor_image_submission_payload_service,
    build_asset_image_base_draft as _build_asset_image_base_draft_service,
    build_asset_image_context as _build_asset_image_context_service,
    build_asset_image_submission_payload as _build_asset_image_submission_payload_service,
    build_character_image_base_draft as _build_character_image_base_draft_service,
    build_character_image_submission_payload as _build_character_image_submission_payload_service,
    derive_asset_image_preview as _derive_asset_image_preview_service,
)
from app.services.studio.generation.frame import (
    build_frame_base_draft as _build_frame_base_draft_service,
    build_frame_context as _build_frame_context_service,
    build_frame_submission_payload as _build_frame_submission_payload_service,
    derive_frame_preview as _derive_frame_preview_service,
)
from app.services.film.shot_frame_prompt_tasks import (
    build_run_args as _build_shot_frame_prompt_run_args_service,
    normalize_frame_type as _normalize_frame_type_service,
    persist_frame_prompt as _persist_frame_prompt_service,
    read_saved_frame_prompt as _read_saved_frame_prompt_service,
    relation_type_for_frame as _relation_type_for_frame_service,
    resolve_batch_frame_prompt as _resolve_batch_frame_prompt_service,
)
from app.services.studio.shot_status import mark_shot_generating as _mark_shot_generating_service
from app.services.studio.generation.frame.derive_preview import (
    to_rendered_shot_frame_prompt_read as _to_rendered_shot_frame_prompt_read_service,
)
from app.services.studio.image_task_runner import create_image_task_and_link as _create_image_task_and_link_service
from app.tasks.execute_task import enqueue_task_execution, revoke_task_execution


router = APIRouter()


_BATCH_LOCK = threading.Lock()
_ASSET_IMAGE_BATCHES: dict[str, dict] = {}
_FRAME_IMAGE_BATCHES: dict[str, dict] = {}
_TERMINAL_TASK_STATUSES = {TaskStatus.succeeded, TaskStatus.failed, TaskStatus.cancelled}


def _scene_empty_prompt(prompt: str) -> str:
    text = prompt.strip()
    if not text:
        return text
    if "空无一人" in text or "无人" in text:
        return text
    return f"空无一人的{text}"


class StudioImageTaskRequest(BaseModel):
    """Studio 专用图片任务请求体：可选模型 ID，不传则用默认图片模型；供应商由模型反查。

    image_id 表示具体的图片模型 ID，例如：
    - 演员图片：ActorImage.id
    - 场景图片：SceneImage.id
    - 道具图片：PropImage.id
    - 服装图片：CostumeImage.id
    - 角色图片：CharacterImage.id
    - 分镜帧图片：ShotFrameImage.id
    """

    model_id: str | None = Field(
        None,
        description="可选模型 ID（models.id）；不传则使用 ModelSettings.default_image_model_id；Provider 由模型关联反查",
    )
    image_id: int | None = Field(
        None,
        description="图片模型 ID，如 ActorImage.id / SceneImage.id / PropImage.id 等；必须与路径主体 ID 匹配",
    )
    prompt: str | None = Field(
        None,
        description="提示词（由前端传入）。创建任务接口必填；render-prompt 接口可不传",
    )
    images: list[str] = Field(
        default_factory=list,
        description="参考图 file_id 列表（可多张，顺序有效）。创建任务接口会基于 file_id 从数据中解析为参考图",
    )


class AssetImageBatchItem(BaseModel):
    """设定图批量队列项；派生状态在执行时读取已完成的基准图作为参考。"""

    type: Literal["character", "actor", "scene", "prop", "costume"]
    id: str
    name: str = ""
    image_id: int
    prompt: str = Field(..., min_length=1)
    reference_type: Literal["character", "actor", "scene", "prop", "costume"] | None = None
    reference_entity_id: str | None = None
    reference_assets: list["AssetImageReference"] = Field(default_factory=list)


class AssetImageReference(BaseModel):
    """批量生成时动态读取的实体参考图，用于照片/屏幕等强关联道具。"""

    type: Literal["character", "actor", "scene", "prop", "costume"]
    entity_id: str


class AssetImageBatchRequest(BaseModel):
    items: list[AssetImageBatchItem] = Field(default_factory=list)
    model_id: str | None = None


class AssetImageBatchCreated(BaseModel):
    batch_id: str
    total: int


class AssetImageBatchStatus(BaseModel):
    batch_id: str
    status: str
    total: int
    queued: int
    running: int
    succeeded: int
    failed: int
    cancelled: int
    current: str = ""
    current_task_id: str | None = None
    error: str = ""
    items: list[dict] = Field(default_factory=list)


class FrameImageBatchItem(BaseModel):
    shot_id: str
    name: str = ""
    frame_type: ShotFrameType = Field("key", description="first | key | last")
    images: list[ShotLinkedAssetItem] = Field(default_factory=list)


class FrameImageBatchRequest(BaseModel):
    items: list[FrameImageBatchItem] = Field(default_factory=list)
    model_id: str | None = None
    target_ratio: ImageTargetRatio = "9:16"
    resolution_profile: ImageResolutionProfile | None = "standard"


class FrameImageBatchCreated(BaseModel):
    batch_id: str
    total: int


class FrameImageBatchStatus(BaseModel):
    batch_id: str
    status: str
    total: int
    queued: int
    running: int
    succeeded: int
    failed: int
    cancelled: int
    current: str = ""
    current_task_id: str | None = None
    error: str = ""
    items: list[dict] = Field(default_factory=list)


class ShotFrameImageTaskRequest(BaseModel):
    """镜头分镜帧图片生成请求体：只根据 `shot_id + frame_type` 定位 ShotFrameImage。

    用于替代旧接口中通过 `image_id` 直接传入 ShotFrameImage.id 的方式。
    """

    model_id: str | None = Field(
        None,
        description="可选模型 ID（models.id）；不传则使用 ModelSettings.default_image_model_id；Provider 由模型关联反查",
    )
    frame_type: ShotFrameType = Field(..., description="first | last | key")
    prompt: str = Field(
        ...,
        description="提示词（由前端传入，创建任务接口必填）。",
        min_length=1,
    )
    images: list[ShotLinkedAssetItem] = Field(
        default_factory=list,
        description=(
            "参考资产条目列表（可多张，顺序有效）。后端会使用 item.file_id 作为参考图；"
            "无效条目会被跳过。"
        ),
    )
    target_ratio: ImageTargetRatio = Field(
        ...,
        description="目标视频画幅比例；关键帧将按该画幅生成，以提升后续视频参考稳定性",
    )
    resolution_profile: ImageResolutionProfile | None = Field(
        "standard",
        description="关键帧输出分辨率档位，默认 standard",
    )


class ShotFramePromptRenderRequest(BaseModel):
    """镜头分镜帧提示词渲染请求体。"""

    frame_type: ShotFrameType = Field(..., description="first | last | key")
    prompt: str = Field(
        ...,
        description="原始基础提示词。渲染接口要求显式传入，用于生成最终提示词。",
        min_length=1,
    )
    images: list[ShotLinkedAssetItem] = Field(
        default_factory=list,
        description="参考资产条目列表（可多张，顺序有效）。后端会使用 item.file_id 作为参考图；无效条目会被跳过。",
    )


class RenderedPromptResponse(BaseModel):
    prompt: str = Field(..., description="渲染后的提示词（已套用模板与变量替换）")
    images: list[str] = Field(
        default_factory=list,
        description="参考图 file_id 列表（自动选择；顺序有效）",
    )


async def _load_frame_render_guidance(
    *,
    db: AsyncSession,
    shot_id: str,
    frame_type: ShotFrameType,
) -> dict[str, str]:
    """读取最终图片提示词需要保留的高优先级镜头约束。"""
    try:
        run_args = await _build_shot_frame_prompt_run_args_service(
            db,
            shot_id=shot_id,
            frame_type=frame_type.value if hasattr(frame_type, "value") else str(frame_type),
        )
    except HTTPException:
        return {
            "director_command_summary": "",
            "continuity_guidance": "",
            "frame_specific_guidance": "",
            "composition_anchor": "",
            "screen_direction_guidance": "",
        }

    input_dict = dict(run_args.get("input") or {})
    return {
        "director_command_summary": str(input_dict.get("director_command_summary") or "").strip(),
        "continuity_guidance": str(input_dict.get("continuity_guidance") or "").strip(),
        "frame_specific_guidance": str(input_dict.get("frame_specific_guidance") or "").strip(),
        "composition_anchor": str(input_dict.get("composition_anchor") or "").strip(),
        "screen_direction_guidance": str(input_dict.get("screen_direction_guidance") or "").strip(),
    }


async def _create_shot_frame_prompt_task_internal(*, shot_id: str, frame_type: ShotFrameType) -> str:
    frame_type_value = _normalize_frame_type_service(frame_type.value if hasattr(frame_type, "value") else str(frame_type))
    async with async_session_maker() as db:
        store = SqlAlchemyTaskStore(db)
        tm = TaskManager(store=store, strategies={})
        run_args = await _build_shot_frame_prompt_run_args_service(
            db,
            shot_id=shot_id,
            frame_type=frame_type_value,
        )
        task_record = await tm.create(
            task=_CreateOnlyTask(),
            mode=DeliveryMode.async_polling,
            task_kind="shot_frame_prompt",
            run_args=run_args,
        )
        db.add(
            GenerationTaskLink(
                task_id=task_record.id,
                resource_type="prompt",
                relation_type=_relation_type_for_frame_service(frame_type_value),
                relation_entity_id=shot_id,
            )
        )
        await _mark_shot_generating_service(db, shot_id=shot_id)
        await db.commit()
        enqueue_task_execution(task_record.id)
        return task_record.id


async def _read_task_result(task_id: str) -> dict:
    async with async_session_maker() as db:
        record = await SqlAlchemyTaskStore(db).get(task_id)
        return dict(record.result or {}) if record is not None else {}


async def _create_shot_frame_image_task_internal(
    *,
    db: AsyncSession,
    shot_id: str,
    frame_type: ShotFrameType,
    prompt: str,
    images: list[ShotLinkedAssetItem],
    model_id: str | None,
    target_ratio: ImageTargetRatio,
    resolution_profile: ImageResolutionProfile | None,
) -> str:
    prompt = (prompt or "").strip()
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="prompt is required for shot frame generation",
        )
    shot_detail = await db.get(ShotDetail, shot_id)
    if shot_detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ShotDetail not found")
    shot = await db.get(Shot, shot_id)
    render_guidance = await _load_frame_render_guidance(
        db=db,
        shot_id=shot_id,
        frame_type=frame_type,
    )
    base = _build_frame_base_draft_service(
        shot_id=shot_id,
        frame_type=frame_type,
        prompt=prompt,
        director_command_summary=render_guidance["director_command_summary"],
        continuity_guidance=render_guidance["continuity_guidance"],
        frame_specific_guidance=render_guidance["frame_specific_guidance"],
        composition_anchor=render_guidance["composition_anchor"],
        screen_direction_guidance=render_guidance["screen_direction_guidance"],
    )
    context = _build_frame_context_service(
        shot_id=shot_id,
        frame_type=frame_type,
        items=images,
    )
    submission = _build_frame_submission_payload_service(
        base=base,
        context=context,
    )
    ref_images = await _resolve_reference_image_refs_by_file_ids_service(db, file_ids=submission.images)

    shot_frame_image_stmt = (
        select(ShotFrameImage)
        .where(ShotFrameImage.shot_detail_id == shot_id, ShotFrameImage.frame_type == frame_type)
        .limit(1)
    )
    shot_frame_image = (await db.execute(shot_frame_image_stmt)).scalars().first()
    if shot_frame_image is None:
        shot_frame_image = ShotFrameImage(
            shot_detail_id=shot_id,
            frame_type=frame_type,
            file_id=None,
            width=None,
            height=None,
            format="png",
            shot_version=shot.version if shot is not None else 1,
            prompt_version=getattr(shot_detail, "prompt_version", 1),
            asset_versions={f"{item.type}:{item.id}": item.file_id or "" for item in images},
            is_stale=False,
        )
        db.add(shot_frame_image)
        await db.flush()
        await db.refresh(shot_frame_image)
    elif not shot_frame_image.format:
        shot_frame_image.format = "png"

    shot_frame_image.shot_version = shot.version if shot is not None else 1
    shot_frame_image.prompt_version = getattr(shot_detail, "prompt_version", 1)
    shot_frame_image.asset_versions = {
        f"{item.type}:{item.id}": item.file_id or "" for item in images
    }
    shot_frame_image.is_stale = False

    submission_extra = dict(submission.extra or {})
    return await _create_image_task_and_link_service(
        db=db,
        model_id=model_id,
        relation_type="shot_frame_image",
        relation_entity_id=str(shot_frame_image.id),
        prompt=submission.prompt,
        images=ref_images if ref_images else None,
        target_ratio=target_ratio,
        resolution_profile=resolution_profile,
        purpose="video_reference",
        render_context=submission_extra.get("render_context"),
    )


def _batch_snapshot(batch_id: str) -> dict | None:
    with _BATCH_LOCK:
        batch = _ASSET_IMAGE_BATCHES.get(batch_id)
        if batch is None:
            return None
        return {
            **batch,
            "items": [dict(x) for x in batch.get("items", [])],
        }


def _update_batch_counts(batch: dict) -> None:
    items = batch.get("items", [])
    batch["queued"] = sum(1 for item in items if item.get("status") == "queued")
    batch["running"] = sum(1 for item in items if item.get("status") == "running")
    batch["succeeded"] = sum(1 for item in items if item.get("status") == "succeeded")
    batch["failed"] = sum(1 for item in items if item.get("status") == "failed")
    batch["cancelled"] = sum(1 for item in items if item.get("status") == "cancelled")


def _batch_update(batch_id: str, **patch: object) -> None:
    with _BATCH_LOCK:
        batch = _ASSET_IMAGE_BATCHES.get(batch_id)
        if batch is None:
            return
        batch.update(patch)
        _update_batch_counts(batch)


def _batch_item_update(batch_id: str, index: int, **patch: object) -> None:
    with _BATCH_LOCK:
        batch = _ASSET_IMAGE_BATCHES.get(batch_id)
        if batch is None:
            return
        items = batch.get("items", [])
        if index < 0 or index >= len(items):
            return
        items[index].update(patch)
        _update_batch_counts(batch)


def _frame_batch_snapshot(batch_id: str) -> dict | None:
    with _BATCH_LOCK:
        batch = _FRAME_IMAGE_BATCHES.get(batch_id)
        if batch is None:
            return None
        return {
            **batch,
            "items": [dict(x) for x in batch.get("items", [])],
        }


def _frame_batch_update(batch_id: str, **patch: object) -> None:
    with _BATCH_LOCK:
        batch = _FRAME_IMAGE_BATCHES.get(batch_id)
        if batch is None:
            return
        batch.update(patch)
        _update_batch_counts(batch)


def _frame_batch_item_update(batch_id: str, index: int, **patch: object) -> None:
    with _BATCH_LOCK:
        batch = _FRAME_IMAGE_BATCHES.get(batch_id)
        if batch is None:
            return
        items = batch.get("items", [])
        if index < 0 or index >= len(items):
            return
        items[index].update(patch)
        _update_batch_counts(batch)


def _batch_cancel_requested(batches: dict[str, dict], batch_id: str) -> bool:
    with _BATCH_LOCK:
        batch = batches.get(batch_id)
        return bool(batch and batch.get("cancel_requested"))


def _request_batch_cancel(batches: dict[str, dict], batch_id: str) -> str | None:
    """停止后不再启动队列项目，并返回当前已提交任务供调用方撤销。"""
    with _BATCH_LOCK:
        batch = batches.get(batch_id)
        if batch is None:
            return None
        if batch.get("status") in {"succeeded", "failed", "cancelled"}:
            return str(batch.get("current_task_id") or "")
        batch["cancel_requested"] = True
        for item in batch.get("items", []):
            if item.get("status") == "queued":
                item.update(status="cancelled", error="队列已停止")
        _update_batch_counts(batch)
        batch["status"] = "cancelling" if batch["running"] else "cancelled"
        batch["error"] = "已请求停止队列"
        return str(batch.get("current_task_id") or "")


async def _cancel_generation_task(task_id: str) -> None:
    if not task_id:
        return
    async with async_session_maker() as db:
        store = SqlAlchemyTaskStore(db)
        record = await store.request_cancel(task_id, "批量队列已停止")
        if record is None:
            return
        await db.commit()
        if record.status != TaskStatus.cancelled and revoke_task_execution(task_id):
            await store.mark_cancelled(task_id)
            await db.commit()


async def _wait_generation_task(task_id: str, *, timeout_s: float = 900.0) -> TaskStatus:
    deadline = time.monotonic() + timeout_s
    last_status = TaskStatus.pending
    while time.monotonic() < deadline:
        # 每轮使用全新会话。长轮询连接即使 rollback，也可能继续读到 SQLite 旧状态，
        # 造成图片已完成但队列永远停在 0/N。
        async with async_session_maker() as db:
            store = SqlAlchemyTaskStore(db)
            view = await store.get_status_view(task_id)
            if view is not None:
                last_status = view.status
                if view.status in _TERMINAL_TASK_STATUSES:
                    return view.status
        await asyncio.sleep(2.0)
    return last_status


_IMAGE_REFERENCE_SPECS = {
    "character": (CharacterImage, "character_id"),
    "actor": (ActorImage, "actor_id"),
    "scene": (SceneImage, "scene_id"),
    "prop": (PropImage, "prop_id"),
    "costume": (CostumeImage, "costume_id"),
}


async def _load_entity_reference_file_ids(
    db: AsyncSession,
    references: list[AssetImageReference],
) -> list[str]:
    """Dynamically resolve entity images for a strong visual prop relationship."""
    file_ids: list[str] = []
    for reference in references:
        image_model, parent_field = _IMAGE_REFERENCE_SPECS[reference.type]
        statement = (
            select(image_model.file_id)
            .where(getattr(image_model, parent_field) == reference.entity_id)
            .where(image_model.file_id.is_not(None))
            .order_by(image_model.id.asc())
            .limit(1)
        )
        file_id = (await db.execute(statement)).scalar_one_or_none()
        if not file_id:
            raise ValueError(f"强关联参考图尚未生成：{reference.type}/{reference.entity_id}")
        file_ids.append(str(file_id))
    return list(dict.fromkeys(file_ids))


async def _load_state_reference_file_ids(db: AsyncSession, item: AssetImageBatchItem) -> list[str]:
    """在派生状态真正执行时读取基准图，确保队列前一项生成完成后才能被引用。"""
    if not item.reference_type or not item.reference_entity_id:
        return []
    image_model, parent_field = _IMAGE_REFERENCE_SPECS[item.reference_type]
    statement = (
        select(image_model.file_id)
        .where(getattr(image_model, parent_field) == item.reference_entity_id)
        .where(image_model.file_id.is_not(None))
        .order_by(image_model.id.asc())
    )
    return [str(file_id) for file_id in (await db.execute(statement)).scalars().all() if file_id]


async def _create_asset_batch_item_task(item: AssetImageBatchItem, *, model_id: str | None) -> str:
    prompt = _scene_empty_prompt(item.prompt) if item.type == "scene" else item.prompt.strip()
    if not prompt:
        raise ValueError("prompt is required")
    async with async_session_maker() as db:
        state_reference_file_ids = await _load_state_reference_file_ids(db, item)
        if item.reference_entity_id and not state_reference_file_ids:
            raise ValueError("基准造型图尚未生成，派生状态不会独立生成")
        strong_reference_file_ids = await _load_entity_reference_file_ids(db, item.reference_assets)
        reference_file_ids = list(dict.fromkeys([*state_reference_file_ids, *strong_reference_file_ids]))
        if item.type == "character":
            submission = await _build_character_image_submission_payload_service(
                db,
                character_id=item.id,
                image_id=item.image_id,
                prompt=prompt,
                images=reference_file_ids,
            )
        elif item.type == "actor":
            submission = await _build_actor_image_submission_payload_service(
                db,
                actor_id=item.id,
                image_id=item.image_id,
                prompt=prompt,
                images=reference_file_ids,
            )
        else:
            submission = await _build_asset_image_submission_payload_service(
                db,
                asset_type=item.type,
                asset_id=item.id,
                image_id=item.image_id,
                prompt=prompt,
                images=reference_file_ids,
            )
        ref_images = await _resolve_reference_image_refs_by_file_ids_service(db, file_ids=submission.images)
        return await _create_image_task_and_link_service(
            db=db,
            model_id=model_id,
            relation_type=submission.relation_type,
            relation_entity_id=submission.relation_entity_id,
            prompt=submission.prompt,
            images=ref_images if ref_images else None,
            target_ratio="16:9",
        )


async def _run_asset_image_batch(batch_id: str, items: list[AssetImageBatchItem], *, model_id: str | None) -> None:
    if _batch_cancel_requested(_ASSET_IMAGE_BATCHES, batch_id):
        _batch_update(batch_id, status="cancelled", current="", current_task_id=None)
        return
    _batch_update(batch_id, status="running", current="")
    for index, item in enumerate(items):
        if _batch_cancel_requested(_ASSET_IMAGE_BATCHES, batch_id):
            break
        label = item.name or item.id
        _batch_update(batch_id, current=label)
        _batch_item_update(batch_id, index, status="running", error="")
        try:
            task_id = await _create_asset_batch_item_task(item, model_id=model_id)
            _batch_update(batch_id, current_task_id=task_id)
            _batch_item_update(batch_id, index, task_id=task_id)
            if _batch_cancel_requested(_ASSET_IMAGE_BATCHES, batch_id):
                await _cancel_generation_task(task_id)
            task_status = await _wait_generation_task(task_id)
            if task_status == TaskStatus.succeeded:
                _batch_item_update(batch_id, index, status="succeeded")
            elif task_status == TaskStatus.cancelled and _batch_cancel_requested(_ASSET_IMAGE_BATCHES, batch_id):
                _batch_item_update(batch_id, index, status="cancelled", error="队列已停止")
            else:
                _batch_item_update(batch_id, index, status="failed", error=f"任务{task_status.value}")
        except Exception as exc:  # noqa: BLE001
            _batch_item_update(
                batch_id,
                index,
                status="cancelled" if _batch_cancel_requested(_ASSET_IMAGE_BATCHES, batch_id) else "failed",
                error="队列已停止" if _batch_cancel_requested(_ASSET_IMAGE_BATCHES, batch_id) else str(exc),
            )
    if _batch_cancel_requested(_ASSET_IMAGE_BATCHES, batch_id):
        _batch_update(batch_id, status="cancelled", current="", current_task_id=None)
        return
    snapshot = _batch_snapshot(batch_id) or {}
    failed = int(snapshot.get("failed") or 0)
    _batch_update(
        batch_id,
        status="failed" if failed else "succeeded",
        current="",
        current_task_id=None,
        error=f"{failed} 项生成失败" if failed else "",
    )


def _spawn_asset_image_batch(batch_id: str, items: list[AssetImageBatchItem], *, model_id: str | None) -> None:
    def runner() -> None:
        asyncio.run(_run_asset_image_batch(batch_id, items, model_id=model_id))

    threading.Thread(target=runner, daemon=True).start()


async def _create_frame_batch_item_task(
    item: FrameImageBatchItem,
    *,
    model_id: str | None,
    target_ratio: ImageTargetRatio,
    resolution_profile: ImageResolutionProfile | None,
    on_task_created: Callable[[str, Literal["prompt", "image"]], Awaitable[None]] | None = None,
) -> str:
    frame_type_value = item.frame_type.value if hasattr(item.frame_type, "value") else str(item.frame_type)
    async with async_session_maker() as db:
        prompt = await _read_saved_frame_prompt_service(
            db,
            shot_id=item.shot_id,
            frame_type=frame_type_value,
        )

    if not prompt:
        prompt_task_id = await _create_shot_frame_prompt_task_internal(
            shot_id=item.shot_id,
            frame_type=item.frame_type,
        )
        if on_task_created:
            await on_task_created(prompt_task_id, "prompt")
        prompt_status = await _wait_generation_task(prompt_task_id, timeout_s=300.0)
        if prompt_status == TaskStatus.cancelled:
            raise RuntimeError("prompt task cancelled")
        if prompt_status == TaskStatus.succeeded:
            result = await _read_task_result(prompt_task_id)
            prompt = str(result.get("prompt") or "").strip()

    if not prompt:
        async with async_session_maker() as db:
            prompt = await _resolve_batch_frame_prompt_service(
                db,
                shot_id=item.shot_id,
                frame_type=frame_type_value,
            )
            await _persist_frame_prompt_service(
                db,
                shot_id=item.shot_id,
                frame_type=frame_type_value,
                prompt=prompt,
            )
            await db.commit()

    async with async_session_maker() as db:
        image_task_id = await _create_shot_frame_image_task_internal(
            db=db,
            shot_id=item.shot_id,
            frame_type=item.frame_type,
            prompt=prompt,
            images=item.images,
            model_id=model_id,
            target_ratio=target_ratio,
            resolution_profile=resolution_profile,
        )
    if on_task_created:
        await on_task_created(image_task_id, "image")
    return image_task_id


async def _run_frame_image_batch(
    batch_id: str,
    items: list[FrameImageBatchItem],
    *,
    model_id: str | None,
    target_ratio: ImageTargetRatio,
    resolution_profile: ImageResolutionProfile | None,
) -> None:
    if _batch_cancel_requested(_FRAME_IMAGE_BATCHES, batch_id):
        _frame_batch_update(batch_id, status="cancelled", current="", current_task_id=None)
        return
    _frame_batch_update(batch_id, status="running", current="")
    for index, item in enumerate(items):
        if _batch_cancel_requested(_FRAME_IMAGE_BATCHES, batch_id):
            break
        label = item.name or item.shot_id
        _frame_batch_update(batch_id, current=label)
        _frame_batch_item_update(batch_id, index, status="running", stage="preparing", error="")
        try:
            async def register_current_task(
                task_id: str,
                stage: Literal["prompt", "image"],
                *,
                item_index: int = index,
            ) -> None:
                """同步批次当前任务及阶段，让前端能区分提示词和图像生成。"""
                _frame_batch_update(batch_id, current_task_id=task_id)
                _frame_batch_item_update(batch_id, item_index, task_id=task_id, stage=stage)
                if _batch_cancel_requested(_FRAME_IMAGE_BATCHES, batch_id):
                    await _cancel_generation_task(task_id)

            task_id = await _create_frame_batch_item_task(
                item,
                model_id=model_id,
                target_ratio=target_ratio,
                resolution_profile=resolution_profile,
                on_task_created=register_current_task,
            )
            _frame_batch_update(batch_id, current_task_id=task_id)
            _frame_batch_item_update(batch_id, index, task_id=task_id)
            if _batch_cancel_requested(_FRAME_IMAGE_BATCHES, batch_id):
                await _cancel_generation_task(task_id)
            task_status = await _wait_generation_task(task_id)
            if task_status == TaskStatus.succeeded:
                _frame_batch_item_update(batch_id, index, status="succeeded", stage="done")
            elif task_status == TaskStatus.cancelled and _batch_cancel_requested(_FRAME_IMAGE_BATCHES, batch_id):
                _frame_batch_item_update(batch_id, index, status="cancelled", stage="cancelled", error="队列已停止")
            else:
                _frame_batch_item_update(batch_id, index, status="failed", stage="failed", error=f"任务{task_status.value}")
        except Exception as exc:  # noqa: BLE001
            _frame_batch_item_update(
                batch_id,
                index,
                status="cancelled" if _batch_cancel_requested(_FRAME_IMAGE_BATCHES, batch_id) else "failed",
                stage="cancelled" if _batch_cancel_requested(_FRAME_IMAGE_BATCHES, batch_id) else "failed",
                error="队列已停止" if _batch_cancel_requested(_FRAME_IMAGE_BATCHES, batch_id) else str(exc),
            )
    if _batch_cancel_requested(_FRAME_IMAGE_BATCHES, batch_id):
        _frame_batch_update(batch_id, status="cancelled", current="", current_task_id=None)
        return
    snapshot = _frame_batch_snapshot(batch_id) or {}
    failed = int(snapshot.get("failed") or 0)
    _frame_batch_update(
        batch_id,
        status="failed" if failed else "succeeded",
        current="",
        current_task_id=None,
        error=f"{failed} 项生成失败" if failed else "",
    )


def _spawn_frame_image_batch(
    batch_id: str,
    items: list[FrameImageBatchItem],
    *,
    model_id: str | None,
    target_ratio: ImageTargetRatio,
    resolution_profile: ImageResolutionProfile | None,
) -> None:
    def runner() -> None:
        asyncio.run(
            _run_frame_image_batch(
                batch_id,
                items,
                model_id=model_id,
                target_ratio=target_ratio,
                resolution_profile=resolution_profile,
            )
        )

    threading.Thread(target=runner, daemon=True).start()


@router.post(
    "/asset-batches",
    response_model=ApiResponse[AssetImageBatchCreated],
    status_code=status.HTTP_201_CREATED,
    summary="批量排队生成设定页造型图",
)
async def create_asset_image_batch(
    body: AssetImageBatchRequest,
) -> ApiResponse[AssetImageBatchCreated]:
    items = [item for item in body.items if item.prompt.strip()]
    if not items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no items to generate")
    batch_id = f"asset_batch_{uuid.uuid4().hex}"
    with _BATCH_LOCK:
        _ASSET_IMAGE_BATCHES[batch_id] = {
            "batch_id": batch_id,
            "status": "queued",
            "total": len(items),
            "queued": len(items),
            "running": 0,
            "succeeded": 0,
            "failed": 0,
            "cancelled": 0,
            "current": "",
            "current_task_id": None,
            "error": "",
            "cancel_requested": False,
            "items": [
                {
                    "type": item.type,
                    "id": item.id,
                    "name": item.name,
                    "reference_entity_id": item.reference_entity_id,
                    "status": "queued",
                    "task_id": None,
                    "error": "",
                }
                for item in items
            ],
        }
    _spawn_asset_image_batch(batch_id, items, model_id=body.model_id)
    return created_response(AssetImageBatchCreated(batch_id=batch_id, total=len(items)))


@router.get(
    "/asset-batches/{batch_id}",
    response_model=ApiResponse[AssetImageBatchStatus],
    status_code=status.HTTP_200_OK,
    summary="查询设定页造型图批量生成进度",
)
async def get_asset_image_batch(batch_id: str) -> ApiResponse[AssetImageBatchStatus]:
    snapshot = _batch_snapshot(batch_id)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="batch not found")
    return success_response(AssetImageBatchStatus.model_validate(snapshot))


@router.post(
    "/asset-batches/{batch_id}/cancel",
    response_model=ApiResponse[AssetImageBatchStatus],
    status_code=status.HTTP_200_OK,
    summary="停止设定页造型图批量生成",
)
async def cancel_asset_image_batch(batch_id: str) -> ApiResponse[AssetImageBatchStatus]:
    task_id = _request_batch_cancel(_ASSET_IMAGE_BATCHES, batch_id)
    if task_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="batch not found")
    await _cancel_generation_task(task_id)
    snapshot = _batch_snapshot(batch_id)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="batch not found")
    return success_response(AssetImageBatchStatus.model_validate(snapshot))


@router.post(
    "/frame-batches",
    response_model=ApiResponse[FrameImageBatchCreated],
    status_code=status.HTTP_201_CREATED,
    summary="批量排队生成镜头缺失画面",
)
async def create_frame_image_batch(
    body: FrameImageBatchRequest,
) -> ApiResponse[FrameImageBatchCreated]:
    items = [item for item in body.items if item.shot_id.strip()]
    if not items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no shots to generate")
    batch_id = f"frame_batch_{uuid.uuid4().hex}"
    with _BATCH_LOCK:
        _FRAME_IMAGE_BATCHES[batch_id] = {
            "batch_id": batch_id,
            "status": "queued",
            "total": len(items),
            "queued": len(items),
            "running": 0,
            "succeeded": 0,
            "failed": 0,
            "cancelled": 0,
            "current": "",
            "current_task_id": None,
            "error": "",
            "cancel_requested": False,
            "items": [
                {
                    "shot_id": item.shot_id,
                    "name": item.name,
                    "frame_type": item.frame_type.value if hasattr(item.frame_type, "value") else str(item.frame_type),
                    "status": "queued",
                    "stage": "queued",
                    "task_id": None,
                    "error": "",
                }
                for item in items
            ],
        }
    _spawn_frame_image_batch(
        batch_id,
        items,
        model_id=body.model_id,
        target_ratio=body.target_ratio,
        resolution_profile=body.resolution_profile,
    )
    return created_response(FrameImageBatchCreated(batch_id=batch_id, total=len(items)))


@router.get(
    "/frame-batches/{batch_id}",
    response_model=ApiResponse[FrameImageBatchStatus],
    status_code=status.HTTP_200_OK,
    summary="查询镜头画面批量生成进度",
)
async def get_frame_image_batch(batch_id: str) -> ApiResponse[FrameImageBatchStatus]:
    snapshot = _frame_batch_snapshot(batch_id)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="batch not found")
    return success_response(FrameImageBatchStatus.model_validate(snapshot))


@router.post(
    "/frame-batches/{batch_id}/cancel",
    response_model=ApiResponse[FrameImageBatchStatus],
    status_code=status.HTTP_200_OK,
    summary="停止镜头画面批量生成",
)
async def cancel_frame_image_batch(batch_id: str) -> ApiResponse[FrameImageBatchStatus]:
    task_id = _request_batch_cancel(_FRAME_IMAGE_BATCHES, batch_id)
    if task_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="batch not found")
    await _cancel_generation_task(task_id)
    snapshot = _frame_batch_snapshot(batch_id)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="batch not found")
    return success_response(FrameImageBatchStatus.model_validate(snapshot))



@router.post(
    "/actors/{actor_id}/image-tasks",
    response_model=ApiResponse[TaskCreated],
    status_code=status.HTTP_201_CREATED,
    summary="演员图片生成（任务版）",
)
async def create_actor_image_generation_task(
    actor_id: str,
    body: StudioImageTaskRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskCreated]:
    """为指定演员创建图片生成任务，并通过 `GenerationTaskLink` 关联。"""
    prompt = (body.prompt or "").strip()
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="prompt is required for actor generation",
        )
    submission = await _build_actor_image_submission_payload_service(
        db,
        actor_id=actor_id,
        image_id=body.image_id,
        prompt=prompt,
        images=body.images,
    )
    ref_images = await _resolve_reference_image_refs_by_file_ids_service(db, file_ids=submission.images)
    task_id = await _create_image_task_and_link_service(
        db=db,
        model_id=body.model_id,
        relation_type=submission.relation_type,
        relation_entity_id=submission.relation_entity_id,
        prompt=submission.prompt,
        images=ref_images if ref_images else None,
        target_ratio="16:9",  # 造型区统一横向构图
    )
    return created_response(TaskCreated(task_id=task_id))


@router.post(
    "/actors/{actor_id}/render-prompt",
    response_model=ApiResponse[RenderedPromptResponse],
    status_code=status.HTTP_200_OK,
    summary="演员图片提示词渲染",
)
async def render_actor_image_prompt(
    actor_id: str,
    body: StudioImageTaskRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[RenderedPromptResponse]:
    base = await _build_actor_image_base_draft_service(
        db,
        actor_id=actor_id,
        image_id=body.image_id,
    )
    context = _build_asset_image_context_service(base=base)
    derived = _derive_asset_image_preview_service(base=base, context=context)
    return success_response(RenderedPromptResponse(prompt=derived.prompt, images=derived.images))


@router.post(
    "/assets/{asset_type}/{asset_id}/image-tasks",
    response_model=ApiResponse[TaskCreated],
    status_code=status.HTTP_201_CREATED,
    summary="道具/场景/服装图片生成（任务版）",
)
async def create_asset_image_generation_task(
    asset_type: str,
    asset_id: str,
    body: StudioImageTaskRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskCreated]:
    """为道具/场景/服装创建图片生成任务。

    - asset_type: prop / scene / costume
    - path 参数 asset_id 为对应资产 ID
    - body.image_id 必须为该资产下对应图片表记录的 ID（PropImage/SceneImage/CostumeImage）
    """
    prompt = (body.prompt or "").strip()
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="prompt is required for asset image generation",
        )
    submission = await _build_asset_image_submission_payload_service(
        db,
        asset_type=asset_type,
        asset_id=asset_id,
        image_id=body.image_id,
        prompt=prompt,
        images=body.images,
    )
    ref_images = await _resolve_reference_image_refs_by_file_ids_service(db, file_ids=submission.images)

    task_id = await _create_image_task_and_link_service(
        db=db,
        model_id=body.model_id,
        relation_type=submission.relation_type,
        relation_entity_id=submission.relation_entity_id,
        prompt=submission.prompt,
        images=ref_images if ref_images else None,
        target_ratio="16:9",  # 造型区统一横向构图
    )
    return created_response(TaskCreated(task_id=task_id))


@router.post(
    "/assets/{asset_type}/{asset_id}/render-prompt",
    response_model=ApiResponse[RenderedPromptResponse],
    status_code=status.HTTP_200_OK,
    summary="道具/场景/服装图片提示词渲染",
)
async def render_asset_image_prompt(
    asset_type: str,
    asset_id: str,
    body: StudioImageTaskRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[RenderedPromptResponse]:
    base = await _build_asset_image_base_draft_service(
        db,
        asset_type=asset_type,
        asset_id=asset_id,
        image_id=body.image_id,
    )
    context = _build_asset_image_context_service(base=base)
    derived = _derive_asset_image_preview_service(base=base, context=context)
    return success_response(RenderedPromptResponse(prompt=derived.prompt, images=derived.images))


@router.post(
    "/characters/{character_id}/image-tasks",
    response_model=ApiResponse[TaskCreated],
    status_code=status.HTTP_201_CREATED,
    summary="角色图片生成（任务版）",
)
async def create_character_image_generation_task(
    character_id: str,
    body: StudioImageTaskRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskCreated]:
    """为角色创建图片生成任务（对应 CharacterImage 业务）。

    - path 参数 character_id 为 Character.id
    - body.image_id 必须为该角色下的 CharacterImage.id
    """
    prompt = (body.prompt or "").strip()
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="prompt is required for character image generation",
        )
    submission = await _build_character_image_submission_payload_service(
        db,
        character_id=character_id,
        image_id=body.image_id,
        prompt=prompt,
        images=body.images,
    )
    ref_images = await _resolve_reference_image_refs_by_file_ids_service(db, file_ids=submission.images)
    task_id = await _create_image_task_and_link_service(
        db=db,
        model_id=body.model_id,
        relation_type=submission.relation_type,
        relation_entity_id=submission.relation_entity_id,
        prompt=submission.prompt,
        images=ref_images if ref_images else None,
        target_ratio="16:9",  # 造型区统一横向构图
    )
    return created_response(TaskCreated(task_id=task_id))


@router.post(
    "/characters/{character_id}/render-prompt",
    response_model=ApiResponse[RenderedPromptResponse],
    status_code=status.HTTP_200_OK,
    summary="角色图片提示词渲染",
)
async def render_character_image_prompt(
    character_id: str,
    body: StudioImageTaskRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[RenderedPromptResponse]:
    base = await _build_character_image_base_draft_service(
        db,
        character_id=character_id,
        image_id=body.image_id,
    )
    context = _build_asset_image_context_service(base=base)
    derived = _derive_asset_image_preview_service(base=base, context=context)
    return success_response(RenderedPromptResponse(prompt=derived.prompt, images=derived.images))


@router.post(
    "/shot/{shot_id}/frame-image-tasks",
    response_model=ApiResponse[TaskCreated],
    status_code=status.HTTP_201_CREATED,
    summary="镜头分镜帧图片生成（任务版）",
)
async def create_shot_frame_image_generation_task(
    shot_id: str,
    body: ShotFrameImageTaskRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskCreated]:
    """为镜头分镜帧图片生成任务（基于 `shot_id + frame_type` 自动定位数据）。"""
    task_id = await _create_shot_frame_image_task_internal(
        db=db,
        shot_id=shot_id,
        frame_type=body.frame_type,
        prompt=body.prompt,
        images=body.images,
        model_id=body.model_id,
        target_ratio=body.target_ratio,
        resolution_profile=body.resolution_profile,
    )
    return created_response(TaskCreated(task_id=task_id))


@router.post(
    "/shot/{shot_id}/frame-render-prompt",
    response_model=ApiResponse[RenderedShotFramePromptRead],
    status_code=status.HTTP_200_OK,
    summary="镜头分镜帧提示词渲染",
)
async def render_shot_frame_prompt(
    shot_id: str,
    body: ShotFramePromptRenderRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[RenderedShotFramePromptRead]:
    prompt = (body.prompt or "").strip()
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="prompt is required for shot frame render",
        )
    render_guidance = await _load_frame_render_guidance(
        db=db,
        shot_id=shot_id,
        frame_type=body.frame_type,
    )
    base = _build_frame_base_draft_service(
        shot_id=shot_id,
        frame_type=body.frame_type,
        prompt=prompt,
        director_command_summary=render_guidance["director_command_summary"],
        continuity_guidance=render_guidance["continuity_guidance"],
        frame_specific_guidance=render_guidance["frame_specific_guidance"],
        composition_anchor=render_guidance["composition_anchor"],
        screen_direction_guidance=render_guidance["screen_direction_guidance"],
    )
    context = _build_frame_context_service(
        shot_id=shot_id,
        frame_type=body.frame_type,
        items=body.images,
    )
    rendered = _to_rendered_shot_frame_prompt_read_service(
        derived=_derive_frame_preview_service(
            base=base,
            context=context,
        )
    )
    return success_response(rendered)
