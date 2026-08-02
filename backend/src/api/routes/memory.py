"""记忆管理路由 — 短期记忆 + 长期记忆 + 用户画像

管理员视角：查看全部用户数据
普通用户视角：仅查看自己数据
"""

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from src.core.auth_deps import get_current_user_id, is_admin_user
from src.core.long_term_memory import long_term_memory
from src.core.memory import smart_memory
from src.core.schema import R

router = APIRouter(prefix="/memory", tags=["记忆管理"], dependencies=[Depends(get_current_user_id)])


async def _resolve_memory_user_id(user_id: str) -> str | None:
    """管理员 → None（查全部）；普通用户 → 仅自己"""
    if await is_admin_user(user_id):
        return None
    return user_id


# ==================== 短期记忆 ====================

@router.get("/sessions")
async def list_sessions(user_id: str = Depends(get_current_user_id)):
    if await is_admin_user(user_id):
        sessions = await smart_memory.list_all_user_sessions()
    else:
        sessions = await smart_memory.list_sessions(user_id)
    return R.ok(sessions)


@router.get("/sessions/{session_id}")
async def get_session_detail(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
    owner_user_id: str | None = Query(default=None),
):
    """获取会话详情 — 管理员可传 owner_user_id 查看其他用户会话"""
    lookup_id = owner_user_id if owner_user_id and await is_admin_user(user_id) else user_id
    messages = await smart_memory.get_messages(lookup_id, session_id)
    facts = await smart_memory.get_summary_facts(lookup_id, session_id)
    if not messages and not facts:
        raise HTTPException(404, f"会话 [{session_id}] 不存在或已过期")
    return R.ok({
        "session_id": session_id, "messages": messages, "summary_facts": facts,
        "message_count": len(messages), "fact_count": len(facts),
    })


@router.delete("/sessions/{session_id}")
async def clear_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
    owner_user_id: str | None = Query(default=None),
):
    """清除会话 — 管理员可传 owner_user_id 清除其他用户会话"""
    lookup_id = owner_user_id if owner_user_id and await is_admin_user(user_id) else user_id
    await smart_memory.clear(lookup_id, session_id)
    return R.ok(None, f"会话 [{session_id}] 记忆已清除")


@router.put("/sessions/{session_id}/title")
async def set_session_title(
    session_id: str,
    title: str = Body(..., embed=True),  # noqa: B008
    user_id: str = Depends(get_current_user_id),
):
    """重命名会话"""
    await smart_memory.set_session_title(user_id, session_id, title)
    return R.ok(None, "会话已重命名")


# ==================== 长期记忆 ====================

@router.get("/long-term")
async def get_long_term(user_id: str = Depends(get_current_user_id)):
    """获取长期记忆 — 管理员查看全部用户"""
    data = await long_term_memory.list_all(await _resolve_memory_user_id(user_id))
    return R.ok(data)


@router.delete("/long-term")
async def delete_fact(fact_text: str = Body(..., embed=True), user_id: str = Depends(get_current_user_id)):
    """删除单条长期记忆事实"""
    ok = await long_term_memory.delete_fact(user_id, fact_text)
    if ok:
        return R.ok(None, "已删除")
    raise HTTPException(404, "未找到该事实")


# ==================== 用户画像 ====================

@router.get("/profile")
async def get_profile(user_id: str = Depends(get_current_user_id)):
    """获取用户画像"""
    data = await long_term_memory.list_all(user_id)
    return R.ok(data.get("profile", {}))


@router.put("/profile")
async def update_profile(
    preferences: dict = Body(...),  # noqa: B008
    user_id: str = Depends(get_current_user_id),
):
    """更新用户偏好"""
    await long_term_memory.update_preferences(user_id, preferences)
    return R.ok(None, "偏好已更新")
