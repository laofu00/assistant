"""备忘录工具 — @tool 封装（6 个方法）

对齐 Java 版 MemoTool：add/list/complete/delete/update/list_by_date + 自动分类 + 相对日期替换
"""

from datetime import date, datetime, timedelta
import re

from langchain_core.tools import tool
from loguru import logger
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.cache import tool_cache
from src.core.database import async_session_factory
from src.models.memo import Memo, classify_memo


def _clear_memo_cache(user_id: str) -> None:
    """清除指定用户的备忘录缓存（写操作后调用）"""
    prefix = f"list_memos:{user_id}"
    n = tool_cache.invalidate_by_prefix(prefix)
    if n:
        logger.debug(f"已清除 {n} 条 memo 缓存: user={user_id}")

_DATE_FORMAT = "%Y-%m-%d"


# ==================== 日期工具函数 ====================

def _normalize_date_terms(text: str) -> str:
    """替换文本中的相对日期为具体日期"""
    if not text:
        return text
    today = date.today()
    replacements = {
        "今天": today.strftime(_DATE_FORMAT),
        "昨天": (today - timedelta(days=1)).strftime(_DATE_FORMAT),
        "明天": (today + timedelta(days=1)).strftime(_DATE_FORMAT),
        "后天": (today + timedelta(days=2)).strftime(_DATE_FORMAT),
        "前天": (today - timedelta(days=2)).strftime(_DATE_FORMAT),
    }
    result = text
    for k, v in replacements.items():
        result = result.replace(k, v)
    return result


def _parse_date(date_str: str | None) -> date | None:
    """解析日期字符串"""
    if not date_str or not date_str.strip():
        return None
    try:
        # 尝试 yyyy-MM-dd
        return datetime.strptime(date_str.strip(), _DATE_FORMAT).date()
    except ValueError:
        pass
    # 尝试 "2026年7月2日"
    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", date_str.strip())
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


# ==================== 工具函数 ====================

@tool
async def add_memo(title: str, content: str, due_date: str | None, user_id: str) -> str:
    """创建新的备忘录。标题2-8字简洁概括。content中不要使用"今天""明天"等相对日期。

    Args:
        title: 备忘录标题
        content: 备忘录内容（详细描述）
        due_date: 到期日期（yyyy-MM-dd格式），无日期则不传
        user_id: 当前用户ID
    """
    if not title or not title.strip():
        return "备忘录标题不能为空"
    if not content or not content.strip():
        return "备忘录内容不能为空"

    content = _normalize_date_terms(content)
    category = classify_memo(title, content)
    parsed_date = _parse_date(due_date)

    async with async_session_factory() as session:
        memo = Memo(
            user_id=user_id,
            title=title.strip(),
            content=content,
            category=category,
            due_date=parsed_date,
        )
        session.add(memo)
        await session.commit()
        await session.refresh(memo)
        _clear_memo_cache(user_id)
        logger.info(f"备忘录创建成功: id={memo.id}, title={title}, user={user_id}")
        return f"备忘录创建成功（ID: {memo.id}）— 标题: {title}，分类: {category}" + (
            f"，到期: {parsed_date}" if parsed_date else ""
        )


@tool
async def list_memos(user_id: str, keyword: str | None = None, category: str | None = None, page: int = 1, limit: int = 10) -> str:
    """查询用户的备忘录列表，支持按关键词和分类过滤。

    Args:
        user_id: 当前用户ID
        keyword: 搜索关键词（搜索标题和内容），可选
        category: 分类过滤，可选
        page: 页码（默认1）
        limit: 每页数量（默认10）
    """
    async with async_session_factory() as session:
        conditions = [
            Memo.user_id == user_id,
            Memo.status != 0,
        ]
        if keyword and keyword.strip():
            kw = f"%{keyword.strip()}%"
            conditions.append((Memo.title.ilike(kw)) | (Memo.content.ilike(kw)))
        if category and category.strip():
            conditions.append(Memo.category == category.strip())

        total_query = select(func.count(Memo.id)).where(and_(*conditions))
        total = (await session.execute(total_query)).scalar() or 0

        offset = (max(1, page) - 1) * max(1, limit)
        query = select(Memo).where(and_(*conditions)).order_by(Memo.created_at.desc()).offset(offset).limit(limit)
        result = await session.execute(query)
        memos = result.scalars().all()

        if not memos:
            return "没有找到备忘录记录。"

        sb = f"找到 {total} 条备忘录（第{page}页）:\n"
        for i, m in enumerate(memos):
            due = m.due_date.strftime(_DATE_FORMAT) if m.due_date else "无"
            content = (m.content or "")[:500]
            sb += f"{i + 1}. ID:{m.id} [{m.category}] {m.title} | 到期:{due}"
            if content:
                sb += f" | {content}"
            sb += "\n"
        return sb.strip()


@tool
async def complete_memo(memo_id: int, user_id: str) -> str:
    """将指定备忘录标记为已完成。

    Args:
        memo_id: 备忘录ID
        user_id: 当前用户ID
    """
    async with async_session_factory() as session:
        result = await session.execute(select(Memo).where(Memo.id == memo_id, Memo.user_id == user_id))
        memo = result.scalar_one_or_none()
        if memo is None:
            return f"未找到ID为 {memo_id} 的备忘录"
        memo.status = 2
        await session.commit()
        _clear_memo_cache(user_id)
        return f"备忘录 [{memo.title}] 已标记为完成"


@tool
async def delete_memo(memo_id: int, user_id: str) -> str:
    """删除指定备忘录（软删除）。

    Args:
        memo_id: 备忘录ID
        user_id: 当前用户ID
    """
    async with async_session_factory() as session:
        result = await session.execute(select(Memo).where(Memo.id == memo_id, Memo.user_id == user_id))
        memo = result.scalar_one_or_none()
        if memo is None:
            return f"未找到ID为 {memo_id} 的备忘录"
        memo.status = 0
        await session.commit()
        _clear_memo_cache(user_id)
        return f"备忘录 [{memo.title}] 已删除"


@tool
async def update_memo(memo_id: int, title: str | None, content: str | None, due_date: str | None, user_id: str) -> str:
    """更新现有备忘录。memoId 须通过 list_memos 获取，禁止猜测或使用历史对话中的ID。

    Args:
        memo_id: 备忘录ID
        title: 新标题（可选）
        content: 新内容（可选）
        due_date: 到期日期（yyyy-MM-dd），可选
        user_id: 当前用户ID
    """
    if memo_id <= 0:
        return "无效的备忘录ID"
    if (not title or not title.strip()) and (not content or not content.strip()):
        return "至少需要提供标题或内容中的一个"

    async with async_session_factory() as session:
        result = await session.execute(select(Memo).where(Memo.id == memo_id, Memo.user_id == user_id))
        memo = result.scalar_one_or_none()
        if memo is None:
            return f"未找到ID为 {memo_id} 的备忘录，请先调用 list_memos 确认ID"

        if title and title.strip():
            memo.title = title.strip()
        if content and content.strip():
            memo.content = _normalize_date_terms(content)
            memo.category = classify_memo(memo.title, memo.content)
        if due_date:
            parsed = _parse_date(due_date)
            if parsed:
                memo.due_date = parsed

        await session.commit()
        _clear_memo_cache(user_id)
        return f"备忘录 [{memo.title}] 更新成功"


@tool
async def list_memos_by_date(user_id: str, start_date: str, end_date: str, keyword: str | None = None, limit: int = 10) -> str:
    """按到期日期范围查询备忘录。

    Args:
        user_id: 当前用户ID
        start_date: 开始日期（yyyy-MM-dd）
        end_date: 结束日期（yyyy-MM-dd）
        keyword: 可选关键词
        limit: 返回数量（默认10）
    """
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if not start or not end:
        return "日期格式错误，请使用 yyyy-MM-dd 格式"

    async with async_session_factory() as session:
        conditions = [
            Memo.user_id == user_id,
            Memo.status != 0,
            Memo.due_date >= start,
            Memo.due_date <= end,
        ]
        if keyword and keyword.strip():
            kw = f"%{keyword.strip()}%"
            conditions.append((Memo.title.ilike(kw)) | (Memo.content.ilike(kw)))

        query = select(Memo).where(and_(*conditions)).order_by(Memo.due_date.asc()).limit(limit)
        result = await session.execute(query)
        memos = result.scalars().all()

        if not memos:
            return f"在 {start_date} 至 {end_date} 范围内没有找到备忘录。"

        sb = f"在 {start_date} ~ {end_date} 范围内找到 {len(memos)} 条备忘录:\n"
        for i, m in enumerate(memos):
            due = m.due_date.strftime(_DATE_FORMAT) if m.due_date else "无"
            content = (m.content or "")[:500]
            sb += f"{i + 1}. ID:{m.id} [{m.category}] {m.title} | 到期:{due}"
            if content:
                sb += f" | 内容:{content}"
            sb += "\n"
        return sb.strip()
