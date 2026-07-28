"""对齐Java表结构

Revision ID: 15071c38ae86
Revises: 001
Create Date: 2026-07-27 20:23:16.495514
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '15071c38ae86'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==================== 1. memos → memo（rename + status 类型改造） ====================
    # 先移除 VARCHAR 默认值，再改类型
    op.execute("ALTER TABLE memos ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE memos ALTER COLUMN status TYPE integer USING "
        "CASE status WHEN 'pending' THEN 1 WHEN 'completed' THEN 2 WHEN 'deleted' THEN 0 ELSE 1 END"
    )
    op.execute("ALTER TABLE memos ALTER COLUMN status SET DEFAULT 1")
    op.alter_column('memos', 'status', existing_type=sa.Integer(), nullable=False, server_default=sa.text('1'))
    op.rename_table('memos', 'memo')

    # ==================== 2. 新建 user_info ====================
    op.create_table('user_info',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.String(length=50), nullable=False),
        sa.Column('username', sa.String(length=50), nullable=False),
        sa.Column('password', sa.String(length=255), nullable=False),
        sa.Column('nickname', sa.String(length=100), nullable=True),
        sa.Column('avatar', sa.String(length=500), nullable=True),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('email', sa.String(length=100), nullable=True),
        sa.Column('gender', sa.Integer(), nullable=True),
        sa.Column('status', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('roles', sa.String(length=500), nullable=True),
        sa.Column('permissions', sa.String(length=1000), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('deleted', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
    )
    op.create_index('ix_user_info_user_id', 'user_info', ['user_id'], unique=True)

    # ==================== 3. 新建 user_preference ====================
    op.create_table('user_preference',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.String(length=50), nullable=False),
        sa.Column('language', sa.String(length=20), nullable=True),
        sa.Column('theme', sa.String(length=20), nullable=True),
        sa.Column('timezone', sa.String(length=50), nullable=True),
        sa.Column('notification_settings', sa.Text(), nullable=True),
        sa.Column('privacy_settings', sa.Text(), nullable=True),
        sa.Column('device_preferences', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('deleted', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_user_preference_user_id', 'user_preference', ['user_id'], unique=True)

    # ==================== 4. ai_token_usage 补字段 ====================
    op.add_column('ai_token_usage', sa.Column('input_unit_price', sa.Numeric(precision=10, scale=6), nullable=True))
    op.add_column('ai_token_usage', sa.Column('output_unit_price', sa.Numeric(precision=10, scale=6), nullable=True))
    op.add_column('ai_token_usage', sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False))
    op.add_column('ai_token_usage', sa.Column('deleted', sa.Integer(), nullable=False, server_default=sa.text('0')))

    # ==================== 5. tool_audit_log 字段对齐 ====================
    op.add_column('tool_audit_log', sa.Column('conversation_id', sa.String(length=128), nullable=True))
    op.add_column('tool_audit_log', sa.Column('result', sa.String(length=20), nullable=True))
    # success(Boolean) → result(String): 做数据迁移
    op.execute("UPDATE tool_audit_log SET result = CASE WHEN success THEN 'SUCCESS' ELSE 'FAILED' END")
    op.drop_column('tool_audit_log', 'success')
    # error_message → error_msg（rename）
    op.alter_column('tool_audit_log', 'error_message', new_column_name='error_msg', existing_type=sa.Text(), nullable=True)
    op.add_column('tool_audit_log', sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False))

    # ==================== 6. index 重命名（对齐 SQLAlchemy 命名规范） ====================
    # ai_token_usage
    op.drop_index('idx_token_trace_id', table_name='ai_token_usage')
    op.drop_index('idx_token_user_id', table_name='ai_token_usage')
    op.drop_index('idx_token_created_at', table_name='ai_token_usage')
    op.create_index('ix_ai_token_usage_trace_id', 'ai_token_usage', ['trace_id'])
    op.create_index('ix_ai_token_usage_user_id', 'ai_token_usage', ['user_id'])
    op.create_index('ix_ai_token_usage_created_at', 'ai_token_usage', ['created_at'])
    # tool_audit_log
    op.drop_index('idx_audit_trace_id', table_name='tool_audit_log')
    op.drop_index('idx_audit_user_id', table_name='tool_audit_log')
    op.create_index('ix_tool_audit_log_trace_id', 'tool_audit_log', ['trace_id'])
    op.create_index('ix_tool_audit_log_user_id', 'tool_audit_log', ['user_id'])
    # knowledge_file
    op.drop_index('idx_knowledge_user_id', table_name='knowledge_file')
    op.create_index('ix_knowledge_file_user_id', 'knowledge_file', ['user_id'])


def downgrade() -> None:
    # index 回退
    op.drop_index('ix_knowledge_file_user_id', table_name='knowledge_file')
    op.create_index('idx_knowledge_user_id', 'knowledge_file', ['user_id'])
    op.drop_index('ix_tool_audit_log_user_id', table_name='tool_audit_log')
    op.drop_index('ix_tool_audit_log_trace_id', table_name='tool_audit_log')
    op.create_index('idx_audit_user_id', 'tool_audit_log', ['user_id'])
    op.create_index('idx_audit_trace_id', 'tool_audit_log', ['trace_id'])
    op.drop_index('ix_ai_token_usage_created_at', table_name='ai_token_usage')
    op.drop_index('ix_ai_token_usage_user_id', table_name='ai_token_usage')
    op.drop_index('ix_ai_token_usage_trace_id', table_name='ai_token_usage')
    op.create_index('idx_token_created_at', 'ai_token_usage', ['created_at'])
    op.create_index('idx_token_user_id', 'ai_token_usage', ['user_id'])
    op.create_index('idx_token_trace_id', 'ai_token_usage', ['trace_id'])

    # tool_audit_log 回退
    op.drop_column('tool_audit_log', 'updated_at')
    op.alter_column('tool_audit_log', 'error_msg', new_column_name='error_message', existing_type=sa.Text(), nullable=True)
    op.add_column('tool_audit_log', sa.Column('success', sa.Boolean(), server_default=sa.text('true'), nullable=True))
    op.execute("UPDATE tool_audit_log SET success = (result = 'SUCCESS')")
    op.drop_column('tool_audit_log', 'result')
    op.drop_column('tool_audit_log', 'conversation_id')

    # ai_token_usage 回退
    op.drop_column('ai_token_usage', 'deleted')
    op.drop_column('ai_token_usage', 'updated_at')
    op.drop_column('ai_token_usage', 'output_unit_price')
    op.drop_column('ai_token_usage', 'input_unit_price')

    # user_preference 回退
    op.drop_index('ix_user_preference_user_id', table_name='user_preference')
    op.drop_table('user_preference')

    # user_info 回退
    op.drop_index('ix_user_info_user_id', table_name='user_info')
    op.drop_table('user_info')

    # memo → memos 回退
    op.rename_table('memo', 'memos')
    op.execute("ALTER TABLE memos ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE memos ALTER COLUMN status TYPE varchar(20) USING "
        "CASE status WHEN 0 THEN 'deleted' WHEN 2 THEN 'completed' ELSE 'pending' END"
    )
    op.execute("ALTER TABLE memos ALTER COLUMN status SET DEFAULT 'pending'")
    op.alter_column('memos', 'status', existing_type=sa.String(20), nullable=True, server_default=sa.text("'pending'::character varying"))
