"""项目大脑全文提取任务的去重、保护和下游上下文测试。"""

from __future__ import annotations

from types import SimpleNamespace

from app.models.studio import ProjectBrainEntry
from app.models.studio_project_brain import ProjectBrainCategory, ProjectBrainOrigin, ProjectBrainStatus
from app.schemas.studio.project_brain import ProjectBrainExtractionResult
from app.services.film.shot_frame_prompt_tasks import _build_project_brain_context
from app.services.project_brain_tasks import apply_project_brain_extraction
from app.services.worker.task_registry import task_executor_registry


def _entry(
    entry_id: str,
    title: str,
    content: str,
    *,
    origin: ProjectBrainOrigin,
    status: ProjectBrainStatus,
    locked: bool,
    version: int = 1,
) -> ProjectBrainEntry:
    return ProjectBrainEntry(
        id=entry_id,
        project_id="project_1",
        category=ProjectBrainCategory.continuity,
        title=title,
        content=content,
        origin=origin,
        status=status,
        source_ref="",
        evidence=[],
        locked=locked,
        version=version,
    )


class _ScalarRows:
    def __init__(self, rows: list[ProjectBrainEntry]) -> None:
        self.rows = rows

    def all(self) -> list[ProjectBrainEntry]:
        return self.rows


class _SyncDB:
    def __init__(self, rows: list[ProjectBrainEntry]) -> None:
        self.rows = rows

    def scalars(self, _statement: object) -> _ScalarRows:
        return _ScalarRows(self.rows)

    def add(self, entry: ProjectBrainEntry) -> None:
        self.rows.append(entry)


def test_extraction_updates_ai_drafts_without_overwriting_confirmed_rules() -> None:
    locked = _entry(
        "locked", "旧宅空间关系", "堂屋东侧连接厨房。",
        origin=ProjectBrainOrigin.user, status=ProjectBrainStatus.confirmed, locked=True,
    )
    draft = _entry(
        "draft", "周诚持物状态", "周诚手中有钥匙。",
        origin=ProjectBrainOrigin.ai, status=ProjectBrainStatus.draft, locked=False,
    )
    db = _SyncDB([locked, draft])
    result = ProjectBrainExtractionResult.model_validate({
        "entries": [
            {"category": "continuity", "title": "旧宅空间关系", "content": "错误覆盖"},
            {"category": "continuity", "title": "周诚持物状态", "content": "周诚离开后仍拿着钥匙。"},
            {"category": "fact", "title": "事件发生在雨夜", "content": "原文明示当晚下雨。"},
        ],
        "analysis_note": "已先去重再检查派生约束。",
    })

    apply_project_brain_extraction(
        SimpleNamespace(db=db),  # type: ignore[arg-type]
        project_id="project_1",
        result=result,
    )

    assert locked.content == "堂屋东侧连接厨房。"
    assert locked.version == 1
    assert draft.content == "周诚离开后仍拿着钥匙。"
    assert draft.version == 2
    created = next(item for item in db.rows if item.title == "事件发生在雨夜")
    assert created.origin == ProjectBrainOrigin.ai
    assert created.status == ProjectBrainStatus.draft
    assert created.locked is False


def test_confirmed_rules_are_rendered_as_downstream_prompt_context() -> None:
    entries = [
        _entry(
            "one", "旧宅空间关系", "堂屋东侧连接厨房。",
            origin=ProjectBrainOrigin.user, status=ProjectBrainStatus.confirmed, locked=True,
        )
    ]
    context = _build_project_brain_context(entries)
    assert context == "[continuity] 旧宅空间关系：堂屋东侧连接厨房。"


def test_project_brain_executor_is_registered() -> None:
    executor = task_executor_registry.resolve("project_brain_extract")
    assert executor.task_kind == "project_brain_extract"
