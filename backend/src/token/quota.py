"""Token 配额检查 — 单日用量限制 + 阈值告警

对齐 Java 版 TokenQuotaService
"""

import asyncio
from datetime import date

from loguru import logger
from sqlalchemy import func, select

from src.core.config import settings
from src.core.database import async_session_factory
from src.core.exceptions import TokenQuotaExceededError
from src.models.token_usage import TokenUsage


class QuotaChecker:
    """Token 配额检查器"""

    async def get_today_usage(self, user_id: str) -> dict:
        """获取用户今日用量摘要"""
        today = date.today()
        async with async_session_factory() as session:
            result = await session.execute(
                select(
                    func.coalesce(func.sum(TokenUsage.total_tokens), 0).label("tokens"),
                    func.coalesce(func.sum(TokenUsage.cost_amount), 0).label("cost"),
                    func.count(TokenUsage.id).label("requests"),
                ).where(
                    TokenUsage.user_id == user_id,
                    func.date(TokenUsage.created_at) == today,
                )
            )
            row = result.one_or_none()
            if row is None:
                return {"tokens": 0, "cost": 0.0, "requests": 0}
            return {
                "tokens": int(row[0]),
                "cost": float(row[1]),
                "requests": int(row[2]),
            }

    async def check_quota(self, user_id: str) -> None:
        """检查配额，超限抛异常"""
        usage = await self.get_today_usage(user_id)

        if usage["tokens"] >= settings.TOKEN_DAILY_LIMIT:
            raise TokenQuotaExceededError(user_id, settings.TOKEN_DAILY_LIMIT)

        if usage["cost"] >= settings.TOKEN_DAILY_COST_LIMIT:
            raise TokenQuotaExceededError(
                f"用户 [{user_id}] 今日费用已达上限（¥{settings.TOKEN_DAILY_COST_LIMIT}）"
            )

        # 阈值告警（异步，不阻断）
        ratio = usage["tokens"] / settings.TOKEN_DAILY_LIMIT if settings.TOKEN_DAILY_LIMIT > 0 else 0
        if ratio >= settings.TOKEN_ALERT_THRESHOLD:
            logger.warning(
                f"Token 用量告警: user={user_id}, tokens={usage['tokens']}/{settings.TOKEN_DAILY_LIMIT} ({ratio:.0%})"
            )
            if settings.TOKEN_ALERT_WEBHOOK:
                asyncio.create_task(self._send_alert(user_id, usage))

    async def _send_alert(self, user_id: str, usage: dict) -> None:
        """发送告警（Webhook）"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as s:
                await s.post(settings.TOKEN_ALERT_WEBHOOK, json={
                    "user_id": user_id,
                    "tokens": usage["tokens"],
                    "limit": settings.TOKEN_DAILY_LIMIT,
                    "ratio": usage["tokens"] / settings.TOKEN_DAILY_LIMIT,
                }, timeout=aiohttp.ClientTimeout(total=5))
        except Exception as e:
            logger.warning(f"告警 Webhook 发送失败: {e}")


# 全局实例
quota_checker = QuotaChecker()
