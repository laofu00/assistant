"""工具管理路由

GET  /tools              — 工具列表（含健康状态、熔断、版本）
GET  /tools/{name}       — 工具详情
GET  /tools/stats        — 工具统计
PUT  /tools/{name}/enable   — 启用工具（管理员）
PUT  /tools/{name}/disable  — 禁用工具（管理员）
PUT  /tools/{name}/version  — 切换版本（管理员）
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.auth_deps import get_current_user_id, require_admin
from src.core.schema import R
from src.tools.health import get_all_health_status
from src.tools.tool_registry import tool_registry

router = APIRouter(prefix="/tools", tags=["工具管理"], dependencies=[Depends(get_current_user_id)])


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
        return R.ok(None, f"工具 [{name}] 已启用")
    raise HTTPException(404, f"工具 [{name}] 不存在")


@router.put("/{name}/disable", dependencies=[Depends(require_admin)])
async def disable_tool(name: str):
    """禁用工具"""
    if tool_registry.disable(name):
        return R.ok(None, f"工具 [{name}] 已禁用")
    raise HTTPException(404, f"工具 [{name}] 不存在")


@router.put("/{name}/version", dependencies=[Depends(require_admin)])
async def set_tool_version(name: str, version: int = Query(ge=1)):
    """切换工具版本（灰度切流）"""
    if tool_registry.set_version(name, version):
        return R.ok(None, f"工具 [{name}] 版本已切换为 v{version}")
    raise HTTPException(404, f"工具 [{name}] 不存在")
