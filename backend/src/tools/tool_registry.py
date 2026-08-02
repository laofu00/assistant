"""工具注册中心 — 元数据管理 + 权限分级 + 动态启停 + 熔断器

对齐 Java 版 ToolRegistry + RequirePermission + ToolPermission
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from loguru import logger

from src.core.config import settings
from src.core.exceptions import CircuitBreakerOpenError


class ToolPermission(StrEnum):
    READ_ONLY = "READ_ONLY"
    READ_WRITE = "READ_WRITE"
    ADMIN = "ADMIN"


@dataclass
class ToolMeta:
    name: str                        # e.g. "search_knowledge"
    description: str                  # 工具描述
    permission: ToolPermission        # 所需权限级别
    parameter_count: int              # 参数数量
    category: str                     # knowledge/memo/email/date/user
    enabled: bool = True
    version: int = 1                  # 工具版本号（灰度切流用）
    input_max_lengths: dict[str, int] = field(default_factory=dict)  # 参数名 → 最大长度
    output_max_length: int = 0        # 返回值截断长度（0=不截断）
    dependency: str = ""              # 依赖类型 chromadb/postgresql/smtp/空
    _func: Callable | None = field(default=None, repr=False)

    @property
    def func(self) -> Callable | None:
        return self._func


class CircuitBreaker:
    """简单熔断器：连续失败 N 次 → 打开 → 超时后半开"""

    def __init__(self) -> None:
        self.failure_count = 0
        self.last_failure_time: float | None = None
        self.is_open = False

    def record_success(self) -> None:
        self.failure_count = 0
        if self.is_open:
            logger.info("熔断器半开 → 关闭")
        self.is_open = False

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.failure_count >= settings.AGENT_CIRCUIT_BREAKER_THRESHOLD and not self.is_open:
            self.is_open = True
            logger.warning(f"熔断器打开: 连续 {self.failure_count} 次失败")

    def check(self) -> None:
        if not self.is_open:
            return
        if self.last_failure_time is None:
            return
        elapsed = time.monotonic() - self.last_failure_time
        if elapsed >= settings.AGENT_CIRCUIT_BREAKER_TIMEOUT:
            self.is_open = False
            self.failure_count = 0
            logger.info("熔断器超时 → 半开，允许尝试")
            return
        raise CircuitBreakerOpenError(
            f"熔断器已打开，请 {settings.AGENT_CIRCUIT_BREAKER_TIMEOUT - int(elapsed)} 秒后重试"
        )


class ToolRegistry:
    """工具注册中心"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolMeta] = {}
        self._breakers: dict[str, CircuitBreaker] = {}

    # ==================== 注册 ====================

    def register(
        self,
        func: Callable,
        name: str,
        description: str,
        permission: ToolPermission = ToolPermission.READ_ONLY,
        category: str = "other",
        parameter_count: int = 0,
        version: int = 1,
        input_max_lengths: dict[str, int] | None = None,
        output_max_length: int = 0,
        dependency: str = "",
    ) -> None:
        meta = ToolMeta(
            name=name,
            description=description,
            permission=permission,
            parameter_count=parameter_count,
            category=category,
            version=version,
            input_max_lengths=input_max_lengths or {},
            output_max_length=output_max_length,
            dependency=dependency,
            _func=func,
        )
        self._tools[name] = meta
        self._breakers[name] = CircuitBreaker()
        logger.debug(f"工具注册: {name} [{permission.value}] {category}")

    def register_tool(self, tool_func: Callable, permission: ToolPermission = ToolPermission.READ_ONLY) -> None:
        """从 langchain @tool 装饰的函数自动注册"""
        from src.core.config import settings

        name = getattr(tool_func, "name", None) or getattr(tool_func, "__name__", "unknown")
        desc = getattr(tool_func, "description", "") or ""
        params = getattr(tool_func, "args_schema", None)

        # 推断分类
        category = "other"
        if "knowledge" in name or "document" in name:
            category = "knowledge"
        elif "memo" in name:
            category = "memo"
        elif "email" in name or "mail" in name:
            category = "email"
        elif "date" in name or "time" in name:
            category = "date"
        elif "user" in name:
            category = "user"

        # 推断依赖
        dependency = ""
        if category == "knowledge":
            dependency = "chromadb"
        elif category == "memo" or category == "user":
            dependency = "postgresql"
        elif category == "email":
            dependency = "smtp"

        # 推断输入长度限制
        input_max_lengths: dict[str, int] = {}
        if params and hasattr(params, "model_fields"):
            default_limit = settings.TOOL_INPUT_MAX_LENGTHS.get("_default", 5000)
            for field_name in params.model_fields:
                key = f"{name}.{field_name}"
                limit = settings.TOOL_INPUT_MAX_LENGTHS.get(key, default_limit)
                input_max_lengths[field_name] = limit

        # 推断输出长度限制
        output_max_length = settings.TOOL_OUTPUT_MAX_LENGTHS.get(
            name, settings.TOOL_OUTPUT_MAX_LENGTHS.get("_default", 4000)
        )

        param_count = len(params.model_fields) if params and hasattr(params, "model_fields") else 0
        self.register(
            tool_func, name, desc, permission, category, param_count,
            input_max_lengths=input_max_lengths,
            output_max_length=output_max_length,
            dependency=dependency,
        )

    # ==================== 查询 ====================

    def get(self, name: str) -> ToolMeta | None:
        return self._tools.get(name)

    def list_all(self) -> list[ToolMeta]:
        return list(self._tools.values())

    def list_enabled(self) -> list[ToolMeta]:
        return [m for m in self._tools.values() if m.enabled]

    def list_by_permission(self, permission: ToolPermission) -> list[ToolMeta]:
        return [m for m in self._tools.values() if m.permission.value <= permission.value]

    def get_enabled_funcs(self) -> list[Callable]:
        return [m.func for m in self._tools.values() if m.enabled and m.func is not None]

    # ==================== 启用/禁用 ====================

    def enable(self, name: str) -> bool:
        meta = self._tools.get(name)
        if meta is None:
            return False
        meta.enabled = True
        logger.info(f"工具已启用: {name}")
        return True

    def disable(self, name: str) -> bool:
        meta = self._tools.get(name)
        if meta is None:
            return False
        meta.enabled = False
        logger.warning(f"工具已禁用: {name}")
        return True

    def is_enabled(self, name: str) -> bool:
        meta = self._tools.get(name)
        return meta is not None and meta.enabled

    # ==================== 熔断 ====================

    def get_breaker(self, name: str) -> CircuitBreaker:
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker()
        return self._breakers[name]

    def record_success(self, name: str) -> None:
        self.get_breaker(name).record_success()

    def record_failure(self, name: str) -> None:
        self.get_breaker(name).record_failure()

    def check_breaker(self, name: str) -> None:
        self.get_breaker(name).check()

    # ==================== 权限修改 ====================

    def set_permission(self, name: str, permission: ToolPermission) -> bool:
        meta = self._tools.get(name)
        if meta is None:
            return False
        old = meta.permission
        meta.permission = permission
        logger.info(f"工具 [{name}] 权限变更: {old.value} → {permission.value}")
        return True

    # ==================== 版本管理 ====================

    def set_version(self, name: str, version: int) -> bool:
        """切换工具版本（灰度切流用）"""
        meta = self._tools.get(name)
        if meta is None:
            return False
        meta.version = version
        logger.info(f"工具 [{name}] 版本切换: v{version}")
        return True

    def get_version(self, name: str) -> int | None:
        meta = self._tools.get(name)
        return meta.version if meta else None

    # ==================== 统计 ====================

    def get_stats(self) -> dict:
        """获取工具注册统计信息"""
        all_tools = self.list_all()
        enabled = [t for t in all_tools if t.enabled]
        disabled = [t for t in all_tools if not t.enabled]

        categories: dict[str, int] = {}
        for t in all_tools:
            categories[t.category] = categories.get(t.category, 0) + 1

        return {
            "total": len(all_tools),
            "enabled": len(enabled),
            "disabled": len(disabled),
            "categories": categories,
            "tools": [
                {
                    "name": t.name,
                    "category": t.category,
                    "permission": t.permission.value,
                    "enabled": t.enabled,
                    "version": t.version,
                    "dependency": t.dependency,
                }
                for t in all_tools
            ],
        }


# 全局实例
tool_registry = ToolRegistry()
