"""Token 统计查询 — 分页记录 + 汇总 + 按模型/按日期分组

对齐 Java 版 TokenUsageService

user_id=None 表示查询全部用户数据（管理员视角）
"""

from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import async_session_factory
from src.models.token_usage import TokenUsage


def _build_conditions(user_id: str | None, start_time, end_time) -> list:
    conditions = []
    if user_id is not None:
        conditions.append(TokenUsage.user_id == user_id)
    if start_time:
        conditions.append(TokenUsage.created_at >= start_time)
    if end_time:
        conditions.append(TokenUsage.created_at <= end_time)
    return conditions


class StatisticsService:
    """Token 使用统计服务"""

    async def query_records(
        self, user_id: str | None, start_time: datetime | None = None, end_time: datetime | None = None,
        page: int = 1, size: int = 20,
    ) -> dict:
        """分页查询 Token 使用记录"""
        async with async_session_factory() as session:
            conditions = _build_conditions(user_id, start_time, end_time)

            total = (await session.execute(select(func.count(TokenUsage.id)).where(*conditions))).scalar() or 0

            offset = (max(1, page) - 1) * size
            query = select(TokenUsage).where(*conditions).order_by(TokenUsage.created_at.desc()).offset(offset).limit(size)
            result = await session.execute(query)
            records = result.scalars().all()

            return {
                "records": records,
                "total": total,
                "page": page,
                "size": size,
            }

    async def get_statistics(
        self, user_id: str | None, start_time: datetime | None = None, end_time: datetime | None = None,
    ) -> dict:
        """汇总统计"""
        async with async_session_factory() as session:
            conditions = _build_conditions(user_id, start_time, end_time)

            result = await session.execute(
                select(
                    func.coalesce(func.sum(TokenUsage.input_tokens), 0),
                    func.coalesce(func.sum(TokenUsage.output_tokens), 0),
                    func.coalesce(func.sum(TokenUsage.total_tokens), 0),
                    func.coalesce(func.sum(TokenUsage.cost_amount), 0),
                    func.count(TokenUsage.id),
                    func.coalesce(func.sum(TokenUsage.tool_called), 0),
                ).where(*conditions)
            )
            row = result.one_or_none()
            if row is None:
                return {"total_tokens": 0, "total_cost": 0, "request_count": 0}

            total_tokens = int(row[2])
            request_count = int(row[4])
            avg = (total_tokens / request_count) if request_count > 0 else 0

            return {
                "total_input_tokens": int(row[0]),
                "total_output_tokens": int(row[1]),
                "total_tokens": total_tokens,
                "total_cost": float(row[3]),
                "request_count": request_count,
                "tool_call_count": int(row[5]),
                "avg_tokens_per_request": round(avg, 1),
            }

    async def get_by_model(
        self, user_id: str | None, start_time: datetime | None = None, end_time: datetime | None = None,
    ) -> list[dict]:
        """按模型分组统计"""
        async with async_session_factory() as session:
            conditions = _build_conditions(user_id, start_time, end_time)

            result = await session.execute(
                select(
                    TokenUsage.model_name,
                    func.count(TokenUsage.id),
                    func.sum(TokenUsage.total_tokens),
                    func.sum(TokenUsage.cost_amount),
                ).where(*conditions).group_by(TokenUsage.model_name).order_by(func.sum(TokenUsage.total_tokens).desc())
            )
            return [
                {"model": row[0] or "unknown", "count": row[1], "total_tokens": int(row[2] or 0), "total_cost": float(row[3] or 0)}
                for row in result.all()
            ]

    async def get_by_date(
        self, user_id: str | None, start_time: datetime | None = None, end_time: datetime | None = None,
    ) -> list[dict]:
        """按日期分组统计"""
        async with async_session_factory() as session:
            conditions = _build_conditions(user_id, start_time, end_time)

            result = await session.execute(
                select(
                    func.date(TokenUsage.created_at),
                    func.count(TokenUsage.id),
                    func.sum(TokenUsage.total_tokens),
                    func.sum(TokenUsage.cost_amount),
                ).where(*conditions).group_by(func.date(TokenUsage.created_at)).order_by(func.date(TokenUsage.created_at).desc())
            )
            return [
                {"date": str(row[0]), "count": row[1], "total_tokens": int(row[2] or 0), "total_cost": float(row[3] or 0)}
                for row in result.all()
            ]

    async def get_today_usage(self, user_id: str | None) -> dict:
        """今日用量摘要"""
        today = date.today()
        async with async_session_factory() as session:
            conditions = [func.date(TokenUsage.created_at) == today]
            if user_id is not None:
                conditions.append(TokenUsage.user_id == user_id)
            result = await session.execute(
                select(
                    func.coalesce(func.sum(TokenUsage.total_tokens), 0),
                    func.coalesce(func.sum(TokenUsage.cost_amount), 0),
                    func.count(TokenUsage.id),
                ).where(*conditions)
            )
            row = result.one_or_none()
            if row is None:
                return {"today_tokens": 0, "today_cost": 0.0, "request_count": 0}
            return {
                "today_tokens": int(row[0]),
                "today_cost": float(row[1]),
                "request_count": int(row[2]),
            }


# 全局实例
statistics_service = StatisticsService()
