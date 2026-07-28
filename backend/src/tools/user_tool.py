"""用户工具 — @tool 封装（1 个方法，含内存缓存 + 降级）

对齐 Java 版 UserTool：getCurrentUserEmail + ConcurrentHashMap 缓存 + fallback
"""

import time

from langchain_core.tools import tool
from loguru import logger

# 内存缓存：userId → (email, expire_at)
_email_cache: dict[str, tuple[str, float]] = {}
_CACHE_TTL_SEC = 5 * 60  # 5 分钟


@tool
async def get_current_user_email(user_id: str) -> str | None:
    """获取当前用户注册的邮箱地址。当需要向用户发送邮件但用户未提供邮箱时调用。

    Args:
        user_id: 当前用户ID
    """
    # 1. 检查缓存
    cached = _email_cache.get(user_id)
    if cached:
        email, expire_at = cached
        if time.monotonic() < expire_at:
            return email

    # 2. 从 user_info 表查询
    try:
        from sqlalchemy import select
        from src.core.database import async_session_factory
        from src.models.user import User

        async with async_session_factory() as session:
            result = await session.execute(
                select(User.email).where(User.user_id == user_id, User.deleted == 0)
            )
            email = result.scalar_one_or_none()

        if email:
            _email_cache[user_id] = (email, time.monotonic() + _CACHE_TTL_SEC)
            logger.info(f"获取到用户邮箱: user_id={user_id}")
            return email

        return None
    except Exception as e:
        logger.error(f"获取用户邮箱失败: {e}")
        # 3. 降级：返回过期缓存
        if cached:
            return cached[0]
        return None
