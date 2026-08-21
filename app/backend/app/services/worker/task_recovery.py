"""服务启动时收口已失联的本机线程任务。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import async_session_maker
from app.models.task import GenerationTask, GenerationTaskStatus

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = (
    GenerationTaskStatus.pending,
    GenerationTaskStatus.running,
    GenerationTaskStatus.streaming,
)


async def reconcile_orphaned_local_tasks(
    session_factory: Callable[[], AsyncSession] = async_session_maker,
) -> int:
    """终结上次服务进程遗留的本机线程任务，并返回处理数量。"""
    now = datetime.now(UTC).replace(tzinfo=None)
    async with session_factory() as db:
        result = await db.execute(
            select(GenerationTask).where(
                GenerationTask.executor_type == "local-thread",
                GenerationTask.status.in_(_ACTIVE_STATUSES),
            )
        )
        rows = list(result.scalars())
        for row in rows:
            row.finished_at = now
            if row.cancel_requested:
                row.status = GenerationTaskStatus.cancelled
                row.cancelled_at = now
                row.error = "任务已取消（本机执行进程已结束）"
            else:
                row.status = GenerationTaskStatus.failed
                row.error = "本机任务因服务重启而中断，请重新提交"
        if rows:
            await db.commit()

    if rows:
        logger.warning("reconciled orphaned local tasks on startup: count=%s", len(rows))
    return len(rows)
