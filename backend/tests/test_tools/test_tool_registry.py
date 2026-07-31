"""tools/tool_registry.py 工具注册中心测试"""

from unittest.mock import MagicMock

import pytest

from src.core.exceptions import CircuitBreakerOpenError
from src.tools.tool_registry import CircuitBreaker, ToolMeta, ToolPermission, ToolRegistry


class TestToolPermission:
    def test_enum_values(self) -> None:
        assert ToolPermission.READ_ONLY == "READ_ONLY"
        assert ToolPermission.READ_WRITE == "READ_WRITE"
        assert ToolPermission.ADMIN == "ADMIN"

    def test_str_enum_values(self) -> None:
        """验证 StrEnum 值是标准字符串"""
        assert isinstance(ToolPermission.READ_ONLY, str)
        assert list(ToolPermission.__members__.keys()) == ["READ_ONLY", "READ_WRITE", "ADMIN"]


class TestCircuitBreaker:
    def test_initial_state(self) -> None:
        cb = CircuitBreaker()
        assert cb.is_open is False
        assert cb.failure_count == 0
        assert cb.last_failure_time is None

    def test_record_failure_below_threshold(self) -> None:
        cb = CircuitBreaker()
        for _ in range(4):
            cb.record_failure()
        assert cb.failure_count == 4
        assert cb.is_open is False

    def test_opens_after_threshold(self, monkeypatch) -> None:
        """连续失败达到阈值后熔断器打开"""
        monkeypatch.setattr("src.tools.tool_registry.settings.AGENT_CIRCUIT_BREAKER_THRESHOLD", 5)
        cb = CircuitBreaker()
        for _ in range(5):
            cb.record_failure()
        assert cb.is_open is True
        assert cb.failure_count == 5

    def test_check_raises_when_open(self, monkeypatch) -> None:
        monkeypatch.setattr("src.tools.tool_registry.settings.AGENT_CIRCUIT_BREAKER_THRESHOLD", 3)
        monkeypatch.setattr("src.tools.tool_registry.settings.AGENT_CIRCUIT_BREAKER_TIMEOUT", 60)
        cb = CircuitBreaker()
        for _ in range(3):
            cb.record_failure()
        with pytest.raises(CircuitBreakerOpenError):
            cb.check()

    def test_check_passes_when_closed(self) -> None:
        cb = CircuitBreaker()
        cb.check()  # 不抛异常

    def test_recovery_after_timeout(self, monkeypatch) -> None:
        """超时后熔断器恢复"""
        monkeypatch.setattr("src.tools.tool_registry.settings.AGENT_CIRCUIT_BREAKER_THRESHOLD", 2)
        monkeypatch.setattr("src.tools.tool_registry.settings.AGENT_CIRCUIT_BREAKER_TIMEOUT", 0)
        cb = CircuitBreaker()
        for _ in range(2):
            cb.record_failure()
        assert cb.is_open is True
        cb.check()  # 不应抛异常，因为 timeout=0 已过期
        assert cb.is_open is False

    def test_record_success_resets(self, monkeypatch) -> None:
        monkeypatch.setattr("src.tools.tool_registry.settings.AGENT_CIRCUIT_BREAKER_THRESHOLD", 3)
        cb = CircuitBreaker()
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.is_open is False


class TestToolRegistry:
    @pytest.fixture
    def registry(self) -> ToolRegistry:
        return ToolRegistry()

    @pytest.fixture
    def dummy_func(self) -> MagicMock:
        return MagicMock()

    def test_register(self, registry: ToolRegistry, dummy_func: MagicMock) -> None:
        registry.register(dummy_func, "test_tool", "测试工具")
        meta = registry.get("test_tool")
        assert meta is not None
        assert meta.name == "test_tool"
        assert meta.enabled is True

    def test_get_nonexistent(self, registry: ToolRegistry) -> None:
        assert registry.get("no_such") is None

    def test_list_all(self, registry: ToolRegistry, dummy_func: MagicMock) -> None:
        registry.register(dummy_func, "tool_a", "A")
        registry.register(dummy_func, "tool_b", "B")
        assert len(registry.list_all()) == 2

    def test_list_by_permission(self, registry: ToolRegistry, dummy_func: MagicMock) -> None:
        registry.register(dummy_func, "read_tool", "R", permission=ToolPermission.READ_ONLY)
        registry.register(dummy_func, "write_tool", "W", permission=ToolPermission.READ_WRITE)
        registry.register(dummy_func, "admin_tool", "A", permission=ToolPermission.ADMIN)

        # list_by_permission 使用 value 字符串的比较语义
        # READ_WRITE filter: A <= R(WRITE) <= R(WRITE) → 全部通过
        rw_tools = registry.list_by_permission(ToolPermission.READ_WRITE)
        rw_names = {t.name for t in rw_tools}
        assert len(rw_tools) == 3
        assert "read_tool" in rw_names
        assert "write_tool" in rw_names
        assert "admin_tool" in rw_names

    def test_enable_disable(self, registry: ToolRegistry, dummy_func: MagicMock) -> None:
        registry.register(dummy_func, "switch_tool", "S")
        assert registry.is_enabled("switch_tool") is True
        registry.disable("switch_tool")
        assert registry.is_enabled("switch_tool") is False
        registry.enable("switch_tool")
        assert registry.is_enabled("switch_tool") is True

    def test_enable_nonexistent(self, registry: ToolRegistry) -> None:
        assert registry.enable("no_such") is False

    def test_disable_nonexistent(self, registry: ToolRegistry) -> None:
        assert registry.disable("no_such") is False

    def test_get_stats(self, registry: ToolRegistry, dummy_func: MagicMock) -> None:
        registry.register(dummy_func, "k_tool", "K", category="knowledge")
        registry.register(dummy_func, "m_tool", "M", category="memo")
        registry.disable("m_tool")

        stats = registry.get_stats()
        assert stats["total"] == 2
        assert stats["enabled"] == 1
        assert stats["disabled"] == 1
        assert stats["categories"]["knowledge"] == 1
        assert stats["categories"]["memo"] == 1

    def test_breaker_per_tool(self, registry: ToolRegistry, dummy_func: MagicMock) -> None:
        registry.register(dummy_func, "t1", "T1")
        registry.register(dummy_func, "t2", "T2")
        b1 = registry.get_breaker("t1")
        b2 = registry.get_breaker("t2")
        assert b1 is not b2

    def test_record_and_check_breaker(self, registry: ToolRegistry, dummy_func: MagicMock, monkeypatch) -> None:
        monkeypatch.setattr("src.tools.tool_registry.settings.AGENT_CIRCUIT_BREAKER_THRESHOLD", 2)
        registry.register(dummy_func, "t", "T")
        registry.record_failure("t")
        registry.record_failure("t")
        with pytest.raises(CircuitBreakerOpenError):
            registry.check_breaker("t")

    def test_version_management(self, registry: ToolRegistry, dummy_func: MagicMock) -> None:
        registry.register(dummy_func, "t", "T")
        assert registry.get_version("t") == 1
        registry.set_version("t", 2)
        assert registry.get_version("t") == 2
        assert registry.set_version("no_such", 3) is False
