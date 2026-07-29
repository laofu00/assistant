"""管理端点 — PUT /admin/log-level, POST /admin/cache/clear, POST /admin/backup/chromadb"""

from fastapi import APIRouter, Depends, Query
from loguru import logger

from src.core.auth_deps import require_admin
from src.core.cache import tool_cache
from src.core.schema import R
from src.token.dead_letter import dead_letter

router = APIRouter(prefix="/admin", tags=["管理"], dependencies=[Depends(require_admin)])


@router.put("/log-level")
async def set_log_level(level: str = Query(default="INFO")):
    """动态调整日志级别"""
    valid_levels = {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}
    if level.upper() not in valid_levels:
        return R.error(400, f"无效的日志级别: {level}，支持: {valid_levels}")

    logger.remove()
    from src.core.logging_config import setup_logging
    setup_logging(level.upper())
    return R.ok(None, f"日志级别已更新为 {level.upper()}")


@router.post("/cache/clear")
async def clear_cache():
    """清理工具降级缓存"""
    count = len(tool_cache)
    tool_cache.clear()
    return R.ok({"cleared": count}, f"已清理 {count} 条缓存")


@router.get("/dead-letter/count")
async def dead_letter_count():
    """查询死信队列待处理数量"""
    count = await dead_letter.get_pending_count()
    return R.ok({"pending": count})


@router.post("/dead-letter/retry")
async def retry_dead_letter():
    """重试死信队列"""
    count = await dead_letter.retry_pending()
    return R.ok({"retried": count}, f"已重试 {count} 条死信")
