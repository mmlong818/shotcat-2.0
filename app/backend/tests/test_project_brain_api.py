"""Shotcat 2.0 项目大脑的写入、锁定与版本冲突测试。"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from app.api.v1.routes.studio.project_brain import (
    create_project_brain_entry,
    delete_project_brain_entry,
    get_project_brain_summary,
    update_project_brain_entry,
)
from app.models.studio import Project, ProjectBrainEntry
from app.dependencies import get_db
from app.main import app
from app.schemas.studio.project_brain import ProjectBrainEntryCreate, ProjectBrainEntryUpdate


class _Scalars:
    def __init__(self, values: list[ProjectBrainEntry]) -> None:
        self._values = values

    def scalars(self) -> "_Scalars":
        return self

    def all(self) -> list[ProjectBrainEntry]:
        return self._values


class _BrainDB:
    def __init__(self) -> None:
        self.project = object()
        self.entries: dict[str, ProjectBrainEntry] = {}

    async def get(self, model: type[object], entity_id: str) -> object | None:
        if model is Project:
            return self.project if entity_id == "project_1" else None
        if model is ProjectBrainEntry:
            return self.entries.get(entity_id)
        return None

    def add(self, entry: ProjectBrainEntry) -> None:
        self.entries[entry.id] = entry

    async def flush(self) -> None:
        return None

    async def refresh(self, entry: ProjectBrainEntry) -> None:
        return None

    async def delete(self, entry: ProjectBrainEntry) -> None:
        self.entries.pop(entry.id, None)

    async def execute(self, _statement: object) -> _Scalars:
        return _Scalars(list(self.entries.values()))


@pytest.mark.asyncio
async def test_project_brain_preserves_confirmed_rules_and_rejects_stale_writes() -> None:
    db = _BrainDB()
    created = await create_project_brain_entry(
        "project_1",
        ProjectBrainEntryCreate(
            category="continuity",
            title="旧宅空间关系",
            content="堂屋东侧始终连接厨房。",
            origin="user",
            status="confirmed",
            source_ref="用户确认",
            locked=True,
        ),
        db=db,  # type: ignore[arg-type]
    )
    entry = created.data
    assert entry is not None
    assert entry.version == 1
    assert entry.locked is True

    updated = await update_project_brain_entry(
        "project_1",
        entry.id,
        ProjectBrainEntryUpdate(expected_version=1, content="堂屋东侧连接厨房，北侧连接卧房。"),
        db=db,  # type: ignore[arg-type]
    )
    assert updated.data is not None
    assert updated.data.version == 2

    with pytest.raises(HTTPException) as stale:
        await update_project_brain_entry(
            "project_1",
            entry.id,
            ProjectBrainEntryUpdate(expected_version=1, title="过期修改"),
            db=db,  # type: ignore[arg-type]
        )
    assert stale.value.status_code == 409

    with pytest.raises(HTTPException) as locked:
        await delete_project_brain_entry("project_1", entry.id, db=db)  # type: ignore[arg-type]
    assert locked.value.status_code == 409


@pytest.mark.asyncio
async def test_project_brain_summary_distinguishes_ai_drafts() -> None:
    db = _BrainDB()
    for title, origin, status, locked in (
        ("原文事实", "source", "confirmed", True),
        ("待确认推断", "ai", "draft", False),
    ):
        await create_project_brain_entry(
            "project_1",
            ProjectBrainEntryCreate(
                category="fact",
                title=title,
                content=title,
                origin=origin,
                status=status,
                locked=locked,
            ),
            db=db,  # type: ignore[arg-type]
        )

    response = await get_project_brain_summary("project_1", db=db)  # type: ignore[arg-type]
    assert response.data is not None
    assert response.data.total == 2
    assert response.data.confirmed == 1
    assert response.data.locked == 1
    assert response.data.ai_drafts == 1
    assert response.data.by_category == {"fact": 2}


def test_project_brain_route_is_registered(client: TestClient) -> None:
    db = _BrainDB()

    async def _override_db() -> AsyncGenerator[_BrainDB, None]:
        yield db

    app.dependency_overrides[get_db] = _override_db
    try:
        response = client.get("/api/v1/studio/projects/project_1/brain/summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["data"] == {
        "total": 0,
        "confirmed": 0,
        "locked": 0,
        "ai_drafts": 0,
        "by_category": {},
    }
