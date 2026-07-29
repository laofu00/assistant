"""认证依赖 — 从中间件注入的 request.state 读取已验证的 user_id"""

from fastapi import HTTPException, Request
from sqlalchemy import select

from src.core.database import async_session_factory
from src.models.user import User


async def get_current_user_id(request: Request) -> str:
    """获取当前请求的已验证 user_id（由 RequestContextMiddleware 注入）"""
    user_id = getattr(request.state, "user_id", "anonymous")
    if user_id == "anonymous":
        raise HTTPException(401, "未认证，请先登录")
    return user_id


async def require_admin(request: Request) -> str:
    """获取管理员权限已验证的 user_id，非管理员返回 403"""
    user_id = await get_current_user_id(request)
    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(401, "用户不存在")
    roles = (user.roles or "").split(",")
    if "admin" not in roles:
        raise HTTPException(403, "权限不足，需要管理员角色")
    return user_id

