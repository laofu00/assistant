"""备忘录 REST API — CRUD 端点（面向前端）"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import and_, func, select

from src.core.auth_deps import is_admin_user
from src.core.database import async_session_factory
from src.core.schema import R
from src.models.memo import Memo
from src.services.memo_service import async_classify_memo

router = APIRouter(prefix="/memo", tags=["备忘录"])


def _get_user_id(request: Request) -> str:
    """从请求上下文获取已认证的用户ID（中间件已保证非 anonymous）"""
    return request.state.user_id


def _fmt_time(dt: datetime | None) -> str | None:
    """格式化时间字符串（PostgreSQL 已设为 Asia/Shanghai，无时区差）"""
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%d %H:%M:%S")


class MemoCreate(BaseModel):
    title: str
    content: str
    due_date: str | None = None
    category: str | None = None  # 用户手动指定分类，不传则 AI 自动分类


class MemoUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    due_date: str | None = None
    status: int | None = None
    category: str | None = None  # 用户手动指定分类，不传则仅在内容变化时 AI 重新分类


@router.post("")
async def create_memo(body: MemoCreate, request: Request):
    """创建备忘录"""
    from src.core.date_utils import normalize_date_terms, parse_date

    user_id = _get_user_id(request)

    content = normalize_date_terms(body.content) if body.content else ""
    # 用户手动指定分类优先，否则 AI 自动分类
    if body.category and body.category.strip():
        category = body.category.strip()
    else:
        category = await async_classify_memo(body.title, content)
    parsed_date = parse_date(body.due_date) if body.due_date else None

    async with async_session_factory() as session:
        memo = Memo(
            user_id=user_id,
            title=body.title,
            content=content,
            category=category,
            due_date=parsed_date,
        )
        session.add(memo)
        await session.commit()
        await session.refresh(memo)
        return R.ok({"id": memo.id, "title": memo.title, "category": memo.category})


@router.put("/{memo_id}")
async def update_memo(memo_id: int, body: MemoUpdate):
    """更新备忘录"""
    from src.core.date_utils import normalize_date_terms, parse_date

    async with async_session_factory() as session:
        result = await session.execute(select(Memo).where(Memo.id == memo_id))
        memo = result.scalar_one_or_none()
        if memo is None:
            raise HTTPException(404, "备忘录不存在")

        if body.title is not None:
            memo.title = body.title
        if body.content is not None:
            memo.content = normalize_date_terms(body.content)
        if body.due_date is not None:
            memo.due_date = parse_date(body.due_date)
        if body.status is not None:
            memo.status = body.status
        if body.category is not None and body.category.strip():
            memo.category = body.category.strip()

        # 用户未手动指定分类，且标题或内容有变化时，AI 重新分类
        has_category = body.category is not None and body.category.strip()
        if not has_category and (body.title is not None or body.content is not None):
            memo.category = await async_classify_memo(memo.title, memo.content or "")

        await session.commit()
        return R.ok(None, "更新成功")


@router.delete("/{memo_id}")
async def delete_memo(memo_id: int):
    """软删除备忘录"""
    async with async_session_factory() as session:
        result = await session.execute(select(Memo).where(Memo.id == memo_id))
        memo = result.scalar_one_or_none()
        if memo is None:
            raise HTTPException(404, "备忘录不存在")
        memo.status = 0
        await session.commit()
        return R.ok(None, "删除成功")


@router.get("/list")
async def list_memos(
    request: Request,
    category: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
):
    """查询备忘录列表 — 管理员查看全部用户"""
    user_id = _get_user_id(request)
    is_admin = await is_admin_user(user_id)
    async with async_session_factory() as session:
        conditions = [Memo.status != 0]
        if not is_admin:
            conditions.insert(0, Memo.user_id == user_id)
        if category:
            conditions.append(Memo.category == category)
        if keyword:
            kw = f"%{keyword}%"
            conditions.append((Memo.title.ilike(kw)) | (Memo.content.ilike(kw)))

        total_q = select(func.count(Memo.id)).where(and_(*conditions))
        total = (await session.execute(total_q)).scalar() or 0

        offset = (page - 1) * size
        q = select(Memo).where(and_(*conditions)).order_by(Memo.created_at.desc()).offset(offset).limit(size)
        result = await session.execute(q)
        memos = result.scalars().all()

        records = [
            {
                "id": m.id,
                "title": m.title,
                "content": m.content,
                "category": m.category,
                "status": m.status,
                "due_date": str(m.due_date) if m.due_date else None,
                "createTime": _fmt_time(m.created_at),
            }
            for m in memos
        ]
        return R.ok({"records": records, "total": total, "page": page, "size": size})


@router.get("/search")
async def search_memos(
    request: Request,
    keyword: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
):
    """关键词搜索备忘录"""
    return await list_memos(request=request, keyword=keyword, page=page, size=size)
