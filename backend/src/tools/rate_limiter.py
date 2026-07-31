"""三层限流器 — Redis 滑动窗口

架构:
  第一层: 单用户单工具 QPS（防恶意用户刷爆单个工具）
  第二层: 全局工具 QPS（保护下游服务，防总量打挂）
  第三层: 单用户总 QPS（公平使用兜底）

全部通过才放行，任何一层不通过即拒绝。
"""


from loguru import logger

from src.core.config import settings
from src.core.metrics import tool_rate_limit_hits_total
from src.core.redis_client import get_redis

# 工具 → 全局限流分组映射
_TOOL_GLOBAL_GROUP: dict[str, str] = {
    "search_knowledge": "chroma_ops",
    "upload_knowledge": "chroma_ops",
    "get_document_content": "chroma_ops",
    "list_knowledge": "chroma_ops",
    "delete_knowledge": "chroma_ops",
    "do_send_email": "smtp_ops",
    "do_send_formatted_email": "smtp_ops",
    "preview_email": "smtp_ops",
    "add_memo": "db_write",
    "update_memo": "db_write",
    "delete_memo": "db_write",
    "complete_memo": "db_write",
}

# Lua 脚本：原子性检查 + 递增 + 设置 TTL
_ACQUIRE_SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local current = redis.call('INCR', key)
if current == 1 then
    redis.call('EXPIRE', key, window)
end
if current > limit then
    return 0
end
return 1
"""


class ToolRateLimiter:
    """三层限流器"""

    def __init__(self) -> None:
        self._script_hash: str | None = None

    async def _load_script(self) -> str:
        if self._script_hash is None:
            r = await get_redis()
            self._script_hash = await r.script_load(_ACQUIRE_SCRIPT)
        return self._script_hash

    async def acquire(self, tool_name: str, user_id: str) -> bool:
        """尝试获取调用许可，返回 True（放行）或 False（拒绝）

        三层全部通过才返回 True。
        """
        redis_client = await get_redis()
        sha = await self._load_script()
        window = 60  # 滑动窗口 60 秒

        # 第一层：单用户单工具
        user_tool_limit = self._get_user_tool_limit(tool_name)
        if user_tool_limit > 0:
            user_tool_key = f"ratelimit:user_tool:{user_id}:{tool_name}:minute"
            ok = await redis_client.evalsha(sha, 1, user_tool_key, user_tool_limit, window)
            if not ok:
                self._record_hit(tool_name, "user_tool")
                return False

        # 第二层：全局工具
        global_group = _TOOL_GLOBAL_GROUP.get(tool_name)
        if global_group:
            global_limit = settings.TOOL_RATE_LIMIT_GLOBAL_TOOL.get(global_group, 0)
            if global_limit > 0:
                global_key = f"ratelimit:global_tool:{global_group}:minute"
                ok = await redis_client.evalsha(sha, 1, global_key, global_limit, window)
                if not ok:
                    self._record_hit(tool_name, "global_tool")
                    return False

        # 第三层：单用户总 QPS
        user_total_limit = settings.TOOL_RATE_LIMIT_USER_TOTAL
        if user_total_limit > 0:
            user_total_key = f"ratelimit:user_total:{user_id}:minute"
            ok = await redis_client.evalsha(sha, 1, user_total_key, user_total_limit, window)
            if not ok:
                self._record_hit(tool_name, "user_total")
                return False

        return True

    def _get_user_tool_limit(self, tool_name: str) -> int:
        config = settings.TOOL_RATE_LIMIT_USER_TOOL
        return config.get(tool_name, config.get("_default", 0))

    @staticmethod
    def _record_hit(tool_name: str, layer: str) -> None:
        tool_rate_limit_hits_total.labels(tool_name=tool_name, layer=layer).inc()
        logger.warning(f"工具限流命中: tool={tool_name}, layer={layer}")


# 全局单例
tool_rate_limiter = ToolRateLimiter()
