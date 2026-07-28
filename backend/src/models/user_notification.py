"""用户通知 ORM 模型 — 对齐 Java user_notification 表"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class UserNotification(Base):
    __tablename__ = "user_notification"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    notification_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # system/device/scene/security
    priority: Mapped[int] = mapped_column(Integer, default=0)  # 0:低 1:中 2:高 3:紧急
    read_status: Mapped[int] = mapped_column(Integer, default=0)  # 0:未读 1:已读
    related_id: Mapped[str | None] = mapped_column(String(64))
    related_type: Mapped[str | None] = mapped_column(String(50))
    extra_data: Mapped[str | None] = mapped_column(Text)  # JSON
    expire_time: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    def __repr__(self) -> str:
        return f"<UserNotification(user='{self.user_id}', type='{self.type}', title='{self.title}')>"
