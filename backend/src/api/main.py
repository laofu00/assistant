"""FastAPI 应用工厂 — 生命周期 + CORS + GZip + 限流 + 指标 + 全局异常处理"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from prometheus_fastapi_instrumentator import Instrumentator

from src.core.config import settings
from src.core.exceptions import AppException
from src.core.logging_config import setup_logging
from src.core.metrics import get_metrics  # noqa: F401 — 注册自定义工具 Prometheus 指标
from src.core.middleware import RequestContextMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    # 启动
    setup_logging(settings.LOG_LEVEL)
    settings.validate_required()
    logger.info(f"Smart Assistant v{settings.APP_VERSION} 启动中...")
    logger.info(f"环境: {settings.ENVIRONMENT}, 模型: {settings.MODEL_NAME}")

    # 确保数据目录存在
    for d in [settings.chroma_path, str(settings.upload_dir), "data/dead_letter", "logs"]:
        Path(d).mkdir(parents=True, exist_ok=True)

    # 启动 token 写入后台任务
    try:
        from src.token.token_callback import start_token_worker
        start_token_worker()
    except Exception as e:
        logger.warning(f"Token 后台任务启动失败（不影响服务）: {e}")

    # 启动工具审计日志后台写入任务
    try:
        from src.tools.tool_wrapper import start_audit_worker
        start_audit_worker()
    except Exception as e:
        logger.warning(f"审计日志后台任务启动失败（不影响服务）: {e}")

    # 启动死信队列定期重试
    try:
        from src.token.dead_letter import dead_letter
        asyncio.create_task(_retry_dead_letters(dead_letter))
    except Exception as e:
        logger.warning(f"死信重试任务启动失败（不影响服务）: {e}")

    # 从 DB 加载工具禁用配置
    try:
        from src.api.routes.tools import load_tool_config_from_db
        await load_tool_config_from_db()
    except Exception as e:
        logger.warning(f"工具配置加载失败（不影响服务）: {e}")

    yield

    # 关闭
    logger.info("应用正在关闭...")
    # 等待现有请求完成
    await _shutdown_db()


async def _retry_dead_letters(dlq, interval: int = 60) -> None:
    """定期重试死信队列中的失败记录（默认每 60 秒）"""
    while True:
        await asyncio.sleep(interval)
        try:
            count = await dlq.get_pending_count()
            if count > 0:
                success = await dlq.retry_pending()
                if success > 0:
                    logger.info(f"[死信] 重试成功 {success}/{count}")
        except Exception as e:
            logger.warning(f"[死信] 重试异常: {e}")


async def _shutdown_db() -> None:
    try:
        from src.core.database import shutdown_db
        await shutdown_db()
    except Exception:
        pass


def create_app() -> FastAPI:
    app = FastAPI(
        title="Smart Assistant",
        version=settings.APP_VERSION,
        description="AI-powered personal assistant with knowledge base, memo, email, and resume matching",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # GZip 压缩
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # API 全局限流中间件（最先执行，认证之前）
    from src.core.rate_limit import ApiRateLimitMiddleware
    app.add_middleware(ApiRateLimitMiddleware)

    # 请求上下文中间件（JWT + Redis 认证）
    app.add_middleware(RequestContextMiddleware)

    # Prometheus 指标
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    # 全局异常处理
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.status_code, "data": None, "msg": exc.detail},
        )

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(
            status_code=400 if exc.code != "APP_ERROR" else 500,
            content={"code": 400 if exc.code != "APP_ERROR" else 500, "data": None, "msg": exc.message},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(f"未捕获异常: {exc}")
        return JSONResponse(status_code=500, content={"code": 500, "data": None, "msg": "服务器内部错误"})

    # 注册路由
    from src.api.routes import admin, auth, chat, health, knowledge, memo, memory, token, tools, user

    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(knowledge.router, prefix="/api/v1")
    app.include_router(memo.router, prefix="/api/v1")
    app.include_router(token.router, prefix="/api/v1")
    app.include_router(tools.router, prefix="/api/v1")
    app.include_router(memory.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(user.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")
    app.include_router(health.router)  # /health 不带版本前缀

    return app


app = create_app()
