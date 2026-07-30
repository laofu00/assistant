"""知识库文件元数据 ORM 模型（含处理状态机）"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class KnowledgeFile(Base):
    __tablename__ = "knowledge_file"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(500))
    file_type: Mapped[str | None] = mapped_column(String(10))  # txt/pdf/doc/docx/xls/xlsx
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)  # SHA256
    version: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[int] = mapped_column(Integer, default=1, index=True)  # 1=有效 0=旧版本
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING/PROCESSING/COMPLETED/FAILED
    error_message: Mapped[str | None] = mapped_column(Text)
    process_time: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<KnowledgeFile(name='{self.file_name}', status='{self.status}', chunks={self.chunk_count})>"
