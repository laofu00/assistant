"""工具调用包装器 — 超时控制 + 缓存 + 审计 + 重复检测 + 熔断"""

import asyncio
import contextlib
from collections.abc import Callable
from typing import Any

from loguru import logger

from src.core.cache import tool_cache
from src.core.config import settings
from src.tools.tool_registry import ToolPermission, ToolRegistry, tool_registry


class ToolExecutor:
    """工具执行器 — 包装工具调用，注入企业级能力

    执行链：
    1. 检查熔断状态
    2. 检查工具是否被禁用
    3. 检查缓存命中（只读工具）
    4. asyncio.wait_for 超时控制
    5. 成功 → 写缓存 + 熔断计数归零
    6. 失败 → 降级缓存 + 熔断计数递增
    7. 审计日志（成功/失败均记录）
    """

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or tool_registry
        self._call_history: dict[str, list[str]] = {}  # session_id → [tool_name, ...]

    async def execute(
        self,
        tool_name: str,
        tool_func: Callable,
        args: dict[str, Any],
        user_id: str,
        session_id: str,
        trace_id: str,
    ) -> str:
        """执行工具调用"""
        meta = self.registry.get(tool_name)

        # 1. 熔断检查
        self.registry.check_breaker(tool_name)

        # 2. 禁用检查
        if meta and not meta.enabled:
            return f"[错误] 工具 [{tool_name}] 已被管理员禁用"

        # 3. 重复调用检测
        self._record_call(session_id, tool_name)
        if self._detect_duplicate(session_id, tool_name):
            msg = f"工具 [{tool_name}] 连续调用超过 {settings.AGENT_MAX_DUPLICATE_CALLS} 次，已终止"
            logger.warning(msg)
            raise RuntimeError(msg)

        # 4. 缓存检查（仅只读工具）
        cache_key = None
        if meta and meta.permission == ToolPermission.READ_ONLY:
            cache_key = tool_cache.make_key(tool_name, user_id, *args.values())
            cached = tool_cache.get(cache_key)
            if cached is not None:
                logger.debug(f"工具缓存命中: {tool_name}")
                return cached

        # 5. 超时控制
        is_write = meta and meta.permission == ToolPermission.READ_WRITE
        timeout = settings.TOOL_WRITE_TIMEOUT if is_write else settings.TOOL_TIMEOUT
        start = asyncio.get_event_loop().time()

        try:
            result = await asyncio.wait_for(self._invoke(tool_func, args), timeout=timeout)
            duration_ms = int((asyncio.get_event_loop().time() - start) * 1000)

            # 成功 → 写缓存
            if cache_key and result:
                tool_cache.put(cache_key, str(result))
            self.registry.record_success(tool_name)

            # 审计日志
            self._log_audit(trace_id, user_id, tool_name, str(args)[:200], str(result)[:200], duration_ms, True)

            return str(result)

        except TimeoutError:
            duration_ms = int((asyncio.get_event_loop().time() - start) * 1000)
            self.registry.record_failure(tool_name)
            self._log_audit(trace_id, user_id, tool_name, str(args)[:200], "", duration_ms, False, "超时")

            # 降级缓存
            if cache_key:
                fallback = tool_cache.get_fallback(cache_key)
                if fallback:
                    logger.info(f"工具 [{tool_name}] 超时，使用降级缓存")
                    return fallback
            return f"[错误] 工具 [{tool_name}] 操作超时（{timeout}秒），请稍后重试"

        except Exception as e:
            duration_ms = int((asyncio.get_event_loop().time() - start) * 1000)
            self.registry.record_failure(tool_name)
            self._log_audit(trace_id, user_id, tool_name, str(args)[:200], "", duration_ms, False, str(e))

            # 降级缓存
            if cache_key:
                fallback = tool_cache.get_fallback(cache_key)
                if fallback:
                    logger.info(f"工具 [{tool_name}] 异常，使用降级缓存: {e}")
                    return fallback
            return f"[错误] 工具 [{tool_name}] 操作异常: {e}"

    async def _invoke(self, func: Callable, args: dict[str, Any]) -> Any:
        """调用工具函数（支持同步和异步）"""
        if asyncio.iscoroutinefunction(func):
            return await func(**args)
        return func(**args)

    def _record_call(self, session_id: str, tool_name: str) -> None:
        # 限制最大 session 数，防止内存泄漏
        if len(self._call_history) >= 10_000:
            oldest = next(iter(self._call_history))
            del self._call_history[oldest]
        if session_id not in self._call_history:
            self._call_history[session_id] = []
        # 限制单个 session 的最大调用记录数
        if len(self._call_history[session_id]) >= 200:
            self._call_history[session_id] = self._call_history[session_id][-100:]
        self._call_history[session_id].append(tool_name)

    def _detect_duplicate(self, session_id: str, tool_name: str) -> bool:
        history = self._call_history.get(session_id, [])
        if len(history) < settings.AGENT_MAX_DUPLICATE_CALLS:
            return False
        return history[-settings.AGENT_MAX_DUPLICATE_CALLS:].count(tool_name) >= settings.AGENT_MAX_DUPLICATE_CALLS

    @staticmethod
    def _log_audit(
        trace_id: str,
        user_id: str,
        tool_name: str,
        tool_input: str,
        tool_output: str,
        duration_ms: int,
        success: bool,
        error: str = "",
    ) -> None:
        """记录审计日志（异步写入 DB，失败不影响主流程）"""
        status = "SUCCESS" if success else "FAILED"
        log_msg = (
            f"tool={tool_name} result={status} duration={duration_ms}ms "
            f"input={tool_input[:100]} output={tool_output[:100]}"
        )
        with contextlib.suppress(Exception):
            logger.bind(trace_id=trace_id, user_id=user_id).info(log_msg)
            # TODO: 第二阶段后续将异步写入 tool_audit_log 表


# 全局实例
tool_executor = ToolExecutor()
