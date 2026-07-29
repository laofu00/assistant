"""工具管理路由 — GET /tools, GET /tools/{name}, PUT /tools/{name}/enable, PUT /tools/{name}/disable"""

from fastapi import APIRouter, Depends, HTTPException

from src.core.auth_deps import get_current_user_id, require_admin
from src.core.schema import R
from src.tools.tool_registry import tool_registry

router = APIRouter(prefix="/tools", tags=["工具管理"], dependencies=[Depends(get_current_user_id)])


@router.get("")
async def list_tools():
    """获取所有工具列表及状态"""
    tools = tool_registry.list_all()
    result = [
        {
            "name": t.name,
            "description": t.description,
            "permission": t.permission.value,
            "category": t.category,
            "enabled": t.enabled,
        }
        for t in tools
    ]
    return R.ok(result)


@router.get("/{name}")
async def get_tool(name: str):
    """获取单个工具详情"""
    meta = tool_registry.get(name)
    if meta is None:
        raise HTTPException(404, f"工具 [{name}] 不存在")
    return R.ok({
        "name": meta.name,
        "description": meta.description,
        "permission": meta.permission.value,
        "category": meta.category,
        "enabled": meta.enabled,
    })


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
