"""API 全局限流中间件 — Redis 滑动窗口

架构:
  第一层: 路径级限流 — 按 URL 前缀匹配，每路径独立配额
  第二层: IP 级限流 — 单 IP 全局 QPS 上限
  第三层: 用户级限流 — 单用户全局 QPS 上限（基于 JWT user_id）

全部通过才放行，任何一层不通过即返回 429。
"""

from fastapi import Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.core.config import settings
from src.core.redis_client import get_redis

# Lua 原子操作脚本
_ACQUIRE_SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local current = redis.call('INCR', key)
if current == 1 then
    redis.call('EXPIRE', key, window)
end
if current > limit then
    return 0
end
return 1
"""


class ApiRateLimitMiddleware(BaseHTTPMiddleware):
    """API 入口全局限流 — Redis 原子计数 + 滑动窗口"""

    def __init__(self, app) -> None:
        super().__init__(app)
        self._script_hash: str | None = None

    async def _load_script(self) -> str:
        if self._script_hash is None:
            r = await get_redis()
            self._script_hash = await r.script_load(_ACQUIRE_SCRIPT)
        return self._script_hash

    def _get_path_limit(self, path: str) -> int:
        """根据路径前缀匹配限流额度"""
        limits = settings.API_RATE_LIMITS
        for prefix in sorted(limits.keys(), key=len, reverse=True):
            if prefix == "/api/v1/_default":
                continue
            if path.startswith(prefix):
                return limits[prefix]
        return limits.get("/api/v1/_default", 60)

    def _get_client_ip(self, request: Request) -> str:
        """获取客户端 IP（优先 X-Forwarded-For）"""
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        client = request.client
        return client.host if client else "unknown"

    def _get_user_id(self, request: Request) -> str:
        """从 Authorization header 解析 JWT 获取 user_id（限流在认证之前，需自己解析）"""
        from src.core.jwt_utils import get_user_id_from_token

        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            uid = get_user_id_from_token(auth[7:])
            if uid:
                return uid
        return "anonymous"

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        ip = self._get_client_ip(request)
        user_id = self._get_user_id(request)

        r = await get_redis()
        sha = await self._load_script()
        window = 60

        # ── 第一层：路径级限流 ──
        path_limit = self._get_path_limit(path)
        if path_limit > 0:
            path_key = f"apirate:path:{path}:{ip}:minute"
            ok = await r.evalsha(sha, 1, path_key, path_limit, window)
            if not ok:
                logger.warning(f"API 限流-路径: {path} IP={ip} limit={path_limit}")
                return JSONResponse(
                    status_code=429,
                    content={"code": 429, "data": None, "msg": f"请求过于频繁，{path_limit}次/分钟"},
                    headers={"Retry-After": str(window), "X-RateLimit-Limit": str(path_limit)},
                )

        # ── 第二层：IP 级全局限流 ──
        ip_limit = settings.API_RATE_LIMIT_IP_PER_MINUTE
        if ip_limit > 0:
            ip_key = f"apirate:ip:{ip}:minute"
            ok = await r.evalsha(sha, 1, ip_key, ip_limit, window)
            if not ok:
                logger.warning(f"API 限流-IP: {ip} limit={ip_limit}")
                return JSONResponse(
                    status_code=429,
                    content={"code": 429, "data": None, "msg": "请求过于频繁，请稍后重试"},
                    headers={"Retry-After": str(window), "X-RateLimit-Limit": str(ip_limit)},
                )

        # ── 第三层：用户级全局限流（非匿名用户）──
        if user_id != "anonymous":
            user_limit = settings.API_RATE_LIMIT_USER_PER_MINUTE
            if user_limit > 0:
                user_key = f"apirate:user:{user_id}:minute"
                ok = await r.evalsha(sha, 1, user_key, user_limit, window)
                if not ok:
                    logger.warning(f"API 限流-用户: user={user_id} limit={user_limit}")
                    return JSONResponse(
                        status_code=429,
                        content={"code": 429, "data": None, "msg": "请求过于频繁，请稍后重试"},
                        headers={"Retry-After": str(window), "X-RateLimit-Limit": str(user_limit)},
                    )

        return await call_next(request)

