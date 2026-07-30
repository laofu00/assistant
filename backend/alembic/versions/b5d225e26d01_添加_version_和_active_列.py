"""添加 version 和 active 列

Revision ID: b5d225e26d01
Revises: 5776980a65a6
Create Date: 2026-07-31 02:37:12.737889
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b5d225e26d01"
down_revision: Union[str, None] = "5776980a65a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("knowledge_file", sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")))
    op.add_column("knowledge_file", sa.Column("active", sa.Integer(), nullable=False, server_default=sa.text("1")))
    op.create_index(op.f("ix_knowledge_file_active"), "knowledge_file", ["active"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_knowledge_file_active"), table_name="knowledge_file")
    op.drop_column("knowledge_file", "active")
    op.drop_column("knowledge_file", "version")
