"""SQLAlchemy 异步引擎与会话。"""

from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


def _build_engine() -> AsyncEngine:
    connect_args: dict[str, Any] = {}
    if settings.database_url.startswith("sqlite"):
        # SQLite 默认几乎不等待锁；批量图片任务并发写入时会把普通读取也打成 500。
        connect_args = {"timeout": 30}
    db_engine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
        future=True,
        # MySQL wait_timeout（默认 8h）会踢掉空闲连接，池里的死连接会导致
        # "Lost connection to MySQL server during query"；pre_ping 取用前探活，
        # recycle 提前主动换连接兜底
        pool_pre_ping=True,
        pool_recycle=3600,
        connect_args=connect_args,
    )
    if settings.database_url.startswith("sqlite"):
        _configure_sqlite_connection(db_engine)
    return db_engine


def _configure_sqlite_connection(db_engine: AsyncEngine) -> None:
    """为每条 SQLite 连接启用 WAL 和锁等待，允许读请求与短写事务并存。"""

    @event.listens_for(db_engine.sync_engine, "connect")
    def set_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            # SQLite 默认不执行外键约束；必须逐连接开启，ON DELETE CASCADE 才会生效。
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("PRAGMA busy_timeout = 30000")
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.execute("PRAGMA synchronous = NORMAL")
        finally:
            cursor.close()


def _build_session_maker(bind_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


class _AsyncSessionMakerProxy:
    """可重绑定的 sessionmaker 代理。

    Celery prefork 模式下，worker 子进程不能继续复用父进程里初始化的
    async engine / sessionmaker。这里保持导入对象稳定，同时允许在子进程
    启动后重新绑定底层 sessionmaker。
    """

    def __init__(self, maker: async_sessionmaker[AsyncSession]) -> None:
        self._maker = maker

    def configure(self, maker: async_sessionmaker[AsyncSession]) -> None:
        self._maker = maker

    def __call__(self, *args: Any, **kwargs: Any) -> AsyncSession:
        return self._maker(*args, **kwargs)


engine = _build_engine()
async_session_maker = _AsyncSessionMakerProxy(_build_session_maker(engine))


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""

    pass


async def init_db() -> None:
    """创建所有表（开发/迁移用）。"""
    # 确保 ORM 模型已导入，从而注册到 Base.metadata
    import app.models.llm  # noqa: F401  # pylint: disable=unused-import
    import app.models.studio  # noqa: F401
    import app.models.task  # noqa: F401
    import app.models.task_links  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """关闭数据库连接。"""
    await engine.dispose()


def reset_db_runtime() -> None:
    """在 Celery worker 子进程中重建 engine 与 sessionmaker。

    这样可以避免 prefork 继承父进程中的 async engine，导致连接对象和事件循环
    绑定错乱，触发 Future attached to a different loop。
    """

    global engine

    engine = _build_engine()
    async_session_maker.configure(_build_session_maker(engine))
