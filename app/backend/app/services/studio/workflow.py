"""项目工作流版本、影响范围与下游失效记录。"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.studio import (
    Actor, ActorImage, AssetReferenceVersion, Chapter, Character, CharacterImage, CharacterPropLink,
    Costume, CostumeImage,
    Project, ProjectActorLink, ProjectBrainEntry, ProjectCostumeLink,
    ProjectPropLink, ProjectSceneLink, ProjectWorkflowInvalidation,
    ProjectWorkflowRevision, Prop, PropImage, Scene, SceneImage, Shot,
    ShotCharacterLink, ShotDetail, ShotDialogLine, ShotExtractedCandidate,
    ShotExtractedDialogueCandidate, ShotFrameImage,
)
from app.schemas.studio.workflow import WorkflowImpactItem, WorkflowImpactRead


STEP_ORDER = ("script", "brain", "cast", "storyboard", "frames", "gallery")
STEP_LABELS = {
    "script": "剧本", "brain": "项目大脑", "cast": "设定与造型",
    "storyboard": "分镜", "frames": "镜头画面", "gallery": "成片与总览",
}


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _row_payload(row: Any) -> dict[str, Any]:
    return {column.name: _json_value(getattr(row, column.name)) for column in row.__table__.columns}


async def _rows(db: AsyncSession, model: Any, *criteria: Any) -> list[Any]:
    return list((await db.execute(select(model).where(*criteria))).scalars().all())


async def project_impact(db: AsyncSession, *, project_id: str, source_step: str) -> WorkflowImpactRead:
    if source_step not in STEP_ORDER:
        raise ValueError(f"Unknown workflow step: {source_step}")
    chapter_ids = select(Chapter.id).where(Chapter.project_id == project_id)
    shot_ids = select(Shot.id).where(Shot.chapter_id.in_(chapter_ids))
    cast_count = 0
    for model in (Character, Scene, Prop, Costume):
        cast_count += int((await db.execute(
            select(func.count()).select_from(model).where(model.project_id == project_id)
        )).scalar() or 0)
    counts = {
        "brain": int((await db.execute(select(func.count()).select_from(ProjectBrainEntry).where(ProjectBrainEntry.project_id == project_id))).scalar() or 0),
        "cast": cast_count,
        "storyboard": int((await db.execute(select(func.count()).select_from(Shot).where(Shot.chapter_id.in_(chapter_ids)))).scalar() or 0),
        "frames": int((await db.execute(select(func.count()).select_from(ShotFrameImage).where(ShotFrameImage.shot_detail_id.in_(shot_ids)))).scalar() or 0),
        "gallery": 0,
    }
    downstream = STEP_ORDER[STEP_ORDER.index(source_step) + 1:]
    items = [WorkflowImpactItem(step=step, label=STEP_LABELS[step], affected_count=counts.get(step, 0)) for step in downstream]
    return WorkflowImpactRead(
        project_id=project_id,
        source_step=source_step,
        total_affected=sum(item.affected_count for item in items),
        items=items,
    )


async def _snapshot(db: AsyncSession, *, project_id: str) -> dict[str, Any]:
    project = await db.get(Project, project_id)
    chapters = await _rows(db, Chapter, Chapter.project_id == project_id)
    chapter_ids = [row.id for row in chapters]
    shots = await _rows(db, Shot, Shot.chapter_id.in_(chapter_ids)) if chapter_ids else []
    shot_ids = [row.id for row in shots]
    details = await _rows(db, ShotDetail, ShotDetail.id.in_(shot_ids)) if shot_ids else []
    frames = await _rows(db, ShotFrameImage, ShotFrameImage.shot_detail_id.in_(shot_ids)) if shot_ids else []
    characters = await _rows(db, Character, Character.project_id == project_id)
    scenes = await _rows(db, Scene, Scene.project_id == project_id)
    props = await _rows(db, Prop, Prop.project_id == project_id)
    costumes = await _rows(db, Costume, Costume.project_id == project_id)
    actors = await _rows(db, Actor, Actor.project_id == project_id)
    character_ids = [row.id for row in characters]
    scene_ids = [row.id for row in scenes]
    prop_ids = [row.id for row in props]
    costume_ids = [row.id for row in costumes]
    actor_ids = [row.id for row in actors]
    return {
        "project": _row_payload(project) if project is not None else None,
        "chapters": [_row_payload(row) for row in chapters],
        "brain": [_row_payload(row) for row in await _rows(db, ProjectBrainEntry, ProjectBrainEntry.project_id == project_id)],
        "characters": [_row_payload(row) for row in characters],
        "scenes": [_row_payload(row) for row in scenes],
        "props": [_row_payload(row) for row in props],
        "costumes": [_row_payload(row) for row in costumes],
        "actors": [_row_payload(row) for row in actors],
        "character_prop_links": [_row_payload(row) for row in await _rows(db, CharacterPropLink, CharacterPropLink.character_id.in_(character_ids))] if character_ids else [],
        "shots": [_row_payload(row) for row in shots],
        "shot_details": [_row_payload(row) for row in details],
        "frame_images": [_row_payload(row) for row in frames],
        "dialog_lines": [_row_payload(row) for row in await _rows(db, ShotDialogLine, ShotDialogLine.shot_detail_id.in_(shot_ids))] if shot_ids else [],
        "shot_character_links": [_row_payload(row) for row in await _rows(db, ShotCharacterLink, ShotCharacterLink.shot_id.in_(shot_ids))] if shot_ids else [],
        "shot_extracted_candidates": [_row_payload(row) for row in await _rows(db, ShotExtractedCandidate, ShotExtractedCandidate.shot_id.in_(shot_ids))] if shot_ids else [],
        "shot_extracted_dialogue_candidates": [_row_payload(row) for row in await _rows(db, ShotExtractedDialogueCandidate, ShotExtractedDialogueCandidate.shot_id.in_(shot_ids))] if shot_ids else [],
        "project_actor_links": [_row_payload(row) for row in await _rows(db, ProjectActorLink, ProjectActorLink.project_id == project_id)],
        "project_scene_links": [_row_payload(row) for row in await _rows(db, ProjectSceneLink, ProjectSceneLink.project_id == project_id)],
        "project_prop_links": [_row_payload(row) for row in await _rows(db, ProjectPropLink, ProjectPropLink.project_id == project_id)],
        "project_costume_links": [_row_payload(row) for row in await _rows(db, ProjectCostumeLink, ProjectCostumeLink.project_id == project_id)],
        "character_images": [_row_payload(row) for row in await _rows(db, CharacterImage, CharacterImage.character_id.in_(character_ids))] if character_ids else [],
        "scene_images": [_row_payload(row) for row in await _rows(db, SceneImage, SceneImage.scene_id.in_(scene_ids))] if scene_ids else [],
        "prop_images": [_row_payload(row) for row in await _rows(db, PropImage, PropImage.prop_id.in_(prop_ids))] if prop_ids else [],
        "costume_images": [_row_payload(row) for row in await _rows(db, CostumeImage, CostumeImage.costume_id.in_(costume_ids))] if costume_ids else [],
        "actor_images": [_row_payload(row) for row in await _rows(db, ActorImage, ActorImage.actor_id.in_(actor_ids))] if actor_ids else [],
        "asset_references": [_row_payload(row) for row in await _rows(db, AssetReferenceVersion, AssetReferenceVersion.project_id == project_id)],
    }


def _restore_payload(model: Any, payload: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for column in model.__table__.columns:
        if column.name not in payload:
            continue
        value = payload[column.name]
        if isinstance(value, str):
            try:
                python_type = column.type.python_type
            except (AttributeError, NotImplementedError):
                python_type = None
            if python_type is datetime:
                value = datetime.fromisoformat(value)
            elif python_type is date:
                value = date.fromisoformat(value)
        values[column.name] = value
    return values


async def _insert_snapshot_rows(db: AsyncSession, snapshot: dict[str, Any], key: str, model: Any) -> None:
    rows = snapshot.get(key) or []
    if rows:
        await db.execute(model.__table__.insert(), [_restore_payload(model, row) for row in rows])
        await db.flush()


async def restore_revision(
    db: AsyncSession,
    *,
    revision: ProjectWorkflowRevision,
) -> ProjectWorkflowRevision:
    """事务内恢复完整项目快照；版本历史和文件实体本身不回滚。"""
    project_id = revision.project_id
    snapshot = dict(revision.snapshot or {})
    if not snapshot.get("project"):
        raise ValueError("Revision snapshot is empty")

    current_chapter_ids = select(Chapter.id).where(Chapter.project_id == project_id)
    current_shot_ids = select(Shot.id).where(Shot.chapter_id.in_(current_chapter_ids))
    current_character_ids = select(Character.id).where(Character.project_id == project_id)
    current_scene_ids = select(Scene.id).where(Scene.project_id == project_id)
    current_prop_ids = select(Prop.id).where(Prop.project_id == project_id)
    current_costume_ids = select(Costume.id).where(Costume.project_id == project_id)
    current_actor_ids = select(Actor.id).where(Actor.project_id == project_id)

    delete_steps = [
        (AssetReferenceVersion, AssetReferenceVersion.project_id == project_id),
        (ShotExtractedDialogueCandidate, ShotExtractedDialogueCandidate.shot_id.in_(current_shot_ids)),
        (ShotExtractedCandidate, ShotExtractedCandidate.shot_id.in_(current_shot_ids)),
        (ShotDialogLine, ShotDialogLine.shot_detail_id.in_(current_shot_ids)),
        (ShotCharacterLink, ShotCharacterLink.shot_id.in_(current_shot_ids)),
        (ProjectActorLink, ProjectActorLink.project_id == project_id),
        (ProjectSceneLink, ProjectSceneLink.project_id == project_id),
        (ProjectPropLink, ProjectPropLink.project_id == project_id),
        (ProjectCostumeLink, ProjectCostumeLink.project_id == project_id),
        (ShotFrameImage, ShotFrameImage.shot_detail_id.in_(current_shot_ids)),
        (ShotDetail, ShotDetail.id.in_(current_shot_ids)),
        (Shot, Shot.chapter_id.in_(current_chapter_ids)),
        (CharacterPropLink, CharacterPropLink.character_id.in_(current_character_ids)),
        (CharacterImage, CharacterImage.character_id.in_(current_character_ids)),
        (Character, Character.project_id == project_id),
        (SceneImage, SceneImage.scene_id.in_(current_scene_ids)),
        (PropImage, PropImage.prop_id.in_(current_prop_ids)),
        (CostumeImage, CostumeImage.costume_id.in_(current_costume_ids)),
        (Scene, Scene.project_id == project_id),
        (Prop, Prop.project_id == project_id),
        (Costume, Costume.project_id == project_id),
        (ProjectBrainEntry, ProjectBrainEntry.project_id == project_id),
        (Chapter, Chapter.project_id == project_id),
    ]
    if "actors" in snapshot:
        delete_steps[17:17] = [
            (ActorImage, ActorImage.actor_id.in_(current_actor_ids)),
            (Actor, Actor.project_id == project_id),
        ]
    for model, criterion in delete_steps:
        await db.execute(delete(model).where(criterion))
    await db.flush()

    project = await db.get(Project, project_id)
    for key, value in _restore_payload(Project, snapshot["project"]).items():
        if key not in {"id", "created_at", "updated_at"}:
            setattr(project, key, value)

    for key, model in (
        ("chapters", Chapter), ("brain", ProjectBrainEntry),
        ("actors", Actor), ("scenes", Scene), ("props", Prop), ("costumes", Costume),
        ("characters", Character), ("character_prop_links", CharacterPropLink),
        ("shots", Shot), ("shot_details", ShotDetail),
        ("dialog_lines", ShotDialogLine), ("shot_character_links", ShotCharacterLink),
        ("shot_extracted_candidates", ShotExtractedCandidate),
        ("shot_extracted_dialogue_candidates", ShotExtractedDialogueCandidate),
        ("project_actor_links", ProjectActorLink), ("project_scene_links", ProjectSceneLink),
        ("project_prop_links", ProjectPropLink), ("project_costume_links", ProjectCostumeLink),
        ("character_images", CharacterImage), ("scene_images", SceneImage),
        ("prop_images", PropImage), ("costume_images", CostumeImage),
        ("actor_images", ActorImage), ("frame_images", ShotFrameImage),
        ("asset_references", AssetReferenceVersion),
    ):
        if key == "actor_images" and "actors" not in snapshot:
            continue
        await _insert_snapshot_rows(db, snapshot, key, model)

    await db.execute(update(ProjectWorkflowInvalidation).where(
        ProjectWorkflowInvalidation.project_id == project_id,
        ProjectWorkflowInvalidation.status == "pending",
    ).values(status="resolved"))
    revision.restored = True
    await db.flush()
    await db.refresh(revision)
    return revision


async def capture_revision(
    db: AsyncSession,
    *,
    project_id: str,
    source_step: str,
    reason: str,
    source_task_id: str | None = None,
) -> tuple[ProjectWorkflowRevision, WorkflowImpactRead]:
    impact = await project_impact(db, project_id=project_id, source_step=source_step)
    latest = int((await db.execute(
        select(func.max(ProjectWorkflowRevision.revision)).where(
            ProjectWorkflowRevision.project_id == project_id,
            ProjectWorkflowRevision.source_step == source_step,
        )
    )).scalar() or 0)
    revision = ProjectWorkflowRevision(
        id=f"revision_{uuid4().hex}", project_id=project_id, source_step=source_step,
        revision=latest + 1, reason=reason, source_task_id=source_task_id,
        snapshot=await _snapshot(db, project_id=project_id), restored=False,
    )
    db.add(revision)
    for item in impact.items:
        if item.affected_count <= 0:
            continue
        db.add(ProjectWorkflowInvalidation(
            project_id=project_id, revision_id=revision.id, downstream_step=item.step,
            affected_count=item.affected_count,
            reason=f"{STEP_LABELS[source_step]}已重做，需要重新确认{item.label}", status="pending",
        ))
    if source_step in {"script", "brain", "cast"} and impact.items:
        await db.execute(update(Shot).where(Shot.chapter_id.in_(select(Chapter.id).where(Chapter.project_id == project_id))).values(
            is_stale=True, stale_reason=f"{STEP_LABELS[source_step]}发生变化"
        ))
    if source_step in {"script", "brain", "cast", "storyboard"}:
        await db.execute(update(ShotFrameImage).where(
            ShotFrameImage.shot_detail_id.in_(select(Shot.id).where(
                Shot.chapter_id.in_(select(Chapter.id).where(Chapter.project_id == project_id))
            ))
        ).values(is_stale=True))
    await db.flush()
    await db.refresh(revision)
    return revision, impact


__all__ = ["STEP_LABELS", "STEP_ORDER", "capture_revision", "project_impact", "restore_revision"]
