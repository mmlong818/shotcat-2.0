"""项目大脑全文分析任务：创建、执行与安全写入 AI 待确认候选。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chains.agents import ProjectBrainExtractorAgent
from app.core.task_manager import DeliveryMode, SqlAlchemyTaskStore, TaskManager
from app.core.task_manager.types import TaskStatus
from app.models.studio import ProjectBrainEntry
from app.models.studio_project_brain import ProjectBrainOrigin, ProjectBrainStatus
from app.models.task import GenerationTask, GenerationTaskStatus
from app.models.task_links import GenerationTaskLink
from app.schemas.studio.project_brain import ProjectBrainExtractionResult
from app.services.worker.task_executor import AbstractLLMResultGenerator, AbstractWorkerTaskExecutor, WorkerTaskContext


PROJECT_BRAIN_EXTRACTION_TASK_KIND = "project_brain_extract"
PROJECT_BRAIN_EXTRACTION_RELATION_TYPE = "project_brain_extraction"
_ACTIVE_STATUSES = (
    GenerationTaskStatus.pending,
    GenerationTaskStatus.running,
    GenerationTaskStatus.streaming,
)


class _CreateOnlyTask:
    async def run(self, *args: object, **kwargs: object) -> None:
        return None

    async def status(self) -> dict[str, object]:
        return {}

    async def is_done(self) -> bool:
        return False

    async def get_result(self) -> None:
        return None


@dataclass(slots=True)
class ProjectBrainTaskCreateResult:
    task_id: str
    status: TaskStatus
    reused: bool


async def create_project_brain_extraction_task(
    db: AsyncSession,
    *,
    project_id: str,
    project_name: str,
    script_text: str,
) -> ProjectBrainTaskCreateResult:
    existing_stmt = (
        select(GenerationTask)
        .join(GenerationTaskLink, GenerationTaskLink.task_id == GenerationTask.id)
        .where(
            GenerationTaskLink.relation_type == PROJECT_BRAIN_EXTRACTION_RELATION_TYPE,
            GenerationTaskLink.relation_entity_id == project_id,
            GenerationTask.status.in_(_ACTIVE_STATUSES),
        )
        .limit(1)
    )
    existing = (await db.execute(existing_stmt)).scalars().first()
    if existing is not None:
        status_value = existing.status.value if hasattr(existing.status, "value") else str(existing.status)
        return ProjectBrainTaskCreateResult(existing.id, TaskStatus(status_value), True)

    manager = TaskManager(store=SqlAlchemyTaskStore(db), strategies={})
    task = await manager.create(
        task=_CreateOnlyTask(),
        mode=DeliveryMode.async_polling,
        task_kind=PROJECT_BRAIN_EXTRACTION_TASK_KIND,
        run_args={
            "project_id": project_id,
            "project_name": project_name,
            "script_text": script_text,
        },
    )
    db.add(GenerationTaskLink(
        task_id=task.id,
        resource_type="text",
        relation_type=PROJECT_BRAIN_EXTRACTION_RELATION_TYPE,
        relation_entity_id=project_id,
    ))
    await db.flush()
    return ProjectBrainTaskCreateResult(task.id, task.status, False)


class ProjectBrainResultGenerator(AbstractLLMResultGenerator):
    thinking = True

    def generate_with_llm(self, llm, run_args: dict[str, Any]) -> ProjectBrainExtractionResult:
        return ProjectBrainExtractorAgent(llm).extract(
            project_name=str(run_args.get("project_name") or ""),
            script_text=str(run_args.get("script_text") or ""),
        )


def _entry_key(category: object, title: str) -> tuple[str, str]:
    category_value = getattr(category, "value", category)
    normalized_title = re.sub(r"[\s，。；：、,.!！?？—_\-]+", "", title).casefold()
    return str(category_value), normalized_title


def apply_project_brain_extraction(
    ctx: WorkerTaskContext,
    *,
    project_id: str,
    result: ProjectBrainExtractionResult,
) -> None:
    existing = list(ctx.db.scalars(
        select(ProjectBrainEntry).where(ProjectBrainEntry.project_id == project_id)
    ).all())
    by_key = {_entry_key(item.category, item.title): item for item in existing}

    for candidate in result.entries:
        key = _entry_key(candidate.category, candidate.title)
        current = by_key.get(key)
        if current is not None:
            if current.locked or current.status == ProjectBrainStatus.confirmed:
                continue
            if current.origin == ProjectBrainOrigin.ai:
                current.content = candidate.content
                current.source_ref = candidate.source_ref
                current.evidence = candidate.evidence
                current.status = ProjectBrainStatus.draft
                current.version += 1
            continue

        entry = ProjectBrainEntry(
            id=f"brain_{uuid4().hex}",
            project_id=project_id,
            category=candidate.category,
            title=candidate.title,
            content=candidate.content,
            origin=ProjectBrainOrigin.ai,
            status=ProjectBrainStatus.draft,
            source_ref=candidate.source_ref,
            evidence=candidate.evidence,
            locked=False,
            version=1,
        )
        ctx.db.add(entry)
        by_key[key] = entry


class ProjectBrainExtractionTaskExecutor(AbstractWorkerTaskExecutor):
    task_kind = PROJECT_BRAIN_EXTRACTION_TASK_KIND
    timeout_seconds = 1800.0

    def __init__(self) -> None:
        super().__init__()
        self._generator = ProjectBrainResultGenerator()

    def execute(self, ctx: WorkerTaskContext, run_args: dict[str, Any]) -> ProjectBrainExtractionResult:
        return self._generator.generate(ctx.db, run_args)

    def should_apply(
        self,
        ctx: WorkerTaskContext,
        run_args: dict[str, Any],
        result: ProjectBrainExtractionResult,
    ) -> bool:
        return bool(run_args.get("project_id"))

    def apply_result(
        self,
        ctx: WorkerTaskContext,
        run_args: dict[str, Any],
        result: ProjectBrainExtractionResult,
    ) -> None:
        apply_project_brain_extraction(
            ctx,
            project_id=str(run_args.get("project_id") or ""),
            result=result,
        )


__all__ = [
    "PROJECT_BRAIN_EXTRACTION_RELATION_TYPE",
    "PROJECT_BRAIN_EXTRACTION_TASK_KIND",
    "ProjectBrainExtractionTaskExecutor",
    "apply_project_brain_extraction",
    "create_project_brain_extraction_task",
]
