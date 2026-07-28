"""API 路由注册"""

from src.api.routes import admin, auth, chat, health, knowledge, memo, token, tools, user

__all__ = ["chat", "health", "knowledge", "memo", "token", "tools", "admin", "auth", "user"]
