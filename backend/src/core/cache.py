"""工具降级缓存 — TTL + 过期兜底 fallback"""

import time
from collections.abc import Callable
from typing import Any


class CacheEntry:
    def __init__(self, value: str, ttl_ms: int) -> None:
        self.value = value
        self.expire_at = time.monotonic() + ttl_ms / 1000

    def is_expired(self) -> bool:
        return time.monotonic() > self.expire_at


class ToolCache:
    """工具调用结果缓存 + 降级机制

    只缓存只读操作的成功结果，写操作不缓存。
    对齐 Java 版 ToolCacheUtil。
    """

    DEFAULT_TTL_MS: int = 2 * 60 * 1000  # 2 分钟

    def __init__(self) -> None:
        self._store: dict[str, CacheEntry] = {}

    def get(self, key: str) -> str | None:
        """获取缓存（过期返回 None）"""
        entry = self._store.get(key)
        if entry is not None and not entry.is_expired():
            return entry.value
        return None

    def get_fallback(self, key: str) -> str | None:
        """降级获取缓存（即使过期也返回，用于工具失败时的兜底）"""
        entry = self._store.get(key)
        if entry is not None:
            return entry.value
        return None

    def put(self, key: str, value: str, ttl_ms: int | None = None) -> None:
        """存入缓存"""
        ttl = ttl_ms if ttl_ms is not None else self.DEFAULT_TTL_MS
        self._store[key] = CacheEntry(value, ttl)

    def invalidate(self, key: str) -> None:
        """清除指定缓存"""
        self._store.pop(key, None)

    def invalidate_by_prefix(self, prefix: str) -> int:
        """按前缀清除缓存，返回清除数量"""
        keys = [k for k in self._store if k.startswith(prefix)]
        for k in keys:
            del self._store[k]
        return len(keys)

    def clear(self) -> None:
        """清除所有缓存"""
        self._store.clear()

    @staticmethod
    def make_key(tool: str, user_id: str, *params: Any) -> str:
        """生成缓存 key"""
        parts = [tool, user_id]
        parts.extend(str(p) for p in params)
        return ":".join(parts)

    def __len__(self) -> int:
        return len(self._store)


# 全局实例
tool_cache = ToolCache()
