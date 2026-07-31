"""tools/rate_limiter.py 三层限流测试 — 模拟 Redis"""

import pytest

from src.tools.rate_limiter import ToolRateLimiter, tool_rate_limiter


class TestToolRateLimiter:
    @pytest.fixture
    def limiter(self) -> ToolRateLimiter:
        return ToolRateLimiter()

    async def test_first_request_allowed(self, limiter: ToolRateLimiter) -> None:
        from unittest.mock import patch
        redis = FakeRedisForLimit()
        with patch("src.tools.rate_limiter.get_redis", return_value=redis):
            result = await limiter.acquire("search_knowledge", "user1")
            assert result is True

    async def test_user_tool_limit_exceeded(self, limiter: ToolRateLimiter, monkeypatch) -> None:
        from unittest.mock import patch

        monkeypatch.setattr(
            "src.tools.rate_limiter.settings.TOOL_RATE_LIMIT_USER_TOOL",
            {"test_tool": 1, "_default": 30},
        )
        monkeypatch.setattr("src.tools.rate_limiter.settings.TOOL_RATE_LIMIT_USER_TOTAL", 0)

        with patch("src.tools.rate_limiter.get_redis", return_value=FakeRedisForLimit()):
            limiter._script_hash = None
            r = await limiter.acquire("test_tool", "user1")
            assert r is True
            r = await limiter.acquire("test_tool", "user1")
            assert r is False

    async def test_global_limit_exceeded(self, limiter: ToolRateLimiter, monkeypatch) -> None:
        from unittest.mock import patch

        monkeypatch.setattr(
            "src.tools.rate_limiter.settings.TOOL_RATE_LIMIT_USER_TOOL",
            {"search_knowledge": 999, "_default": 30},
        )
        monkeypatch.setattr(
            "src.tools.rate_limiter.settings.TOOL_RATE_LIMIT_GLOBAL_TOOL",
            {"chroma_ops": 1},
        )
        monkeypatch.setattr("src.tools.rate_limiter.settings.TOOL_RATE_LIMIT_USER_TOTAL", 0)

        with patch("src.tools.rate_limiter.get_redis", return_value=FakeRedisForLimit()):
            limiter._script_hash = None
            r = await limiter.acquire("search_knowledge", "user1")
            assert r is True
            r = await limiter.acquire("search_knowledge", "user2")
            assert r is False  # 全局限流

    async def test_user_total_limit_exceeded(self, limiter: ToolRateLimiter, monkeypatch) -> None:
        from unittest.mock import patch

        monkeypatch.setattr(
            "src.tools.rate_limiter.settings.TOOL_RATE_LIMIT_USER_TOOL",
            {"_default": 999},
        )
        monkeypatch.setattr(
            "src.tools.rate_limiter.settings.TOOL_RATE_LIMIT_GLOBAL_TOOL",
            {"chroma_ops": 999},
        )
        monkeypatch.setattr("src.tools.rate_limiter.settings.TOOL_RATE_LIMIT_USER_TOTAL", 1)

        with patch("src.tools.rate_limiter.get_redis", return_value=FakeRedisForLimit()):
            limiter._script_hash = None
            r = await limiter.acquire("search_knowledge", "user1")
            assert r is True
            r = await limiter.acquire("list_memos", "user1")
            assert r is False  # 用户总 QPS 超限

    async def test_global_instance(self) -> None:
        assert isinstance(tool_rate_limiter, ToolRateLimiter)


class FakeRedisForLimit:
    """更精确的 FakeRedis 用于限流测试"""
    def __init__(self) -> None:
        self._store: dict[str, int] = {}
        self._scripts: dict[str, str] = {}

    async def script_load(self, script: str) -> str:
        import hashlib
        sha = hashlib.sha1(script.encode()).hexdigest()
        self._scripts[sha] = script
        return sha

    async def evalsha(self, sha: str, numkeys: int, key: str, limit: int, window: int) -> int:
        current = self._store.get(key, 0) + 1
        self._store[key] = current
        return 1 if current <= limit else 0
