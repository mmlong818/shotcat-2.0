from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.studio import (
    Chapter,
    Project,
    ProjectWorkflowInvalidation,
    Shot,
    ShotDetail,
    ShotFrameImage,
)
from app.services.studio.workflow import capture_revision, project_impact


async def _build_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_local(), engine


@pytest.mark.asyncio
async def test_capture_revision_preserves_snapshot_and_marks_downstream_stale() -> None:
    db, engine = await _build_session()
    async with db:
        db.add(Project(id="p1", name="测试项目", style="drama"))
        db.add(Chapter(id="c1", project_id="p1", index=1, title="第一集", raw_text="原剧本"))
        db.add(Shot(id="s1", chapter_id="c1", index=1, title="镜头一", script_excerpt="原镜头"))
        db.add(ShotDetail(id="s1", camera_shot="MS", angle="EYE_LEVEL", movement="STATIC"))
        db.add(ShotFrameImage(shot_detail_id="s1", frame_type="first", format="png"))
        await db.flush()

        impact = await project_impact(db, project_id="p1", source_step="script")
        assert impact.total_affected == 2
        assert {item.step: item.affected_count for item in impact.items}["storyboard"] == 1
        assert {item.step: item.affected_count for item in impact.items}["frames"] == 1

        revision, _ = await capture_revision(
            db,
            project_id="p1",
            source_step="script",
            reason="修改剧本前自动保存",
        )
        await db.flush()

        shot = await db.get(Shot, "s1")
        frame = (await db.execute(select(ShotFrameImage))).scalars().one()
        invalidations = list((await db.execute(select(ProjectWorkflowInvalidation))).scalars().all())

        assert revision.snapshot["chapters"][0]["raw_text"] == "原剧本"
        assert revision.snapshot["shots"][0]["script_excerpt"] == "原镜头"
        assert shot is not None and shot.is_stale is True
        assert frame.is_stale is True
        assert {(row.downstream_step, row.affected_count) for row in invalidations} == {
            ("storyboard", 1),
            ("frames", 1),
        }
    await engine.dispose()


@pytest.mark.asyncio
async def test_revision_numbers_are_per_project_and_source_step() -> None:
    db, engine = await _build_session()
    async with db:
        db.add(Project(id="p1", name="测试项目", style="drama"))
        await db.flush()

        first, _ = await capture_revision(db, project_id="p1", source_step="brain", reason="第一次")
        second, _ = await capture_revision(db, project_id="p1", source_step="brain", reason="第二次")
        other_step, _ = await capture_revision(db, project_id="p1", source_step="cast", reason="设定")

        assert (first.revision, second.revision, other_step.revision) == (1, 2, 1)
    await engine.dispose()
