"""全局测试 fixtures — mock Redis、DB、LLM、ChromaDB、SMTP 等外部依赖"""

import asyncio
import json
from collections.abc import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


# ==================== 事件循环 ====================

@pytest.fixture
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ==================== Mock Redis ====================

class FakeRedis:
    """内存 Redis 模拟 — 支持 set/get/delete/keys/ttl/exists + Lua evalsha"""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._ttl: dict[str, int] = {}
        self._scripts: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value
        if ex is not None:
            self._ttl[key] = ex

    async def delete(self, *keys: str) -> None:
        for k in keys:
            self._store.pop(k, None)
            self._ttl.pop(k, None)

    async def keys(self, pattern: str = "*") -> list[str]:
        import fnmatch
        return [k for k in self._store if fnmatch.fnmatch(k, pattern)]

    async def ttl(self, key: str) -> int:
        return self._ttl.get(key, -1)

    async def exists(self, key: str) -> int:
        return 1 if key in self._store else 0

    async def expire(self, key: str, seconds: int) -> bool:
        if key in self._store:
            self._ttl[key] = seconds
            return True
        return False

    async def incr(self, key: str) -> int:
        current = int(self._store.get(key, "0")) + 1
        self._store[key] = str(current)
        return current

    async def script_load(self, script: str) -> str:
        import hashlib
        sha = hashlib.sha1(script.encode()).hexdigest()
        self._scripts[sha] = script
        return sha

    async def evalsha(self, sha: str, numkeys: int, *args: str | int) -> int:
        """执行预加载的 Lua 脚本 — 简化版限流逻辑"""
        script = self._scripts.get(sha, "")
        if not script or "INCR" not in script:
            return 1
        # 解析: key=args[0] (after numkeys=1), limit=int(args[1]), window=int(args[2])
        if numkeys < 1 or len(args) < 3:
            return 1
        key = str(args[0])
        limit = int(args[1])
        # window = int(args[2])  # 未使用，简化实现

        current = await self.incr(key)
        if current == 1:
            await self.expire(key, 60)
        return 1 if current <= limit else 0

    async def close(self) -> None:
        pass


@pytest_asyncio.fixture
async def mock_redis() -> AsyncGenerator[FakeRedis, None]:
    """每个测试独立的 FakeRedis + 自动 patch get_redis（需要同时 patch 直接导入和重导出路径）"""
    redis = FakeRedis()
    with (
        patch("src.core.redis_client.get_redis", return_value=redis),
        patch("src.core.memory.get_redis", return_value=redis),
        patch("src.tools.rate_limiter.get_redis", return_value=redis),
    ):
        yield redis


# ==================== Mock LLM ====================

class FakeLLM:
    """Mock LLM — 支持 ainvoke，返回预设内容"""

    def __init__(self, response: str = "mock response") -> None:
        self.response = response
        self._last_prompt: str = ""

    async def ainvoke(self, prompt: str) -> "FakeLLMResponse":
        self._last_prompt = prompt
        return FakeLLMResponse(self.response)


class FakeLLMResponse:
    def __init__(self, content: str) -> None:
        self.content = content
        self.additional_kwargs = {}
        self.response_metadata = {}
        self.usage_metadata = {}


class FakeChatModel:
    """Mock ChatModel — 支持 bind_tools"""

    def __init__(self, response_text: str = "mock response") -> None:
        self._response_text = response_text
        self._bound_tools: list = []

    def bind_tools(self, tools: list, **kwargs) -> "FakeChatModel":
        self._bound_tools = tools
        return self

    async def ainvoke(self, messages: list, **kwargs) -> FakeLLMResponse:
        return FakeLLMResponse(self._response_text)


@pytest.fixture
def mock_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def mock_chat_model() -> FakeChatModel:
    return FakeChatModel()


# ==================== Mock Metrics (Prometheus) ====================

@pytest.fixture(autouse=True)
def mock_metrics() -> Generator[None, None, None]:
    """全局 mock Prometheus 指标，避免测试中注册冲突"""
    mocks = [
        patch("src.core.metrics.tool_calls_total", MagicMock()),
        patch("src.core.metrics.tool_call_duration_seconds", MagicMock()),
        patch("src.core.metrics.tool_active_calls", MagicMock()),
        patch("src.core.metrics.tool_rate_limit_hits_total", MagicMock()),
        patch("src.core.metrics.tool_health_status", MagicMock()),
        patch("src.core.metrics.tool_audit_queue_size", MagicMock()),
        patch("src.core.metrics.memory_session_gauge", MagicMock()),
        patch("src.core.metrics.memory_summary_total", MagicMock()),
        patch("src.core.metrics.memory_summary_duration_seconds", MagicMock()),
        patch("src.core.metrics.match_total", MagicMock()),
        patch("src.core.metrics.match_agent_duration_seconds", MagicMock()),
        patch("src.core.metrics.match_score_distribution", MagicMock()),
    ]
    for m in mocks:
        m.start()
    yield
    for m in mocks:
        m.stop()


# ==================== Mock 数据库 ====================

@pytest.fixture
def mock_db_session() -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def isolated_registry() -> Generator:
    """每个测试独立的 ToolRegistry（不污染全局实例）"""
    from src.tools.tool_registry import ToolRegistry

    registry = ToolRegistry()
    yield registry
    registry._tools.clear()
    registry._breakers.clear()


# ==================== Mock 工具函数 ====================

@pytest.fixture
def dummy_tool_func() -> MagicMock:
    """创建一个模拟的工具函数"""
    func = MagicMock()
    func.name = "test_tool"
    func.description = "测试工具描述"
    return func


# ==================== Mock SMTP ====================

@pytest.fixture
def mock_smtp() -> Generator[MagicMock, None, None]:
    with patch("aiosmtplib.send") as mock_send:
        mock_send.return_value = MagicMock()
        yield mock_send
