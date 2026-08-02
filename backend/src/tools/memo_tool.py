"""备忘录工具 — @tool 封装

add / list / complete / delete / delete_batch / update + 自动分类 + 相对日期替换
"""

import json

from langchain_core.tools import tool
from loguru import logger
from sqlalchemy import and_, func, select

from src.core.cache import tool_cache
from src.core.database import async_session_factory
from src.core.date_utils import DATE_FORMAT, normalize_date_terms, parse_date
from src.models.memo import Memo
from src.services.memo_service import async_classify_memo


def _clear_memo_cache(user_id: str) -> None:
    """清除指定用户的备忘录缓存（写操作后调用）"""
    prefix = f"list_memos:{user_id}"
    n = tool_cache.invalidate_by_prefix(prefix)
    if n:
        logger.debug(f"已清除 {n} 条 memo 缓存: user={user_id}")


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

    content = normalize_date_terms(content)
    category = await async_classify_memo(title, content)
    parsed_date = parse_date(due_date)

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
async def list_memos(
    user_id: str,
    keyword: str | None = None,
    category: str | None = None,
    status: int | None = None,
    due_before: str | None = None,
    due_after: str | None = None,
    page: int = 1,
    limit: int = 10,
) -> str:
    """查询用户的备忘录列表，支持多条件组合过滤。

    - 支持关键词（标题+内容联动）、分类、完成状态
    - 支持到期日范围查询（due_before/due_after 可单独或组合使用）
    - 例如"过期的" → due_before=今天，"本周"→ due_after=今天, due_before=本周日

    Args:
        user_id: 当前用户ID
        keyword: 搜索关键词，可选
        category: 分类过滤，可选
        status: 1=活跃 / 2=已完成，可选（不传=全部）
        due_before: 到期在此日期之前（yyyy-MM-dd），可选
        due_after: 到期在此日期之后（yyyy-MM-dd），可选
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
        if status is not None:
            conditions.append(Memo.status == status)
        if due_before:
            d = parse_date(due_before)
            if d:
                conditions.append(Memo.due_date != None)  # noqa: E711
                conditions.append(Memo.due_date <= d)
        if due_after:
            d = parse_date(due_after)
            if d:
                conditions.append(Memo.due_date != None)  # noqa: E711
                conditions.append(Memo.due_date >= d)

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
            due = m.due_date.strftime(DATE_FORMAT) if m.due_date else "无"
            status_label = "✔" if m.status == 2 else "○"
            content = (m.content or "")[:500]
            sb += f"{i + 1}. ID:{m.id} [{m.category}] {m.title} | 到期:{due} | 状态:{status_label}"
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
            memo.content = normalize_date_terms(content)
            memo.category = await async_classify_memo(memo.title, memo.content)
        if due_date:
            parsed = parse_date(due_date)
            if parsed:
                memo.due_date = parsed

        await session.commit()
        _clear_memo_cache(user_id)
        return f"备忘录 [{memo.title}] 更新成功"


@tool
async def delete_memos_batch(
    memo_ids: str,
    user_id: str,
    confirmed: bool = False,
) -> str:
    """批量删除备忘录。必须先以 confirmed=False 预览，用户确认后再 confirmed=True 执行。

    - 第一次调用 confirmed=False：展示待删除列表，提示用户确认
    - 用户确认后第二次调用 confirmed=True：真正删除

    Args:
        memo_ids: 备忘录ID列表，JSON数组格式，如 "[1,2,3]"，最多20条
        user_id: 当前用户ID
        confirmed: 用户是否已确认删除，默认 False（仅预览）
    """
    try:
        ids = json.loads(memo_ids)
        if not isinstance(ids, list) or not ids:
            return "memo_ids 格式错误，请使用 JSON 数组如 [1,2,3]"
        ids = [int(i) for i in ids]
    except (json.JSONDecodeError, ValueError, TypeError):
        return "memo_ids 格式错误，请使用 JSON 数组如 [1,2,3]"

    if len(ids) > 20:
        return f"最多批量删除 20 条，当前传入了 {len(ids)} 条"

    async with async_session_factory() as session:
        result = await session.execute(
            select(Memo).where(Memo.id.in_(ids), Memo.user_id == user_id, Memo.status != 0)
        )
        memos = result.scalars().all()

        if not memos:
            return "指定的备忘录均不存在或不属于当前用户"

        titles = [f"{m.title}(ID:{m.id})" for m in memos]
        detail = "、".join(titles)
        skipped = len(ids) - len(memos)

        if not confirmed:
            # 预览模式：只展示，不删除
            msg = f"【预览】将删除以下 {len(memos)} 条备忘录：{detail}"
            if skipped > 0:
                msg += f"，{skipped} 条未找到或不属于您"
            msg += '\n请回复"确认"以执行删除，或回复"取消"放弃。'
            return msg

        # 确认模式：真正删除
        for m in memos:
            m.status = 0
        await session.commit()

        msg = f"成功删除 {len(memos)} 条备忘录：{detail}"
        if skipped > 0:
            msg += f"，{skipped} 条未找到或不属于您"
        _clear_memo_cache(user_id)
        return msg
