"""用户偏好 ORM 模型 — 对齐 Java UserPreferenceEntity"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class UserPreference(Base):
    __tablename__ = "user_preference"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    language: Mapped[str | None] = mapped_column(String(20), default="zh-CN")
    theme: Mapped[str | None] = mapped_column(String(20), default="light")
    timezone: Mapped[str | None] = mapped_column(String(50), default="Asia/Shanghai")
    notification_settings: Mapped[str | None] = mapped_column(Text)  # JSON 字符串
    privacy_settings: Mapped[str | None] = mapped_column(Text)  # JSON 字符串
    device_preferences: Mapped[str | None] = mapped_column(Text)  # JSON 字符串
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    deleted: Mapped[int] = mapped_column(Integer, default=0)  # 0:正常 1:删除

    def __repr__(self) -> str:
        return f"<UserPreference(user_id='{self.user_id}', language='{self.language}')>"
