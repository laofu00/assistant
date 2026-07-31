"""core/cache.py 工具降级缓存测试"""

import time

from src.core.cache import ToolCache, tool_cache


class TestToolCache:
    def test_put_and_get(self) -> None:
        cache = ToolCache()
        cache.put("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_expired(self) -> None:
        cache = ToolCache()
        cache.put("key1", "value1", ttl_ms=1)
        time.sleep(0.01)  # 等待过期
        assert cache.get("key1") is None

    def test_get_fallback_expired(self) -> None:
        """降级获取：即使过期也返回"""
        cache = ToolCache()
        cache.put("key1", "value1", ttl_ms=1)
        time.sleep(0.01)
        assert cache.get_fallback("key1") == "value1"

    def test_get_fallback_missing(self) -> None:
        cache = ToolCache()
        assert cache.get_fallback("nonexistent") is None

    def test_invalidate(self) -> None:
        cache = ToolCache()
        cache.put("key1", "value1")
        cache.invalidate("key1")
        assert cache.get("key1") is None

    def test_invalidate_by_prefix(self) -> None:
        cache = ToolCache()
        cache.put("prefix:a", "1")
        cache.put("prefix:b", "2")
        cache.put("other:c", "3")
        count = cache.invalidate_by_prefix("prefix:")
        assert count == 2
        assert cache.get("other:c") == "3"
        assert cache.get("prefix:a") is None

    def test_clear(self) -> None:
        cache = ToolCache()
        cache.put("k1", "v1")
        cache.put("k2", "v2")
        cache.clear()
        assert len(cache) == 0

    def test_len(self) -> None:
        cache = ToolCache()
        cache.put("a", "1")
        cache.put("b", "2")
        assert len(cache) == 2

    def test_make_key(self) -> None:
        key = ToolCache.make_key("search", "user123", "python", "django")
        assert key == "search:user123:python:django"

    def test_make_key_single_param(self) -> None:
        key = ToolCache.make_key("tool", "user1", "param1")
        assert key == "tool:user1:param1"

    def test_global_instance(self) -> None:
        """验证全局单例"""
        assert isinstance(tool_cache, ToolCache)
