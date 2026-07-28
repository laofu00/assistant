"""初始迁移：创建所有基础表

Revision ID: 001
Revises:
Create Date: 2026-07-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 备忘录表
    op.create_table(
        "memos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("category", sa.String(20), server_default="未分类"),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_memos_user_id", "memos", ["user_id"])
    op.create_index("idx_memos_status", "memos", ["user_id", "status"])

    # Token 使用记录表
    op.create_table(
        "ai_token_usage",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("session_id", sa.String(128), nullable=True),
        sa.Column("user_id", sa.String(50), nullable=False),
        sa.Column("provider", sa.String(32), nullable=True),
        sa.Column("model_name", sa.String(64), nullable=True),
        sa.Column("input_tokens", sa.BigInteger(), server_default="0"),
        sa.Column("output_tokens", sa.BigInteger(), server_default="0"),
        sa.Column("total_tokens", sa.BigInteger(), server_default="0"),
        sa.Column("cache_creation_tokens", sa.BigInteger(), server_default="0"),
        sa.Column("cache_read_tokens", sa.BigInteger(), server_default="0"),
        sa.Column("cost_amount", sa.Numeric(10, 6), server_default="0"),
        sa.Column("intent_type", sa.String(32), nullable=True),
        sa.Column("call_purpose", sa.String(64), nullable=True),
        sa.Column("tool_called", sa.SmallInteger(), server_default="0"),
        sa.Column("tool_names", sa.String(256), nullable=True),
        sa.Column("tool_input", sa.Text(), nullable=True),
        sa.Column("tool_output", sa.Text(), nullable=True),
        sa.Column("tool_duration_ms", sa.Integer(), nullable=True),
        sa.Column("query_text", sa.Text(), nullable=True),
        sa.Column("response_length", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_token_trace_id", "ai_token_usage", ["trace_id"])
    op.create_index("idx_token_user_id", "ai_token_usage", ["user_id"])
    op.create_index("idx_token_created_at", "ai_token_usage", ["created_at"])

    # 工具审计日志表
    op.create_table(
        "tool_audit_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(50), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("action", sa.String(64), nullable=True),
        sa.Column("tool_input", sa.Text(), nullable=True),
        sa.Column("tool_output", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), server_default="1"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audit_trace_id", "tool_audit_log", ["trace_id"])
    op.create_index("idx_audit_user_id", "tool_audit_log", ["user_id"])

    # 知识库文件表
    op.create_table(
        "knowledge_file",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(50), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("file_type", sa.String(10), nullable=True),
        sa.Column("chunk_count", sa.Integer(), server_default="0"),
        sa.Column("status", sa.String(20), server_default="PENDING"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("process_time", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_knowledge_user_id", "knowledge_file", ["user_id"])


def downgrade() -> None:
    op.drop_table("knowledge_file")
    op.drop_table("tool_audit_log")
    op.drop_table("ai_token_usage")
    op.drop_table("memos")
