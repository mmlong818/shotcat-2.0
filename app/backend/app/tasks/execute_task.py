"""统一 Celery 执行入口。

职责：
- Celery 统一只接收业务 task_id；
- 通过 GenerationTask.task_kind + registry 找到具体 WorkerTaskExecutor；
- 回写 executor_type / executor_task_id，便于排障。
"""

from __future__ import annotations

import logging
import threading
import uuid

from celery.result import AsyncResult

from app.core.celery_app import celery_app
from app.core.db_sync import sync_session_maker
from app.models.task import GenerationTask
from app.services.worker.task_registry import task_executor_registry

logger = logging.getLogger(__name__)


def _record_executor_dispatch(task_id: str, *, executor_type: str, executor_task_id: str | None) -> None:
    with sync_session_maker() as db:
        row = db.get(GenerationTask, task_id)
        if row is None:
            return
        row.executor_type = executor_type
        row.executor_task_id = executor_task_id
        db.commit()


def enqueue_task_execution(task_id: str) -> AsyncResult:
    try:
        async_result = run_task_celery.delay(task_id)
        _record_executor_dispatch(
            task_id,
            executor_type="celery",
            executor_task_id=async_result.id,
        )
        return async_result
    except Exception as exc:  # noqa: BLE001
        local_id = f"local-{uuid.uuid4().hex}"
        logger.warning("celery unavailable, executing task locally: task_id=%s error=%s", task_id, exc)
        _record_executor_dispatch(
            task_id,
            executor_type="local-thread",
            executor_task_id=local_id,
        )
        threading.Thread(target=run_task_celery.run, args=(task_id,), daemon=True).start()
        return AsyncResult(local_id, app=celery_app)


def revoke_task_execution(task_id: str, *, terminate: bool = True, signal: str = "SIGTERM") -> bool:
    with sync_session_maker() as db:
        row = db.get(GenerationTask, task_id)
        if row is None:
            return False
        executor_type = (row.executor_type or "").strip()
        if executor_type == "local-thread":
            # Python 线程不能被强制终止；任务执行器会在结果写入前检查取消状态，
            # 因此可立即把数据库状态收口，避免界面长期停留在“停止中”。
            return True
        if executor_type != "celery":
            return False
        executor_task_id = (row.executor_task_id or "").strip()
        if not executor_task_id:
            return False

    try:
        AsyncResult(executor_task_id, app=celery_app).revoke(terminate=terminate, signal=signal)
    except Exception:  # noqa: BLE001
        logger.exception("failed to revoke celery task: task_id=%s executor_task_id=%s", task_id, executor_task_id)
        return False
    return True


@celery_app.task(name="task.execute")
def run_task_celery(task_id: str) -> None:
    with sync_session_maker() as db:
        row = db.get(GenerationTask, task_id)
        if row is None:
            return
        task_kind = (row.task_kind or "").strip() or str((row.payload or {}).get("task_kind") or "").strip()
    executor = task_executor_registry.resolve(task_kind)
    executor.run(task_id)
