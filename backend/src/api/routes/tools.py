"""工具管理路由

全局:
  GET  /tools              — 工具列表（含健康状态、熔断、版本）
  GET  /tools/{name}       — 工具详情
  GET  /tools/stats        — 工具统计
  PUT  /tools/{name}/enable   — 启用工具（管理员）
  PUT  /tools/{name}/disable  — 禁用工具（管理员）
  PUT  /tools/{name}/version  — 切换版本（管理员）

用户工具权限:
  GET    /tools/users/{user_id}/disabled   — 查询某用户被禁用的工具
  POST   /tools/users/{user_id}/disable    — 对某用户禁用工具
  DELETE /tools/users/{user_id}/enable     — 取消某用户的工具禁用
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, select

from loguru import logger

from src.core.auth_deps import get_current_user_id, require_admin
from src.core.database import async_session_factory
from src.core.schema import R
from src.models.tool_config import ToolConfig
from src.models.user_tool_blacklist import UserToolBlacklist
from src.tools.health import get_all_health_status
from src.tools.tool_registry import tool_registry

router = APIRouter(prefix="/tools", tags=["工具管理"], dependencies=[Depends(get_current_user_id)])


async def load_tool_config_from_db() -> None:
    """启动时从 DB 加载工具启用/禁用状态到内存"""
    try:
        async with async_session_factory() as session:
            result = await session.execute(select(ToolConfig))
            configs = result.scalars().all()
        for c in configs:
            if not c.enabled:
                tool_registry.disable(c.tool_name)
                logger.info(f"[工具配置] 加载禁用状态: {c.tool_name}")
        logger.info(f"[工具配置] 已从 DB 加载 {len(configs)} 条配置")
    except Exception as e:
        logger.warning(f"[工具配置] 加载失败（可能表尚未创建）: {e}")


async def _save_tool_config(tool_name: str, enabled: bool) -> None:
    """持久化工具启用/禁用状态"""
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(ToolConfig).where(ToolConfig.tool_name == tool_name)
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.enabled = enabled
            else:
                session.add(ToolConfig(tool_name=tool_name, enabled=enabled))
            await session.commit()
    except Exception as e:
        logger.warning(f"[工具配置] 持久化失败: {e}")


def _tool_to_dict(meta, breaker) -> dict:
    """ToolMeta → API 响应"""
    return {
        "name": meta.name,
        "description": meta.description,
        "permission": meta.permission.value,
        "category": meta.category,
        "enabled": meta.enabled,
        "version": meta.version,
        "dependency": meta.dependency,
        "parameter_count": meta.parameter_count,
        "circuit_breaker_open": breaker.is_open,
        "circuit_breaker_failures": breaker.failure_count,
    }


@router.get("")
async def list_tools():
    """获取所有工具列表及状态"""
    tools = tool_registry.list_all()
    result = [_tool_to_dict(t, tool_registry.get_breaker(t.name)) for t in tools]
    return R.ok(result)


@router.get("/stats")
async def get_tool_stats():
    """获取工具注册统计 + 依赖健康状态"""
    stats = tool_registry.get_stats()
    health = get_all_health_status()

    # 熔断器状态汇总
    breakers_open = sum(
        1 for t in tool_registry.list_all() if tool_registry.get_breaker(t.name).is_open
    )

    return R.ok({
        **stats,
        "health": health,
        "circuit_breakers_open": breakers_open,
    })


@router.get("/{name}")
async def get_tool(name: str):
    """获取单个工具详情"""
    meta = tool_registry.get(name)
    if meta is None:
        raise HTTPException(404, f"工具 [{name}] 不存在")
    return R.ok(_tool_to_dict(meta, tool_registry.get_breaker(name)))


@router.put("/{name}/enable", dependencies=[Depends(require_admin)])
async def enable_tool(name: str):
    """启用工具"""
    if tool_registry.enable(name):
        await _save_tool_config(name, True)
        return R.ok(None, f"工具 [{name}] 已启用")
    raise HTTPException(404, f"工具 [{name}] 不存在")


@router.put("/{name}/disable", dependencies=[Depends(require_admin)])
async def disable_tool(name: str):
    """禁用工具"""
    if tool_registry.disable(name):
        await _save_tool_config(name, False)
        return R.ok(None, f"工具 [{name}] 已禁用")
    raise HTTPException(404, f"工具 [{name}] 不存在")


@router.put("/{name}/version", dependencies=[Depends(require_admin)])
async def set_tool_version(name: str, version: int = Query(ge=1)):
    """切换工具版本（灰度切流）"""
    if tool_registry.set_version(name, version):
        return R.ok(None, f"工具 [{name}] 版本已切换为 v{version}")
    raise HTTPException(404, f"工具 [{name}] 不存在")


class UserToolDisableRequest(BaseModel):
    tool_name: str


class UserToolEnableRequest(BaseModel):
    tool_name: str


@router.get("/users/{user_id}/disabled", dependencies=[Depends(require_admin)])
async def get_user_disabled_tools(user_id: str):
    """查询某用户被禁用的工具列表"""
    async with async_session_factory() as session:
        stmt = select(UserToolBlacklist).where(UserToolBlacklist.user_id == user_id)
        result = await session.execute(stmt)
        records = result.scalars().all()
        return R.ok([r.tool_name for r in records])


@router.post("/users/{user_id}/disable", dependencies=[Depends(require_admin)])
async def disable_tool_for_user(user_id: str, body: UserToolDisableRequest):
    """对某用户禁用工具"""
    async with async_session_factory() as session:
        # 检查是否已存在
        existing = (await session.execute(
            select(UserToolBlacklist).where(
                UserToolBlacklist.user_id == user_id,
                UserToolBlacklist.tool_name == body.tool_name,
            )
        )).scalar_one_or_none()

        if existing:
            return R.ok(None, f"工具 [{body.tool_name}] 已对该用户禁用")

        record = UserToolBlacklist(user_id=user_id, tool_name=body.tool_name)
        session.add(record)
        await session.commit()
        return R.ok(None, f"工具 [{body.tool_name}] 已对用户 [{user_id}] 禁用")


@router.put("/{name}/permission", dependencies=[Depends(require_admin)])
async def set_tool_permission(name: str, permission: str = Query(default=...)):
    """修改工具权限级别"""
    valid = {"READ_ONLY", "READ_WRITE", "ADMIN"}
    if permission.upper() not in valid:
        raise HTTPException(400, f"无效权限级别: {permission}，支持: {valid}")
    from src.tools.tool_registry import ToolPermission
    if tool_registry.set_permission(name, ToolPermission(permission.upper())):
        return R.ok(None, f"工具 [{name}] 权限已更新为 {permission.upper()}")
    raise HTTPException(404, f"工具 [{name}] 不存在")


@router.post("/users/{user_id}/enable", dependencies=[Depends(require_admin)])
async def enable_tool_for_user(user_id: str, body: UserToolEnableRequest):
    """取消某用户的工具禁用"""
    async with async_session_factory() as session:
        stmt = delete(UserToolBlacklist).where(
            UserToolBlacklist.user_id == user_id,
            UserToolBlacklist.tool_name == body.tool_name,
        )
        result = await session.execute(stmt)
        await session.commit()
        if result.rowcount == 0:
            return R.ok(None, "该工具未被禁用，无需操作")
        return R.ok(None, f"工具 [{body.tool_name}] 已对用户 [{user_id}] 恢复启用")
