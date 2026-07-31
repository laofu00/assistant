"""记忆管理路由 — 短期记忆 + 长期记忆 + 用户画像

短期记忆（Redis）:
  GET    /memory/sessions           — 列出会话
  GET    /memory/sessions/{id}      — 会话详情
  DELETE /memory/sessions/{id}      — 清除会话

长期记忆（ChromaDB + PG）:
  GET    /memory/long-term          — 全部长期记忆
  DELETE /memory/long-term          — 删除单条事实

用户画像（PG）:
  GET    /memory/profile            — 获取画像
  PUT    /memory/profile            — 更新偏好
"""

from fastapi import APIRouter, Body, Depends, HTTPException

from src.core.auth_deps import get_current_user_id
from src.core.long_term_memory import long_term_memory
from src.core.memory import smart_memory
from src.core.schema import R

router = APIRouter(prefix="/memory", tags=["记忆管理"], dependencies=[Depends(get_current_user_id)])


# ==================== 短期记忆 ====================

@router.get("/sessions")
async def list_sessions(user_id: str = Depends(get_current_user_id)):
    sessions = await smart_memory.list_sessions(user_id)
    return R.ok(sessions)


@router.get("/sessions/{session_id}")
async def get_session_detail(session_id: str, user_id: str = Depends(get_current_user_id)):
    messages = await smart_memory.get_messages(user_id, session_id)
    facts = await smart_memory.get_summary_facts(user_id, session_id)
    if not messages and not facts:
        raise HTTPException(404, f"会话 [{session_id}] 不存在或已过期")
    return R.ok({
        "session_id": session_id, "messages": messages, "summary_facts": facts,
        "message_count": len(messages), "fact_count": len(facts),
    })


@router.delete("/sessions/{session_id}")
async def clear_session(session_id: str, user_id: str = Depends(get_current_user_id)):
    await smart_memory.clear(user_id, session_id)
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
    """获取用户全部长期记忆（画像 + 事实列表）"""
    data = await long_term_memory.list_all(user_id)
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
