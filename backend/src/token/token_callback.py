"""Token 捕获 — callback 收集 token → 队列 → 后台任务写入 DB

避免跨线程使用 async engine 的 event loop 冲突。
"""

import asyncio
from collections import deque
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
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


class TokenCaptureCallback(BaseCallbackHandler):
    """LangChain 回调：拦截 on_llm_end，将 token 数据推入队列"""

    def __init__(
        self,
        trace_id: str = "",
        session_id: str = "",
        user_id: str = "",
        intent_type: str = "",
        call_purpose: str = "",
        tool_chain: list[dict] | None = None,
    ) -> None:
        self.trace_id = trace_id
        self.session_id = session_id
        self.user_id = user_id
        self.intent_type = intent_type
        self.call_purpose = call_purpose
        self.tool_chain = tool_chain or []

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """LLM 调用完成时捕获 token 用量，推入队列"""
        try:
            usage = _extract_usage(response)
            if not usage:
                return

            tool_called = len(self.tool_chain) > 0
            tool_names = (
                ",".join(sorted({t.get("tool", "") for t in self.tool_chain}))
                if self.tool_chain else ""
            )

            logger.info(
                f"[Token] input={usage['input_tokens']} output={usage['output_tokens']} "
                f"total={usage['total_tokens']} tools={tool_names}"
            )

            from src.core.config import settings

            _token_queue.append({
                "trace_id": self.trace_id,
                "session_id": self.session_id,
                "user_id": self.user_id,
                "model_name": settings.MODEL_NAME,
                "input_tokens": usage["input_tokens"],
                "output_tokens": usage["output_tokens"],
                "total_tokens": usage["total_tokens"],
                "intent_type": self.intent_type or "REACT_AGENT",
                "call_purpose": self.call_purpose,
                "tool_called": tool_called,
                "tool_names": tool_names,
            })
        except Exception as e:
            logger.warning(f"Token 回调异常: {e}")


def _extract_usage(response: LLMResult) -> dict | None:
    """从 LLMResult 中提取 token 用量"""
    llm_output = response.llm_output or {}
    usage = llm_output.get("token_usage", {})
    if usage.get("total_tokens", 0) > 0:
        return {
            "input_tokens": usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0) or usage.get("completion_tokens", 0),
            "total_tokens": usage["total_tokens"],
        }

    if response.generations:
        for gen_list in response.generations:
            for gen in gen_list:
                info = getattr(gen, "generation_info", {}) or {}
                u = info.get("token_usage", {}) or info.get("usage", {})
                if u.get("total_tokens", 0) > 0:
                    return {
                        "input_tokens": u.get("input_tokens", 0) or u.get("prompt_tokens", 0),
                        "output_tokens": u.get("output_tokens", 0) or u.get("completion_tokens", 0),
                        "total_tokens": u["total_tokens"],
                    }
    return None
