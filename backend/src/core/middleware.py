"""请求上下文中间件 — 注入 request_id + JWT/Redis 认证，绑定日志上下文，记录请求耗时"""

import time
import uuid
from collections.abc import Awaitable, Callable

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.core.jwt_utils import get_user_id_from_token
from src.core.redis_client import TOKEN_PREFIX, get_redis

# 无需认证的路径
_PUBLIC_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/health",
    "/health",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
}


def _is_public(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in _PUBLIC_PATHS)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """请求上下文中间件：JWT/Redis 认证 + 日志上下文 + 耗时记录"""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        session_id = request.headers.get("X-Session-ID", "")
        path = request.url.path
        method = request.method

        # OPTIONS 预检请求直接放行（CORS 中间件处理，无需认证）
        if method == "OPTIONS":
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response

        # JWT + Redis 认证（公开路径跳过）
        user_id = "anonymous"
        if not _is_public(path):
            result = await self._authenticate(request)
            if result is None:
                origin = request.headers.get("Origin", "*")
                resp = JSONResponse(
                    status_code=401,
                    content={"code": 401, "data": None, "msg": "Token 无效或已过期，请重新登录"},
                )
                resp.headers["Access-Control-Allow-Origin"] = origin
                resp.headers["Access-Control-Allow-Credentials"] = "true"
                resp.headers["X-Request-ID"] = request_id
                logger.info(f"{request.method} {path} 401 (token 无效或已过期)")
                return resp
            user_id = result

        # 注入 request.state，供下游路由使用
        request.state.user_id = user_id
        request.state.request_id = request_id

        start = time.monotonic()

        with logger.contextualize(request_id=request_id, user_id=user_id, session_id=session_id):
            response = await call_next(request)
            elapsed = time.monotonic() - start

            response.headers["X-Request-ID"] = request_id
            response.headers["X-Elapsed"] = f"{elapsed:.3f}"

            logger.bind(elapsed=elapsed).info(
                f"{request.method} {request.url.path} {response.status_code}",
            )

        return response

    async def _authenticate(self, request: Request) -> str | None:
        """校验 JWT + Redis token，返回 user_id；失败返回 None"""
        auth_header = request.headers.get("Authorization", "")
        token = auth_header[7:] if auth_header.startswith("Bearer ") else ""

        if not token:
            return None

        # 1. 解析 JWT 获取 user_id
        user_id = get_user_id_from_token(token)
        if not user_id:
            return None

        # 2. 校验 Redis 中是否存在该 token
        try:
            redis = await get_redis()
            stored = await redis.get(f"{TOKEN_PREFIX}{user_id}")
            if stored != token:
                logger.warning(f"Token 无效或已过期: user_id={user_id}")
                return None
        except Exception as e:
            from src.core.config import settings
            if settings.DEBUG:
                logger.warning(f"Redis 校验失败（DEBUG 模式放行）: {e}")
            else:
                logger.error(f"Redis 校验失败（拒绝请求）: {e}")
                return None

        return user_id
