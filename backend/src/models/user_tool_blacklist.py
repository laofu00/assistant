"""用户工具黑名单 ORM 模型 — 管理员可针对特定用户禁用工具"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class UserToolBlacklist(Base):
    __tablename__ = "user_tool_blacklist"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<UserToolBlacklist(user='{self.user_id}', tool='{self.tool_name}')>"
