"""FastAPI 应用入口。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import router as api_v1_router
from app.bootstrap import bootstrap_all_registries
from app.config import settings
from app.core.storage import LOCAL_STORAGE_ROOT
from app.schemas.common import ApiResponse


def _error_message(detail: object) -> str:
    """将异常 detail 转为前端可读的 message。"""
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        parts = []
        for item in detail:
            if isinstance(item, dict) and "msg" in item:
                loc = item.get("loc", ())
                loc_str = ".".join(str(x) for x in loc if x != "body")
                parts.append(f"{loc_str}: {item['msg']}" if loc_str else item["msg"])
            else:
                parts.append(str(item))
        return "; ".join(parts) if parts else "Validation error"
    return str(detail)


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """HTTP 异常统一为 { code, message, data: null }。"""
    from fastapi import HTTPException

    if isinstance(exc, HTTPException):
        code = exc.status_code
        message = _error_message(exc.detail)
    else:
        code = 500
        message = "Internal server error"
    body = ApiResponse[None](code=code, message=message, data=None, meta=None).model_dump()
    return JSONResponse(status_code=code, content=body)


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """422 校验异常统一为 { code: 422, message, data: null }。"""
    assert isinstance(exc, RequestValidationError)
    message = _error_message(exc.errors())
    body = ApiResponse[None](code=422, message=message, data=None, meta=None).model_dump()
    return JSONResponse(status_code=422, content=body)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化，关闭时清理。"""
    # 启动时：供应商注册 + 任务执行器注册（幂等）
    bootstrap_all_registries()
    # 本机线程随服务进程退出；启动时终结其遗留记录，避免页面永久显示“执行中”。
    from app.services.worker.task_recovery import reconcile_orphaned_local_tasks

    await reconcile_orphaned_local_tasks()
    # 旧版 SQLite 未开启外键，删除资产后可能残留图片槽位；启动时一次性修复。
    from app.services.studio.data_recovery import cleanup_orphaned_entity_image_slots

    await cleanup_orphaned_entity_image_slots()
    # 确保对象存储 bucket 存在（幂等）；存储暂不可用不应阻塞应用启动
    try:
        from anyio import to_thread

        from app.core.storage import init_storage

        await to_thread.run_sync(init_storage)
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).warning("对象存储初始化失败（bucket 可能需要手建）: %s", exc)
    yield
    # 关闭时：清理资源
    pass


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# 统一错误响应格式：{ code, message, data: null }
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, http_exception_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router, prefix=settings.api_v1_prefix)
LOCAL_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/local-storage", StaticFiles(directory=str(LOCAL_STORAGE_ROOT)), name="local-storage")
# 影视技能路由同时挂到主应用，保证 /api/v1/film 一定可访问


@app.get("/health")
async def health():
    """健康检查。"""
    from app.schemas.common import success_response
    return success_response({"status": "ok"})
