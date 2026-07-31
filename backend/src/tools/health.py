"""工具依赖健康检查 — 外部服务探测 + TTL 缓存

探测对象:
  - ChromaDB: heartbeat()
  - PostgreSQL: SELECT 1
  - SMTP: TCP 连接探测（不带认证）
  - 无依赖工具: 始终健康
"""

import asyncio
import time

from loguru import logger

from src.core.config import settings
from src.core.metrics import tool_health_status

# 工具 → 依赖类型映射
_TOOL_DEPENDENCY: dict[str, str] = {
    "search_knowledge": "chromadb",
    "upload_knowledge": "chromadb",
    "get_document_content": "chromadb",
    "list_knowledge": "chromadb",
    "delete_knowledge": "chromadb",
    "add_memo": "postgresql",
    "list_memos": "postgresql",
    "complete_memo": "postgresql",
    "delete_memo": "postgresql",
    "update_memo": "postgresql",
    "list_memos_by_date": "postgresql",
    "get_current_user_email": "postgresql",
    "do_send_email": "smtp",
    "do_send_formatted_email": "smtp",
    "preview_email": "smtp",
}

# 健康状态缓存: dependency → (healthy, expire_at)
_cache: dict[str, tuple[bool, float]] = {}
_cache_lock = asyncio.Lock()


async def check_tool_health(tool_name: str) -> bool:
    """检查指定工具的依赖是否健康

    缓存 TTL 由 TOOL_HEALTH_CHECK_INTERVAL 控制，避免每次调用都探测。
    """
    dependency = _TOOL_DEPENDENCY.get(tool_name)
    if dependency is None:
        # 无依赖工具（date_tool）：始终健康
        return True

    # 检查缓存
    cached = _cache.get(dependency)
    if cached and time.monotonic() < cached[1]:
        return cached[0]

    async with _cache_lock:
        # 双重检查
        cached = _cache.get(dependency)
        if cached and time.monotonic() < cached[1]:
            return cached[0]

        healthy = await _probe(dependency)
        ttl = settings.TOOL_HEALTH_CHECK_INTERVAL
        _cache[dependency] = (healthy, time.monotonic() + ttl)

        status_val = 1 if healthy else 0
        tool_health_status.labels(tool_name=tool_name, dependency=dependency).set(status_val)
        logger.debug(f"工具健康检查: tool={tool_name}, dep={dependency}, healthy={healthy}")

        return healthy


async def _probe(dependency: str) -> bool:
    """探测指定依赖"""
    try:
        if dependency == "chromadb":
            return await _probe_chromadb()
        elif dependency == "postgresql":
            return await _probe_postgresql()
        elif dependency == "smtp":
            return await _probe_smtp()
        return True
    except Exception as e:
        logger.warning(f"依赖健康探测失败: {dependency}, {e}")
        return False


async def _probe_chromadb() -> bool:
    """探测 ChromaDB"""
    try:
        from src.knowledge.vector_store import vector_store

        # heartbeat() 是同步方法，用线程池执行避免阻塞事件循环
        await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, vector_store.heartbeat),
            timeout=5,
        )
        return True
    except Exception:
        return False


async def _probe_postgresql() -> bool:
    """探测 PostgreSQL"""
    try:
        from sqlalchemy import text

        from src.core.database import async_session_factory

        async with async_session_factory() as session:
            await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=3)
        return True
    except Exception:
        return False


async def _probe_smtp() -> bool:
    """探测 SMTP（仅 TCP 连接，不认证）"""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(settings.SMTP_HOST, settings.SMTP_PORT),
            timeout=5,
        )
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


def get_all_health_status() -> dict[str, dict]:
    """获取所有依赖的健康状态（供管理 API 使用）"""
    result = {}
    for dep in ("chromadb", "postgresql", "smtp"):
        cached = _cache.get(dep)
        result[dep] = {
            "healthy": cached[0] if cached else None,
            "checked_at": cached[1] if cached else None,
        }
    return result
