"""Token 写入后台任务 — 队列 → 定期刷入 DB

TokenCaptureCallback 已统一迁移至 src.core.llm_factory._TokenCallback，
通过 contextvars 自动注入，无需各调用点手动管理。
"""

import asyncio
from collections import deque

from loguru import logger

# 后台任务是否已启动
_queue_started = False
# token 记录队列：[(capture_kwargs, ...)]
_token_queue: deque[dict] = deque()


async def _flush_queue():
    """后台任务：定期从队列中取记录写入 DB"""
    from src.token.capture import capture_tokens

    while True:
        await asyncio.sleep(2)  # 每 2 秒刷一次
        while _token_queue:
            record = _token_queue.popleft()
            try:
                await capture_tokens(**record)
                logger.debug(f"[Token] 写入成功: total={record.get('total_tokens')}")
            except Exception as e:
                logger.warning(f"[Token] 队列写入失败: {e}")


def start_token_worker():
    """启动 token 写入后台任务（在 asgi lifespan 中调用）"""
    global _queue_started
    if not _queue_started:
        _queue_started = True
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        loop.create_task(_flush_queue())
        logger.info("[Token] 后台写入任务已启动")
