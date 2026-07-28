"""用户路由 — 偏好设置 CRUD"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from src.core.database import async_session_factory
from src.core.schema import R
from src.models.user_preference import UserPreference

router = APIRouter(prefix="/user", tags=["用户"])


class PreferenceRequest(BaseModel):
    language: str | None = "zh-CN"
    theme: str | None = "light"
    timezone: str | None = "Asia/Shanghai"
    notification_settings: str | None = None
    privacy_settings: str | None = None
    device_preferences: str | None = None


@router.get("/preferences")
async def get_preferences(request: Request):
    """获取用户偏好"""
    user_id = request.state.user_id

    async with async_session_factory() as session:
        pref = (await session.execute(
            select(UserPreference).where(
                UserPreference.user_id == user_id,
                UserPreference.deleted == 0,
            )
        )).scalar_one_or_none()

        if not pref:
            return R.ok({
                "user_id": user_id,
                "language": "zh-CN",
                "theme": "light",
                "timezone": "Asia/Shanghai",
            })

        return R.ok({
            "user_id": pref.user_id,
            "language": pref.language,
            "theme": pref.theme,
            "timezone": pref.timezone,
            "notification_settings": pref.notification_settings,
            "privacy_settings": pref.privacy_settings,
            "device_preferences": pref.device_preferences,
        })


@router.post("/preferences")
async def save_preferences(body: PreferenceRequest, request: Request):
    """保存用户偏好"""
    user_id = request.state.user_id

    async with async_session_factory() as session:
        existing = (await session.execute(
            select(UserPreference).where(UserPreference.user_id == user_id)
        )).scalar_one_or_none()

        if existing:
            existing.language = body.language
            existing.theme = body.theme
            existing.timezone = body.timezone
            existing.notification_settings = body.notification_settings
            existing.privacy_settings = body.privacy_settings
            existing.device_preferences = body.device_preferences
        else:
            pref = UserPreference(
                user_id=user_id,
                language=body.language,
                theme=body.theme,
                timezone=body.timezone,
                notification_settings=body.notification_settings,
                privacy_settings=body.privacy_settings,
                device_preferences=body.device_preferences,
            )
            session.add(pref)

        await session.commit()
        return R.ok(None, "保存成功")


@router.put("/preferences")
async def update_preferences(body: PreferenceRequest, request: Request):
    """更新用户偏好"""
    user_id = request.state.user_id

    async with async_session_factory() as session:
        existing = (await session.execute(
            select(UserPreference).where(UserPreference.user_id == user_id)
        )).scalar_one_or_none()

        if not existing:
            raise HTTPException(404, "用户偏好不存在")

        if body.language is not None:
            existing.language = body.language
        if body.theme is not None:
            existing.theme = body.theme
        if body.timezone is not None:
            existing.timezone = body.timezone
        if body.notification_settings is not None:
            existing.notification_settings = body.notification_settings
        if body.privacy_settings is not None:
            existing.privacy_settings = body.privacy_settings
        if body.device_preferences is not None:
            existing.device_preferences = body.device_preferences

        await session.commit()
        return R.ok(None, "更新成功")
