"""tools/health.py 工具健康检查测试"""

from unittest.mock import AsyncMock, patch

import pytest

from src.tools.health import check_tool_health, get_all_health_status


class TestCheckToolHealth:
    async def test_no_dependency_tool(self) -> None:
        """无依赖工具始终健康"""
        healthy = await check_tool_health("get_current_date")
        assert healthy is True

    async def test_unknown_tool_no_dependency(self) -> None:
        """未知工具（无映射）也视为健康"""
        healthy = await check_tool_health("some_unknown_tool")
        assert healthy is True

    async def test_cached_result(self) -> None:
        """缓存命中后不重新探测"""
        with patch("src.tools.health._probe", return_value=True) as mock_probe:
            # 第一次调用走探测
            r1 = await check_tool_health("search_knowledge")
            assert r1 is True
            mock_probe.assert_called_once()

            # 第二次调用走缓存
            r2 = await check_tool_health("search_knowledge")
            assert r2 is True
            mock_probe.assert_called_once()  # 不再调用

    async def test_dependency_unhealthy(self) -> None:
        """依赖不健康时返回 False"""
        from src.tools import health as health_module
        original_cache = health_module._cache.copy()
        health_module._cache.clear()

        try:
            with patch("src.tools.health._probe", return_value=False):
                healthy = await check_tool_health("search_knowledge")
                assert healthy is False
        finally:
            health_module._cache.clear()
            health_module._cache.update(original_cache)

    async def test_probe_chromadb_healthy(self) -> None:
        from src.tools.health import _probe_chromadb
        mock_store = MagicMock()
        mock_store.heartbeat.return_value = None

        with patch("src.knowledge.vector_store.vector_store", mock_store), \
             patch("asyncio.wait_for", return_value=None):
            healthy = await _probe_chromadb()
            assert healthy is True

    async def test_probe_chromadb_failure(self) -> None:
        from src.tools.health import _probe_chromadb
        mock_store = MagicMock()
        mock_store.heartbeat.side_effect = Exception("ChromaDB down")

        with patch("src.knowledge.vector_store.vector_store", mock_store):
            healthy = await _probe_chromadb()
            # heartbeat 抛异常 → asyncio.wait_for 包装后抛出 → 被 except 捕获
            assert healthy is False

    async def test_probe_postgresql_healthy(self) -> None:
        from src.tools.health import _probe_postgresql

        mock_session = AsyncMock()
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        with patch("src.core.database.async_session_factory", mock_session_factory):
            healthy = await _probe_postgresql()
            assert healthy is True

    async def test_probe_postgresql_failure(self) -> None:
        from src.tools.health import _probe_postgresql

        mock_session_factory = MagicMock()
        mock_session_factory.side_effect = Exception("DB down")

        with patch("src.core.database.async_session_factory", mock_session_factory):
            healthy = await _probe_postgresql()
            assert healthy is False

    async def test_probe_smtp_healthy(self) -> None:
        from src.tools.health import _probe_smtp

        mock_reader = MagicMock()
        mock_writer = MagicMock()
        mock_writer.wait_closed = AsyncMock()

        with patch("src.tools.health.asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            healthy = await _probe_smtp()
            assert healthy is True

    async def test_probe_smtp_failure(self) -> None:
        from src.tools.health import _probe_smtp

        with patch("src.tools.health.asyncio.open_connection", side_effect=OSError("Connection refused")):
            healthy = await _probe_smtp()
            assert healthy is False

    async def test_probe_unknown_dependency(self) -> None:
        from src.tools.health import _probe
        healthy = await _probe("unknown_dep")
        assert healthy is True

    async def test_probe_exception_caught(self) -> None:
        """探测时抛出异常应捕获并返回 False"""
        from src.tools.health import _probe

        with patch("src.tools.health._probe_chromadb", side_effect=RuntimeError("boom")):
            healthy = await _probe("chromadb")
            assert healthy is False


class TestGetAllHealthStatus:
    async def test_returns_three_deps(self) -> None:
        status = get_all_health_status()
        assert "chromadb" in status
        assert "postgresql" in status
        assert "smtp" in status

    async def test_unchecked_status_is_none(self) -> None:
        from src.tools import health as health_module
        original_cache = health_module._cache.copy()
        health_module._cache.clear()
        try:
            status = get_all_health_status()
            assert status["chromadb"]["healthy"] is None
        finally:
            health_module._cache.clear()
            health_module._cache.update(original_cache)


# 顶层 import，用于 patch
from unittest.mock import MagicMock
