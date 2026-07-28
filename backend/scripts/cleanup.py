#!/usr/bin/env python
"""数据清理 — 定期清理过期的审计日志和 Token 记录"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import delete
from src.core.config import settings
from src.core.database import async_session_factory
from src.models.tool_audit import ToolAuditLog
from src.models.token_usage import TokenUsage


async def cleanup() -> None:
    """清理过期数据"""
    audit_cutoff = datetime.now(timezone.utc) - timedelta(days=settings.AUDIT_LOG_RETENTION_DAYS)
    token_cutoff = datetime.now(timezone.utc) - timedelta(days=settings.TOKEN_USAGE_RETENTION_DAYS)

    async with async_session_factory() as session:
        r1 = await session.execute(delete(ToolAuditLog).where(ToolAuditLog.created_at < audit_cutoff))
        r2 = await session.execute(delete(TokenUsage).where(TokenUsage.created_at < token_cutoff))
        await session.commit()
        print(f"清理完成: 审计日志 {r1.rowcount} 条, Token 记录 {r2.rowcount} 条")


if __name__ == "__main__":
    asyncio.run(cleanup())
