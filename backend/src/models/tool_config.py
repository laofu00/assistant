"""工具配置持久化 ORM 模型 — 记录哪些工具被管理员禁用"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class ToolConfig(Base):
    __tablename__ = "tool_config"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<ToolConfig(tool='{self.tool_name}', enabled={self.enabled})>"
