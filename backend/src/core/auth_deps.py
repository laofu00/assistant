"""认证依赖 — 从中间件注入的 request.state 读取已验证的 user_id"""

from fastapi import Request


async def get_current_user_id(request: Request) -> str:
    """获取当前请求的已验证 user_id（由 RequestContextMiddleware 注入）"""
    return getattr(request.state, "user_id", "anonymous")

