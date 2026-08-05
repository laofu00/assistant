"""Token 统计路由 — GET /token/records, /statistics, /by-model, /by-date, /quota

管理员查询全部用户数据，普通用户仅查询自己
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from src.core.auth_deps import get_current_user_id, is_admin_user
from src.core.schema import R
from src.token.statistics import statistics_service

router = APIRouter(prefix="/token", tags=["Token统计"], dependencies=[Depends(get_current_user_id)])


async def _get_token_user_id(user_id: str) -> str | None:
    """管理员 → None（查全部）；普通用户 → 仅查自己"""
    if await is_admin_user(user_id):
        return None
    return user_id


@router.get("/records")
async def get_records(
    user_id: str = Depends(get_current_user_id),
    start_time: str | None = Query(default=None),
    end_time: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
):
    """Token 使用记录（分页）"""
    start = datetime.fromisoformat(start_time) if start_time else None
    end = datetime.fromisoformat(end_time) if end_time else None
    result = await statistics_service.query_records(await _get_token_user_id(user_id), start, end, page, size)
    records = [
        {
            "id": r.id,
            "traceId": r.trace_id,
            "modelName": r.model_name,
            "inputTokens": r.input_tokens,
            "outputTokens": r.output_tokens,
            "totalTokens": r.total_tokens,
            "costAmount": float(r.cost_amount),
            "intentType": r.intent_type,
            "toolCalled": r.tool_called,
            "createTime": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None,
        }
        for r in result["records"]
    ]
    return R.ok({"records": records, "total": result["total"], "page": result["page"], "size": result["size"]})


@router.get("/statistics")
async def get_statistics(
    user_id: str = Depends(get_current_user_id),
    start_time: str | None = Query(default=None),
    end_time: str | None = Query(default=None),
):
    """汇总统计"""
    start = datetime.fromisoformat(start_time) if start_time else None
    end = datetime.fromisoformat(end_time) if end_time else None
    result = await statistics_service.get_statistics(await _get_token_user_id(user_id), start, end)
    return R.ok({
        "totalTokens": result["total_tokens"],
        "totalInputTokens": result["total_input_tokens"],
        "totalOutputTokens": result["total_output_tokens"],
        "totalCost": result["total_cost"],
        "requestCount": result["request_count"],
        "toolCallCount": result["tool_call_count"],
        "avgTokensPerRequest": result["avg_tokens_per_request"],
    })


@router.get("/by-model")
async def get_by_model(
    user_id: str = Depends(get_current_user_id),
    start_time: str | None = Query(default=None),
    end_time: str | None = Query(default=None),
):
    """按模型分组统计"""
    start = datetime.fromisoformat(start_time) if start_time else None
    end = datetime.fromisoformat(end_time) if end_time else None
    result = await statistics_service.get_by_model(await _get_token_user_id(user_id), start, end)
    return R.ok(result)


@router.get("/by-date")
async def get_by_date(
    user_id: str = Depends(get_current_user_id),
    start_time: str | None = Query(default=None),
    end_time: str | None = Query(default=None),
):
    """按日期分组统计"""
    start = datetime.fromisoformat(start_time) if start_time else None
    end = datetime.fromisoformat(end_time) if end_time else None
    result = await statistics_service.get_by_date(await _get_token_user_id(user_id), start, end)
    return R.ok(result)


@router.get("/quota")
async def get_quota(user_id: str = Depends(get_current_user_id)):
    """今日用量摘要"""
    result = await statistics_service.get_today_usage(await _get_token_user_id(user_id))
    result["daily_limit"] = 500_000
    result["cost_limit"] = 10.0
    return R.ok(result)
