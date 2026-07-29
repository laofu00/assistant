"""Redis 客户端 — 异步连接池"""

import asyncio

import redis.asyncio as aioredis

from src.core.config import settings

_redis: aioredis.Redis | None = None
_lock = asyncio.Lock()


async def get_redis() -> aioredis.Redis:
    """获取 Redis 客户端（懒加载单例，线程安全）"""
    global _redis
    if _redis is None:
        async with _lock:
            if _redis is None:
                _redis = aioredis.from_url(
                    settings.REDIS_URL,
                    password=settings.REDIS_PASSWORD or None,
                    encoding="utf-8",
                    decode_responses=True,
                    max_connections=10,
                )
    return _redis


async def close_redis() -> None:
    """关闭 Redis 连接"""
    global _redis
    if _redis is not None:
        await _redis.close()
        _redis = None


# Token 相关 key 前缀
TOKEN_PREFIX = "token:"
TOKEN_EXPIRE_SECONDS = 86400  # 24 小时，与 JWT_EXPIRE_MINUTES 一致
