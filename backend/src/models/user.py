"""用户 ORM 模型 — 对齐 Java UserEntity"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class User(Base):
    __tablename__ = "user_info"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(100))
    avatar: Mapped[str | None] = mapped_column(String(500))
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(100))
    gender: Mapped[int | None] = mapped_column(Integer, default=0)
    status: Mapped[int] = mapped_column(Integer, default=1)  # 1:正常 0:禁用
    roles: Mapped[str | None] = mapped_column(String(500))  # 逗号分隔
    permissions: Mapped[str | None] = mapped_column(String(1000))  # 逗号分隔
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    deleted: Mapped[int] = mapped_column(Integer, default=0)  # 0:正常 1:删除

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', status={self.status})>"
