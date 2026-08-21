"""SQLAlchemy 同步引擎与会话。

给 Celery worker 使用，避免在同步 worker 进程里承载 async DB runtime。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.core.db import Base


def _to_sync_database_url(url: str) -> str:
    if url.startswith("mysql+aiomysql://"):
        return "mysql+pymysql://" + url.removeprefix("mysql+aiomysql://")
    if url.startswith("sqlite+aiosqlite:///"):
        return "sqlite:///" + url.removeprefix("sqlite+aiosqlite:///")
    return url


def _build_sync_engine() -> Engine:
    database_url = _to_sync_database_url(settings.database_url)
    connect_args: dict[str, Any] = {"timeout": 30} if database_url.startswith("sqlite") else {}
    db_engine = create_engine(
        database_url,
        echo=settings.debug,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    if database_url.startswith("sqlite"):
        _configure_sqlite_connection(db_engine)
    return db_engine


def _configure_sqlite_connection(db_engine: Engine) -> None:
    """让同步后台任务使用与 API 相同的 SQLite 并发保护参数。"""

    @event.listens_for(db_engine, "connect")
    def set_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            # Celery/本机线程也可能删除实体，需与 API 连接保持相同的级联语义。
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("PRAGMA busy_timeout = 30000")
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.execute("PRAGMA synchronous = NORMAL")
        finally:
            cursor.close()


engine_sync = _build_sync_engine()
sync_session_maker = sessionmaker(
    bind=engine_sync,
    class_=Session,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

__all__ = [
    "Base",
    "engine_sync",
    "sync_session_maker",
]
