"""用户令牌 ORM 模型 — 对齐 Java user_token 表"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class UserToken(Base):
    __tablename__ = "user_token"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(2000), nullable=False)
    token_type: Mapped[str] = mapped_column(String(20), nullable=False)  # ACCESS / REFRESH
    expired_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<UserToken(user_id='{self.user_id}', type='{self.token_type}')>"
