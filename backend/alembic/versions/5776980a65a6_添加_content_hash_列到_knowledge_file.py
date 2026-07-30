"""添加 content_hash 列到 knowledge_file

Revision ID: 5776980a65a6
Revises: 8a873a7049e3
Create Date: 2026-07-31 02:20:25.328156
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "5776980a65a6"
down_revision: Union[str, None] = "8a873a7049e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("knowledge_file", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_knowledge_file_content_hash"), "knowledge_file", ["content_hash"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_knowledge_file_content_hash"), table_name="knowledge_file")
    op.drop_column("knowledge_file", "content_hash")
