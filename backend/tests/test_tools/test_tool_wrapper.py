"""tools/tool_wrapper.py 工具执行器测试 — 12步执行链验证"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.tool_registry import ToolPermission, ToolRegistry
from src.tools.tool_wrapper import ToolExecutor, ToolInputValidator


class TestToolInputValidator:
    def test_pass_when_no_limits(self) -> None:
        v = ToolInputValidator()
        meta = MagicMock()
        meta.input_max_lengths = {}
        error = v.validate("some_tool", {"key": "value"}, meta)
        assert error is None

    def test_pass_within_limit(self) -> None:
        v = ToolInputValidator()
        meta = MagicMock()
        meta.input_max_lengths = {"title": 50}
        error = v.validate("some_tool", {"title": "short"}, meta)
        assert error is None

    def test_exceed_limit(self) -> None:
        v = ToolInputValidator()
        meta = MagicMock()
        meta.input_max_lengths = {"content": 10}
        error = v.validate("some_tool", {"content": "x" * 15}, meta)
        assert error is not None
        assert "content" in error
        assert "15" in error

    def test_non_string_value_skipped(self) -> None:
        """非字符串参数不检查长度"""
        v = ToolInputValidator()
        meta = MagicMock()
        meta.input_max_lengths = {"count": 5}
        error = v.validate("some_tool", {"count": 100}, meta)
        assert error is None

    def test_default_limit_from_settings(self, monkeypatch) -> None:
        monkeypatch.setattr("src.tools.tool_wrapper.settings.TOOL_INPUT_MAX_LENGTHS", {"_default": 5})
        v = ToolInputValidator()
        meta = MagicMock()
        meta.input_max_lengths = {}  # 空，使用 _default
        error = v.validate("some_tool", {"text": "x" * 10}, meta)
        assert error is not None


class TestToolExecutor:
    @pytest.fixture
    def registry(self) -> ToolRegistry:
        return ToolRegistry()

    @pytest.fixture
    def executor(self, registry: ToolRegistry) -> ToolExecutor:
        return ToolExecutor(registry=registry)

    async def test_input_validation_fails(self, executor: ToolExecutor, registry: ToolRegistry) -> None:
        func = MagicMock()
        registry.register(
            func, "search", "搜索",
            permission=ToolPermission.READ_ONLY,
            category="knowledge",
            input_max_lengths={"query": 5},
        )
        result = await executor.execute("search", func, {"query": "x" * 10}, "user1", "sess1", "trace1")
        assert "参数校验失败" in result

    async def test_permission_denied_admin(self, executor: ToolExecutor, registry: ToolRegistry) -> None:
        func = MagicMock()
        registry.register(
            func, "admin_tool", "管理",
            permission=ToolPermission.ADMIN,
            category="other",
        )
        result = await executor.execute("admin_tool", func, {}, "user1", "sess1", "trace1")
        assert "管理员权限" in result

    async def test_enabled_check(self, executor: ToolExecutor, registry: ToolRegistry) -> None:
        func = MagicMock()
        registry.register(
            func, "disabled_tool", "已禁用",
            permission=ToolPermission.READ_WRITE,
            category="other",
        )
        registry.disable("disabled_tool")

        # 绕过权限和健康检查
        with (
            patch("src.tools.tool_wrapper.ToolInputValidator.validate", return_value=None),
            patch("src.tools.rate_limiter.tool_rate_limiter.acquire", return_value=True),
        ):
            result = await executor.execute("disabled_tool", func, {}, "user1", "sess1", "trace1")
            assert "已被管理员禁用" in result

    async def test_rate_limited(self, executor: ToolExecutor, registry: ToolRegistry) -> None:
        func = MagicMock()
        registry.register(
            func, "rate_tool", "限流",
            permission=ToolPermission.READ_ONLY,
            category="other",
        )
        with (
            patch("src.tools.tool_wrapper.ToolInputValidator.validate", return_value=None),
            patch("src.tools.rate_limiter.tool_rate_limiter.acquire", return_value=False),
        ):
            result = await executor.execute("rate_tool", func, {}, "user1", "sess1", "trace1")
            assert "限流" in result

    async def test_breaker_open(self, executor: ToolExecutor, registry: ToolRegistry, monkeypatch) -> None:
        monkeypatch.setattr("src.tools.tool_registry.settings.AGENT_CIRCUIT_BREAKER_THRESHOLD", 2)
        monkeypatch.setattr("src.tools.tool_registry.settings.AGENT_CIRCUIT_BREAKER_TIMEOUT", 999)
        func = MagicMock()
        registry.register(
            func, "breaker_tool", "熔断",
            permission=ToolPermission.READ_ONLY,
            category="other",
        )
        registry.record_failure("breaker_tool")
        registry.record_failure("breaker_tool")

        with (
            patch("src.tools.tool_wrapper.ToolInputValidator.validate", return_value=None),
            patch("src.tools.rate_limiter.tool_rate_limiter.acquire", return_value=True),
        ):
            with pytest.raises(Exception):  # 熔断器打开会抛异常
                await executor.execute("breaker_tool", func, {}, "user1", "sess1", "trace1")

    async def test_successful_execution(self, executor: ToolExecutor, registry: ToolRegistry) -> None:
        func = MagicMock(return_value="success result")
        registry.register(
            func, "ok_tool", "正常工具",
            permission=ToolPermission.READ_ONLY,
            category="other",
        )
        with (
            patch("src.tools.tool_wrapper.ToolInputValidator.validate", return_value=None),
            patch("src.tools.rate_limiter.tool_rate_limiter.acquire", return_value=True),
            patch("src.tools.tool_wrapper.tool_cache.put"),
            patch("src.tools.tool_wrapper.tool_cache.get", return_value=None),
        ):
            result = await executor.execute("ok_tool", func, {}, "user1", "sess1", "trace1")
            assert result == "success result"

    async def test_async_tool_function(self, executor: ToolExecutor, registry: ToolRegistry) -> None:
        func = AsyncMock(return_value="async result")
        registry.register(
            func, "async_tool", "异步工具",
            permission=ToolPermission.READ_ONLY,
            category="other",
        )
        with (
            patch("src.tools.tool_wrapper.ToolInputValidator.validate", return_value=None),
            patch("src.tools.rate_limiter.tool_rate_limiter.acquire", return_value=True),
            patch("src.tools.tool_wrapper.tool_cache.put"),
            patch("src.tools.tool_wrapper.tool_cache.get", return_value=None),
        ):
            result = await executor.execute("async_tool", func, {}, "user1", "sess1", "trace1")
            assert result == "async result"
            func.assert_awaited_once()

    async def test_output_truncation(self, executor: ToolExecutor, registry: ToolRegistry) -> None:
        long_output = "x" * 5000
        func = MagicMock(return_value=long_output)
        registry.register(
            func, "long_tool", "长输出",
            permission=ToolPermission.READ_ONLY,
            category="other",
            output_max_length=10,
        )
        with (
            patch("src.tools.tool_wrapper.ToolInputValidator.validate", return_value=None),
            patch("src.tools.rate_limiter.tool_rate_limiter.acquire", return_value=True),
            patch("src.tools.tool_wrapper.tool_cache.put"),
            patch("src.tools.tool_wrapper.tool_cache.get", return_value=None),
        ):
            result = await executor.execute("long_tool", func, {}, "user1", "sess1", "trace1")
            assert "已截断" in result
            assert len(result) < len(long_output)

    async def test_timeout_fallback(self, executor: ToolExecutor, registry: ToolRegistry) -> None:
        async def slow_func() -> str:
            import asyncio
            await asyncio.sleep(10)
            return "done"

        registry.register(
            slow_func, "slow_tool", "慢工具",
            permission=ToolPermission.READ_ONLY,
            category="other",
        )
        with (
            patch("src.tools.tool_wrapper.ToolInputValidator.validate", return_value=None),
            patch("src.tools.rate_limiter.tool_rate_limiter.acquire", return_value=True),
            patch("src.tools.tool_wrapper.settings.TOOL_TIMEOUT", 0.01),
            patch("src.tools.tool_wrapper.tool_cache.get_fallback", return_value="cached fallback"),
        ):
            result = await executor.execute("slow_tool", slow_func, {}, "user1", "sess1", "trace1")
            assert "cached fallback" in result

    async def test_tool_error_fallback(self, executor: ToolExecutor, registry: ToolRegistry) -> None:
        def failing_func() -> str:
            raise ValueError("downstream error")

        registry.register(
            failing_func, "fail_tool", "失败工具",
            permission=ToolPermission.READ_ONLY,
            category="other",
        )
        with (
            patch("src.tools.tool_wrapper.ToolInputValidator.validate", return_value=None),
            patch("src.tools.rate_limiter.tool_rate_limiter.acquire", return_value=True),
            patch("src.tools.tool_wrapper.tool_cache.get_fallback", return_value="error fallback"),
        ):
            result = await executor.execute("fail_tool", failing_func, {}, "user1", "sess1", "trace1")
            assert "error fallback" in result

    async def test_cache_hit(self, executor: ToolExecutor, registry: ToolRegistry) -> None:
        func = MagicMock()
        registry.register(
            func, "cached_tool", "缓存工具",
            permission=ToolPermission.READ_ONLY,
            category="other",
        )
        with (
            patch("src.tools.tool_wrapper.ToolInputValidator.validate", return_value=None),
            patch("src.tools.rate_limiter.tool_rate_limiter.acquire", return_value=True),
            patch("src.tools.tool_wrapper.tool_cache.get", return_value="cached value"),
        ):
            result = await executor.execute("cached_tool", func, {}, "user1", "sess1", "trace1")
            assert result == "cached value"
            func.assert_not_called()  # 缓存命中了不调用工具

    async def test_no_cached_write_tool(self, executor: ToolExecutor, registry: ToolRegistry) -> None:
        """写操作不检查缓存"""
        func = MagicMock(return_value="write result")
        registry.register(
            func, "write_tool", "写工具",
            permission=ToolPermission.READ_WRITE,
            category="memo",
        )
        with (
            patch("src.tools.tool_wrapper.ToolInputValidator.validate", return_value=None),
            patch("src.tools.rate_limiter.tool_rate_limiter.acquire", return_value=True),
            patch("src.tools.tool_wrapper.tool_cache.get") as mock_cache_get,
        ):
            result = await executor.execute("write_tool", func, {}, "user1", "sess1", "trace1")
            assert result == "write result"
            mock_cache_get.assert_not_called()  # 写工具不读缓存

    async def test_duplicate_detection(self, executor: ToolExecutor, registry: ToolRegistry) -> None:
        func = MagicMock(return_value="ok")
        registry.register(
            func, "dup_tool", "重复工具",
            permission=ToolPermission.READ_ONLY,
            category="other",
        )
        with (
            patch("src.tools.tool_wrapper.ToolInputValidator.validate", return_value=None),
            patch("src.tools.rate_limiter.tool_rate_limiter.acquire", return_value=True),
            patch("src.tools.tool_wrapper.tool_cache.get", return_value=None),
        ):
            # 预设历史，下一次调用即检测到重复（RuntimeError 直接抛出，外层无 except）
            executor._call_history["sess1"] = ["dup_tool"] * 3
            with pytest.raises(RuntimeError, match="连续调用"):
                await executor.execute("dup_tool", func, {}, "user1", "sess1", "trace1")

    async def test_duplicate_detection_not_triggered(self, executor: ToolExecutor, registry: ToolRegistry) -> None:
        """混合工具调用不会触发重复检测"""
        func_a = MagicMock(return_value="ok")
        func_b = MagicMock(return_value="ok")
        registry.register(func_a, "tool_a", "工具A", permission=ToolPermission.READ_ONLY, category="other")
        registry.register(func_b, "tool_b", "工具B", permission=ToolPermission.READ_ONLY, category="other")
        with (
            patch("src.tools.tool_wrapper.ToolInputValidator.validate", return_value=None),
            patch("src.tools.rate_limiter.tool_rate_limiter.acquire", return_value=True),
            patch("src.tools.tool_wrapper.tool_cache.get", return_value=None),
        ):
            # 交叉调用不同工具不会触发
            r1 = await executor.execute("tool_a", func_a, {}, "user1", "sess1", "trace1")
            r2 = await executor.execute("tool_b", func_b, {}, "user1", "sess1", "trace1")
            r3 = await executor.execute("tool_a", func_a, {}, "user1", "sess1", "trace1")
            assert r1 == "ok"
            assert r2 == "ok"
            assert r3 == "ok"
