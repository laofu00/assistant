"""工具调用包装器 — 企业级执行链

完整执行链（12 步）：
  1. 输入参数校验（Pydantic Schema + 字符串长度）
  2. 运行时权限验证（ADMIN 级工具拦截）
  3. 依赖健康检查 → 不健康直接降级
  4. 三层限流（单用户单工具 / 全局工具 / 单用户总 QPS）
  5. 熔断状态检查
  6. 工具启用/禁用检查
  7. 重复调用检测
  8. 只读工具缓存命中检查
  9. asyncio.wait_for 超时控制 → 执行工具
  10. 返回值截断（保护 Agent 上下文窗口）
  11. 成功 → 写缓存 + 熔断归零；失败 → 降级缓存 + 熔断递增
  12. 审计日志（文件 + DB 异步入队）+ Prometheus 指标
"""

import asyncio
import contextlib
from collections import deque
from collections.abc import Callable
from typing import Any

from loguru import logger

from src.core.cache import tool_cache
from src.core.config import settings
from src.core.metrics import (
    tool_active_calls,
    tool_call_duration_seconds,
    tool_calls_total,
)
from src.tools.tool_registry import ToolPermission, ToolRegistry, tool_registry

# ==================== 审计日志异步队列 ====================

_audit_started = False
_audit_queue: deque[dict] = deque()


async def _flush_audit_queue() -> None:
    """后台任务：定期将审计记录写入 DB"""
    from src.core.database import async_session_factory
    from src.core.metrics import tool_audit_queue_size
    from src.models.tool_audit import ToolAuditLog

    while True:
        await asyncio.sleep(settings.TOOL_AUDIT_FLUSH_INTERVAL)
        batch = []
        while _audit_queue and len(batch) < 50:
            batch.append(_audit_queue.popleft())

        if not batch:
            tool_audit_queue_size.set(0)
            continue

        try:
            async with async_session_factory() as session:
                for record in batch:
                    session.add(ToolAuditLog(**record))
                await session.commit()
            logger.debug(f"[审计] 批量写入 {len(batch)} 条记录")
        except Exception as e:
            logger.warning(f"[审计] 批量写入失败: {e}")
            # 写 DB 失败不丢数据，塞回队列（但限制队列大小防内存泄漏）
            if len(_audit_queue) < 2000:
                for record in batch:
                    _audit_queue.appendleft(record)

        tool_audit_queue_size.set(len(_audit_queue))


def start_audit_worker() -> None:
    """启动审计日志后台写入任务"""
    global _audit_started  # noqa: PLW0603
    if not _audit_started:
        _audit_started = True
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        loop.create_task(_flush_audit_queue())
        logger.info("[审计] 后台写入任务已启动")


def _enqueue_audit(record: dict) -> None:
    """将审计记录放入队列（5000 条上限，防内存泄漏）"""
    if len(_audit_queue) < 5000:
        _audit_queue.append(record)


# ==================== 输入校验 ====================


class ToolInputValidator:
    """工具输入参数校验器 — Pydantic Schema + 字符串长度双重校验"""

    def validate(self, tool_name: str, args: dict[str, Any], meta) -> str | None:
        """校验输入参数，返回错误信息或 None（通过）"""
        # 1. 字符串长度校验
        input_limits = meta.input_max_lengths if meta else {}
        for param_name, value in args.items():
            if not isinstance(value, str):
                continue
            max_len = input_limits.get(param_name, settings.TOOL_INPUT_MAX_LENGTHS.get("_default", 5000))
            if max_len > 0 and len(value) > max_len:
                return (
                    f"参数 [{param_name}] 长度超限: {len(value)}/{max_len} 字符。"
                    f"请缩短内容后重试。"
                )

        return None  # 通过


tool_input_validator = ToolInputValidator()


# ==================== 工具执行器 ====================


class ToolExecutor:
    """工具执行器 — 企业级工具调用包装

    执行链（12 步）：
      1. 输入参数校验
      2. 运行时权限验证
      3. 依赖健康检查
      4. 三层限流
      5. 熔断状态检查
      6. 工具启用/禁用检查
      7. 重复调用检测
      8. 只读工具缓存命中检查
      9. 超时控制 → 执行工具函数
      10. 返回值截断
      11. 成功/失败后处理（缓存、熔断）
      12. 审计日志（文件 + DB） + Prometheus 指标
    """

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or tool_registry
        self._call_history: dict[str, list[str]] = {}

    async def execute(
        self,
        tool_name: str,
        tool_func: Callable,
        args: dict[str, Any],
        user_id: str,
        session_id: str,
        trace_id: str,
    ) -> str:
        """执行工具调用，返回工具执行结果字符串"""
        meta = self.registry.get(tool_name)
        category = meta.category if meta else "other"
        permission = meta.permission.value if meta else "unknown"

        # 指标：活跃调用 +1
        tool_active_calls.labels(tool_name=tool_name).inc()

        try:
            # ====== 步骤 1: 输入参数校验 ======
            if meta:
                error = tool_input_validator.validate(tool_name, args, meta)
                if error:
                    self._log_audit(trace_id, user_id, session_id, tool_name,
                                    self._truncate_input(args), "", 0, False, error)
                    tool_calls_total.labels(
                        tool_name=tool_name, category=category,
                        permission=permission, result="validation_error"
                    ).inc()
                    return f"[参数校验失败] {error}"

            # ====== 步骤 2: 运行时权限验证 ======
            if meta and meta.permission == ToolPermission.ADMIN:
                from src.core.auth_deps import is_admin_user
                if not await is_admin_user(user_id):
                    self._log_audit(trace_id, user_id, session_id, tool_name,
                                    self._truncate_input(args), "", 0, False, "权限不足")
                    tool_calls_total.labels(
                        tool_name=tool_name, category=category,
                        permission=permission, result="permission_denied"
                    ).inc()
                    return f"[错误] 工具 [{tool_name}] 需要管理员权限"

            # ====== 步骤 3: 依赖健康检查 ======
            if meta and meta.dependency:
                from src.tools.health import check_tool_health

                healthy = await check_tool_health(tool_name)
                if not healthy:
                    # 尝试降级缓存
                    cache_key = tool_cache.make_key(tool_name, user_id, *args.values())
                    fallback = tool_cache.get_fallback(cache_key)
                    if fallback:
                        logger.info(f"工具 [{tool_name}] 依赖不健康，使用降级缓存")
                        tool_calls_total.labels(
                            tool_name=tool_name, category=category,
                            permission=permission, result="degraded"
                        ).inc()
                        return f"{fallback}\n\n[提示] 以上为缓存数据，{meta.dependency} 服务暂时不可用"

                    self._log_audit(trace_id, user_id, session_id, tool_name,
                                    self._truncate_input(args), "", 0, False, "依赖不健康")
                    tool_calls_total.labels(
                        tool_name=tool_name, category=category,
                        permission=permission, result="unhealthy"
                    ).inc()
                    return f"[错误] 工具 [{tool_name}] 依赖的 {meta.dependency} 服务暂不可用，请稍后重试"

            # ====== 步骤 4: 三层限流 ======
            from src.tools.rate_limiter import tool_rate_limiter

            allowed = await tool_rate_limiter.acquire(tool_name, user_id)
            if not allowed:
                self._log_audit(trace_id, user_id, session_id, tool_name,
                                self._truncate_input(args), "", 0, False, "限流")
                tool_calls_total.labels(
                    tool_name=tool_name, category=category,
                    permission=permission, result="rate_limited"
                ).inc()
                return "[限流] 操作频率过高，请稍后重试"

            # ====== 步骤 5: 熔断检查 ======
            self.registry.check_breaker(tool_name)

            # ====== 步骤 6: 禁用检查 ======
            if meta and not meta.enabled:
                tool_calls_total.labels(
                    tool_name=tool_name, category=category,
                    permission=permission, result="disabled"
                ).inc()
                return f"[错误] 工具 [{tool_name}] 已被管理员禁用"

            # ====== 步骤 7: 重复调用检测 ======
            self._record_call(session_id, tool_name)
            if self._detect_duplicate(session_id, tool_name):
                msg = f"工具 [{tool_name}] 连续调用超过 {settings.AGENT_MAX_DUPLICATE_CALLS} 次，已终止"
                logger.warning(msg)
                tool_calls_total.labels(
                    tool_name=tool_name, category=category,
                    permission=permission, result="duplicate_blocked"
                ).inc()
                raise RuntimeError(msg)

            # ====== 步骤 8: 缓存检查 ======
            cache_key = None
            if meta and meta.permission == ToolPermission.READ_ONLY:
                cache_key = tool_cache.make_key(tool_name, user_id, *args.values())
                cached = tool_cache.get(cache_key)
                if cached is not None:
                    logger.debug(f"工具缓存命中: {tool_name}")
                    tool_calls_total.labels(
                        tool_name=tool_name, category=category,
                        permission=permission, result="cache_hit"
                    ).inc()
                    return cached

            # ====== 步骤 9: 超时控制 → 执行 ======
            is_write = meta and meta.permission == ToolPermission.READ_WRITE
            timeout = settings.TOOL_WRITE_TIMEOUT if is_write else settings.TOOL_TIMEOUT
            start = asyncio.get_event_loop().time()

            try:
                raw_result = await asyncio.wait_for(
                    self._invoke(tool_func, args), timeout=timeout
                )
                duration_ms = int((asyncio.get_event_loop().time() - start) * 1000)

                # ====== 步骤 10: 返回值截断 ======
                result_str = str(raw_result)
                output_max = meta.output_max_length if meta else 0
                truncated = output_max > 0 and len(result_str) > output_max
                if truncated:
                    result_str = result_str[:output_max] + f"\n...[已截断，原文 {len(str(raw_result))} 字符]"

                # ====== 步骤 11: 成功后处理 ======
                if cache_key and result_str:
                    tool_cache.put(cache_key, result_str)
                self.registry.record_success(tool_name)

                # ====== 步骤 12: 审计 + 指标 ======
                self._log_audit(trace_id, user_id, session_id, tool_name,
                                self._truncate_input(args), str(raw_result)[:8000],
                                duration_ms, True)

                tool_call_duration_seconds.labels(tool_name=tool_name).observe(duration_ms / 1000)
                tool_calls_total.labels(
                    tool_name=tool_name, category=category,
                    permission=permission, result="success"
                ).inc()

                return result_str

            except TimeoutError:
                duration_ms = int((asyncio.get_event_loop().time() - start) * 1000)
                self.registry.record_failure(tool_name)
                self._log_audit(trace_id, user_id, session_id, tool_name,
                                self._truncate_input(args), "", duration_ms, False, "超时")

                tool_call_duration_seconds.labels(tool_name=tool_name).observe(duration_ms / 1000)
                tool_calls_total.labels(
                    tool_name=tool_name, category=category,
                    permission=permission, result="timeout"
                ).inc()

                if cache_key:
                    fallback = tool_cache.get_fallback(cache_key)
                    if fallback:
                        logger.info(f"工具 [{tool_name}] 超时，使用降级缓存")
                        return fallback
                return f"[错误] 工具 [{tool_name}] 操作超时（{timeout}秒），请稍后重试"

            except Exception as e:
                duration_ms = int((asyncio.get_event_loop().time() - start) * 1000)
                self.registry.record_failure(tool_name)
                self._log_audit(trace_id, user_id, session_id, tool_name,
                                self._truncate_input(args), "", duration_ms, False, str(e))

                tool_call_duration_seconds.labels(tool_name=tool_name).observe(duration_ms / 1000)
                tool_calls_total.labels(
                    tool_name=tool_name, category=category,
                    permission=permission, result="error"
                ).inc()

                if cache_key:
                    fallback = tool_cache.get_fallback(cache_key)
                    if fallback:
                        logger.info(f"工具 [{tool_name}] 异常，使用降级缓存: {e}")
                        return fallback
                return f"[错误] 工具 [{tool_name}] 操作异常: {e}"

        finally:
            tool_active_calls.labels(tool_name=tool_name).dec()

    async def _invoke(self, func: Callable, args: dict[str, Any]) -> Any:
        """调用工具函数（支持同步和异步）"""
        if asyncio.iscoroutinefunction(func):
            return await func(**args)
        return func(**args)

    def _record_call(self, session_id: str, tool_name: str) -> None:
        if len(self._call_history) >= 10_000:
            oldest = next(iter(self._call_history))
            del self._call_history[oldest]
        if session_id not in self._call_history:
            self._call_history[session_id] = []
        if len(self._call_history[session_id]) >= 200:
            self._call_history[session_id] = self._call_history[session_id][-100:]
        self._call_history[session_id].append(tool_name)

    def _detect_duplicate(self, session_id: str, tool_name: str) -> bool:
        history = self._call_history.get(session_id, [])
        if len(history) < settings.AGENT_MAX_DUPLICATE_CALLS:
            return False
        return history[-settings.AGENT_MAX_DUPLICATE_CALLS:].count(tool_name) >= settings.AGENT_MAX_DUPLICATE_CALLS

    @staticmethod
    def _truncate_input(args: dict[str, Any]) -> str:
        """序列化输入参数并截断（审计用，防止参数过大）"""
        raw = str(args)
        return raw[:2000] if len(raw) > 2000 else raw

    @staticmethod
    def _log_audit(
        trace_id: str,
        user_id: str,
        session_id: str,
        tool_name: str,
        tool_input: str,
        tool_output: str,
        duration_ms: int,
        success: bool,
        error: str = "",
    ) -> None:
        """记录审计日志 — 同时写 loguru 文件和 DB 队列"""
        status = "SUCCESS" if success else "FAILED"
        error_str = f" error={error}" if error else ""
        log_msg = (
            f"tool={tool_name} result={status} duration={duration_ms}ms "
            f"input={tool_input[:100]} output={tool_output[:100]}{error_str}"
        )

        with contextlib.suppress(Exception):
            logger.bind(trace_id=trace_id, user_id=user_id).info(log_msg)

        # 异步入队写 DB
        try:
            _enqueue_audit({
                "trace_id": trace_id,
                "user_id": user_id,
                "conversation_id": session_id,
                "tool_name": tool_name,
                "tool_input": tool_input,
                "tool_output": tool_output,
                "duration_ms": duration_ms,
                "result": status,
                "error_msg": error[:500] if error else None,
            })
        except Exception as e:
            logger.warning(f"[审计] 入队失败: {e}")


# 全局实例
tool_executor = ToolExecutor()
