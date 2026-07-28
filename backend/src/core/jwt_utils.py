"""JWT 工具 — Token 生成 + 解析"""

from datetime import datetime, timedelta, timezone

import jwt

from src.core.config import settings

_ALGORITHM = "HS256"


def create_token(user_id: str, username: str, roles: str = "READ_WRITE") -> str:
    """生成 JWT access token"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "username": username,
        "roles": roles,
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=_ALGORITHM)


def verify_token(token: str) -> dict:
    """验证并解析 JWT token，返回 payload；无效则抛出异常"""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[_ALGORITHM])


def get_user_id_from_token(token: str) -> str | None:
    """从 token 中安全提取 user_id"""
    try:
        payload = verify_token(token)
        return payload.get("sub")
    except jwt.PyJWTError:
        return None
