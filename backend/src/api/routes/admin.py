"""管理端点 — PUT /admin/log-level, POST /admin/cache/clear, POST /admin/backup/chromadb, 用户管理"""

from fastapi import APIRouter, Depends, Query
from loguru import logger
from sqlalchemy import func, select

from src.core.auth_deps import require_admin
from src.core.cache import tool_cache
from src.core.database import async_session_factory
from src.core.schema import R
from src.models.user import User
from src.models.user_tool_blacklist import UserToolBlacklist
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


@router.get("/users")
async def list_users(
    keyword: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
):
    """管理员列出所有用户及禁用工具数"""
    async with async_session_factory() as session:
        # 查询用户
        stmt = select(User).where(User.deleted == 0)
        if keyword:
            stmt = stmt.where(
                User.username.ilike(f"%{keyword}%")
                | User.nickname.ilike(f"%{keyword}%")
            )
        stmt = stmt.order_by(User.created_at.desc()).offset((page - 1) * size).limit(size)
        result = await session.execute(stmt)
        users = result.scalars().all()

        # 查询总数
        count_stmt = select(func.count(User.id)).where(User.deleted == 0)
        if keyword:
            count_stmt = count_stmt.where(
                User.username.ilike(f"%{keyword}%")
                | User.nickname.ilike(f"%{keyword}%")
            )
        total = (await session.execute(count_stmt)).scalar() or 0

        # 查询每个用户的禁用工具数
        user_ids = [u.user_id for u in users]
        blacklist_counts: dict[str, int] = {}
        if user_ids:
            bl_stmt = (
                select(UserToolBlacklist.user_id, func.count(UserToolBlacklist.id))
                .where(UserToolBlacklist.user_id.in_(user_ids))
                .group_by(UserToolBlacklist.user_id)
            )
            bl_result = await session.execute(bl_stmt)
            blacklist_counts = {row[0]: row[1] for row in bl_result}

        items = [
            {
                "userId": u.user_id,
                "username": u.username,
                "nickname": u.nickname,
                "email": u.email,
                "roles": u.roles,
                "status": u.status,
                "disabledToolCount": blacklist_counts.get(u.user_id, 0),
                "createdAt": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ]

        return R.ok({"total": total, "page": page, "size": size, "items": items})
