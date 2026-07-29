"""备忘录 ORM 模型"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class Memo(Base):
    __tablename__ = "memo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(20), default="未分类")
    status: Mapped[int] = mapped_column(Integer, default=1)  # 1:正常 0:删除 2:完成
    due_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Memo(id={self.id}, title='{self.title}', status={self.status})>"
