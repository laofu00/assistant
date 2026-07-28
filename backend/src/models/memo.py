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


# 自动分类规则（对齐 Java 版）
CATEGORY_RULES: dict[str, str] = {
    "会议": "工作", "开会": "工作", "讨论": "工作", "汇报": "工作",
    "面试": "工作", "培训": "工作",
    "生日": "生活", "聚会": "生活", "聚餐": "生活", "活动": "生活",
    "旅游": "生活", "出行": "生活",
    "提醒": "待办", "todo": "待办", "待办": "待办", "任务": "待办",
    "完成": "待办",
    "学习": "学习", "读书": "学习", "阅读": "学习", "课程": "学习",
    "作业": "学习",
    "重要": "重要", "紧急": "重要", "尽快": "重要",
}


def classify_memo(title: str, content: str | None = None) -> str:
    """根据标题和内容自动分类"""
    text = f"{title or ''} {content or ''}".lower()
    for keyword, category in CATEGORY_RULES.items():
        if keyword.lower() in text:
            return category
    return "未分类"
