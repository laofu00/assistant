"""Alembic 迁移环境配置（异步 PostgreSQL）"""

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

# 将 backend 目录加入 sys.path，确保 from src.xxx import 可运行
sys.path.insert(0, str(Path(__file__).parent.parent))

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.config import settings
from src.core.database import Base

# 导入所有 ORM 模型以确保 Base.metadata 完整
import src.models.memo  # noqa: F401
import src.models.token_usage  # noqa: F401
import src.models.tool_audit  # noqa: F401
import src.models.knowledge_file  # noqa: F401
import src.models.user  # noqa: F401
import src.models.user_preference  # noqa: F401
import src.models.user_token  # noqa: F401
import src.models.operation_log  # noqa: F401
import src.models.user_notification  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线迁移（生成 SQL 脚本）"""
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """在线迁移（连接数据库执行）"""
    connectable = create_async_engine(settings.DATABASE_URL)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
