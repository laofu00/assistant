"""认证路由 — POST /register, POST /login, GET /current, PUT /profile, POST /change-password, POST /refresh"""

import re

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import select

from loguru import logger

from src.core.config import settings
from src.core.database import async_session_factory
from src.core.jwt_utils import create_token, get_user_id_from_token
from src.core.password_utils import hash_password, verify_password
from src.core.redis_client import TOKEN_EXPIRE_SECONDS, TOKEN_PREFIX, get_redis
from src.core.schema import R
from src.models.user import User

router = APIRouter(prefix="/auth", tags=["认证"])

_PASSWORD_PATTERN = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).+$")
_EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9+_.-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_PHONE_PATTERN = re.compile(r"^1[3-9]\d{9}$")


# ==================== 请求模型 ====================

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str | None = None

    @field_validator("username")
    @classmethod
    def check_username(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) < 3 or len(v) > 20:
            raise ValueError("用户名长度 3-20 个字符")
        return v

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("密码长度不能少于 8 位")
        if not _PASSWORD_PATTERN.match(v):
            raise ValueError("密码需包含大写字母、小写字母和数字")
        return v


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class UpdateProfileRequest(BaseModel):
    nickname: str | None = None
    avatar: str | None = None
    phone: str | None = None
    email: str | None = None
    gender: int | None = None


# ==================== 端点 ====================


@router.post("/register")
async def register(body: RegisterRequest):
    """用户注册"""
    async with async_session_factory() as session:
        # 检查用户名唯一性
        existing = (await session.execute(
            select(User).where(User.username == body.username)
        )).scalar_one_or_none()
        if existing:
            raise HTTPException(400, "用户名已存在")

        # 生成用户ID
        import uuid
        user_id = f"u{uuid.uuid4().hex[:8]}"

        user = User(
            user_id=user_id,
            username=body.username,
            password=hash_password(body.password),
            nickname=body.username,
            email=body.email,
            status=1,
            roles="READ_WRITE",
            permissions="",
        )
        session.add(user)
        await session.commit()

        return R.ok({"user_id": user_id, "username": body.username}, "注册成功")


@router.post("/login")
async def login(body: LoginRequest):
    """用户登录"""
    async with async_session_factory() as session:
        user = (await session.execute(
            select(User).where(User.username == body.username, User.deleted == 0)
        )).scalar_one_or_none()

        if not user or not verify_password(body.password, user.password):
            return R.error(400, "用户名或密码错误")

        if user.status != 1:
            return R.error(403, "账号已被禁用")

        token = create_token(user.user_id, user.username, user.roles or "READ_WRITE")

        # 将 token 存入 Redis，有效期与 JWT 一致
        try:
            redis = await get_redis()
            redis_key = f"{TOKEN_PREFIX}{user.user_id}"
            await redis.set(redis_key, token, ex=TOKEN_EXPIRE_SECONDS)
            logger.info(f"Token 已写入 Redis: user_id={user.user_id}")
        except Exception as e:
            logger.warning(f"Redis 写入失败（不影响登录）: {e}")

        return R.ok({
            "token": token,
            "userId": user.user_id,
            "username": user.username,
            "nickname": user.nickname,
        })


@router.get("/current")
async def get_current_user(request: Request):
    """获取当前用户信息"""
    user_id = request.state.user_id

    async with async_session_factory() as session:
        user = (await session.execute(
            select(User).where(User.user_id == user_id, User.deleted == 0)
        )).scalar_one_or_none()

        if not user:
            raise HTTPException(404, "用户不存在")

        return R.ok({
            "userId": user.user_id,
            "username": user.username,
            "nickname": user.nickname,
            "avatar": user.avatar,
            "phone": user.phone,
            "email": user.email,
            "gender": user.gender,
            "status": user.status,
            "roles": user.roles,
        })


@router.put("/profile")
async def update_profile(body: UpdateProfileRequest, request: Request):
    """更新用户资料"""
    user_id = request.state.user_id

    async with async_session_factory() as session:
        user = (await session.execute(
            select(User).where(User.user_id == user_id, User.deleted == 0)
        )).scalar_one_or_none()

        if not user:
            raise HTTPException(404, "用户不存在")

        if body.nickname is not None:
            user.nickname = body.nickname
        if body.avatar is not None:
            user.avatar = body.avatar
        if body.phone is not None and body.phone.strip():
            if not _PHONE_PATTERN.match(body.phone):
                raise HTTPException(400, "手机号格式不正确")
            user.phone = body.phone
        elif body.phone is not None and not body.phone.strip():
            user.phone = None  # 空字符串视为清空
        if body.email is not None and body.email.strip():
            if not _EMAIL_PATTERN.match(body.email):
                raise HTTPException(400, "邮箱格式不正确")
            user.email = body.email
        elif body.email is not None and not body.email.strip():
            user.email = None
        if body.gender is not None:
            user.gender = body.gender

        await session.commit()
        return R.ok(None, "更新成功")


@router.post("/change-password")
async def change_password(body: ChangePasswordRequest, request: Request):
    """修改密码"""
    user_id = request.state.user_id

    async with async_session_factory() as session:
        user = (await session.execute(
            select(User).where(User.user_id == user_id, User.deleted == 0)
        )).scalar_one_or_none()

        if not user:
            raise HTTPException(404, "用户不存在")

        if not verify_password(body.old_password, user.password):
            raise HTTPException(400, "原密码错误")

        if len(body.new_password) < 8:
            raise HTTPException(400, "新密码长度不能少于 8 位")
        if not _PASSWORD_PATTERN.match(body.new_password):
            raise HTTPException(400, "新密码需包含大写字母、小写字母和数字")

        user.password = hash_password(body.new_password)
        await session.commit()

        # 清除 Redis 中的 token，强制重新登录
        try:
            redis = await get_redis()
            await redis.delete(f"{TOKEN_PREFIX}{user_id}")
        except Exception:
            pass

        return R.ok(None, "密码修改成功")


@router.post("/refresh")
async def refresh_token(request: Request):
    """刷新 token"""
    user_id = request.state.user_id

    async with async_session_factory() as session:
        user = (await session.execute(
            select(User).where(User.user_id == user_id, User.deleted == 0)
        )).scalar_one_or_none()

        if not user:
            raise HTTPException(404, "用户不存在")

        new_token = create_token(user.user_id, user.username, user.roles or "READ_WRITE")

        try:
            redis = await get_redis()
            redis_key = f"{TOKEN_PREFIX}{user.user_id}"
            await redis.set(redis_key, new_token, ex=TOKEN_EXPIRE_SECONDS)
        except Exception:
            pass

        return R.ok({"token": new_token, "userId": user.user_id, "username": user.username})

