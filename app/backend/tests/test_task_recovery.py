from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.task import GenerationTask, GenerationTaskStatus
from app.services.worker.task_recovery import reconcile_orphaned_local_tasks


def _task(
    task_id: str,
    *,
    status: str,
    executor_type: str,
    cancel_requested: bool = False,
) -> GenerationTask:
    """创建恢复测试所需的最小任务记录。"""
    return GenerationTask(
        id=task_id,
        mode="async_polling",
        task_kind="image_generation",
        status=status,
        progress=10,
        payload={"task_kind": "image_generation", "run_args": {}},
        result=None,
        error="",
        cancel_requested=cancel_requested,
        executor_type=executor_type,
        executor_task_id=f"{executor_type}-{task_id}",
    )


@pytest.mark.asyncio
async def test_reconcile_orphaned_local_tasks_only_closes_active_local_tasks() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    import app.models.task  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_local() as db:
        db.add_all(
            [
                _task(
                    "local-cancelling",
                    status="running",
                    executor_type="local-thread",
                    cancel_requested=True,
                ),
                _task("local-running", status="running", executor_type="local-thread"),
                _task("local-succeeded", status="succeeded", executor_type="local-thread"),
                _task("celery-running", status="running", executor_type="celery"),
            ]
        )
        await db.commit()

    assert await reconcile_orphaned_local_tasks(session_local) == 2

    async with session_local() as db:
        cancelling = await db.get(GenerationTask, "local-cancelling")
        interrupted = await db.get(GenerationTask, "local-running")
        succeeded = await db.get(GenerationTask, "local-succeeded")
        celery = await db.get(GenerationTask, "celery-running")

        assert cancelling is not None
        assert cancelling.status == GenerationTaskStatus.cancelled
        assert cancelling.finished_at is not None
        assert cancelling.cancelled_at is not None

        assert interrupted is not None
        assert interrupted.status == GenerationTaskStatus.failed
        assert interrupted.finished_at is not None
        assert "服务重启" in interrupted.error

        assert succeeded is not None
        assert succeeded.status == GenerationTaskStatus.succeeded
        assert celery is not None
        assert celery.status == GenerationTaskStatus.running

    await engine.dispose()
