"""Token 使用记录 ORM 模型"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, Numeric, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class TokenUsage(Base):
    __tablename__ = "ai_token_usage"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(String(128))
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    provider: Mapped[str | None] = mapped_column(String(32))  # dashscope/ollama/openai/anthropic
    model_name: Mapped[str | None] = mapped_column(String(64))  # qwen-plus/gpt-4o/...
    input_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    total_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    cache_creation_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    cost_amount: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    input_unit_price: Mapped[float | None] = mapped_column(Numeric(10, 6))  # 输入token单价（元/千token）
    output_unit_price: Mapped[float | None] = mapped_column(Numeric(10, 6))  # 输出token单价（元/千token）
    intent_type: Mapped[str | None] = mapped_column(String(32))  # GENERAL/KNOWLEDGE/MEMO/WORKFLOW/...
    call_purpose: Mapped[str | None] = mapped_column(String(64))
    tool_called: Mapped[int] = mapped_column(SmallInteger, default=0)
    tool_names: Mapped[str | None] = mapped_column(String(256))
    tool_input: Mapped[str | None] = mapped_column(Text)
    tool_output: Mapped[str | None] = mapped_column(Text)
    tool_duration_ms: Mapped[int | None] = mapped_column(Integer)
    query_text: Mapped[str | None] = mapped_column(Text)
    response_length: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    deleted: Mapped[int] = mapped_column(Integer, default=0)  # 0:正常 1:删除

    def __repr__(self) -> str:
        return f"<TokenUsage(user='{self.user_id}', model='{self.model_name}', tokens={self.total_tokens})>"
