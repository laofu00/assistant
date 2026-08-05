"""统一 LLM 工厂 — contextvars 驱动，自动注入 Token 回调

所有 Agent 通过 get_llm() 获取 LLM 实例，无需手动管理回调。
请求入口设置 trace_ctx，后续所有 LLM 调用自动捕获 token。
"""

import contextvars
from typing import Any

from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import LLMResult
from loguru import logger

from src.core.config import settings

# ==================== 请求级追踪上下文 ====================

# ContextVar 默认值用 None，运行时通过 set() 赋值
_trace_ctx: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "trace_ctx", default=None
)


def set_trace_context(
    trace_id: str = "",
    session_id: str = "",
    user_id: str = "",
    intent_type: str = "",
    call_purpose: str = "",
    tool_chain: list[dict] | None = None,
) -> None:
    """设置当前请求的追踪上下文（在 chat 入口调用）"""
    _trace_ctx.set({
        "trace_id": trace_id,
        "session_id": session_id,
        "user_id": user_id,
        "intent_type": intent_type,
        "call_purpose": call_purpose,
        "tool_chain": tool_chain or [],
    })


def update_trace_context(**kwargs: Any) -> None:
    """局部更新追踪上下文（如切换 intent_type）"""
    ctx = (_trace_ctx.get() or {}).copy()
    ctx.update(kwargs)
    _trace_ctx.set(ctx)


# ==================== 统一 Token 回调 ====================


class _TokenCallback(BaseCallbackHandler):
    """LangChain 回调 — 从 contextvars 读取上下文，与 get_llm() 绑定"""

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        ctx = _trace_ctx.get()
        if ctx is None or not ctx.get("trace_id"):
            return

        try:
            usage = _extract_usage(response)
            if not usage:
                return

            tool_chain = ctx.get("tool_chain", [])
            tool_called = len(tool_chain) > 0
            tool_names = (
                ",".join(sorted({t.get("tool", "") for t in tool_chain}))
                if tool_chain else ""
            )

            logger.info(
                f"[Token] input={usage['input_tokens']} output={usage['output_tokens']} "
                f"total={usage['total_tokens']} intent={ctx.get('intent_type', '')} tools={tool_names}"
            )

            from src.token.token_callback import _token_queue

            _token_queue.append({
                "trace_id": ctx["trace_id"],
                "session_id": ctx.get("session_id", ""),
                "user_id": ctx.get("user_id", ""),
                "model_name": settings.MODEL_NAME,
                "input_tokens": usage["input_tokens"],
                "output_tokens": usage["output_tokens"],
                "total_tokens": usage["total_tokens"],
                "intent_type": ctx.get("intent_type") or "UNKNOWN",
                "call_purpose": ctx.get("call_purpose") or "",
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


# ==================== 工厂函数 ====================

# 模块级单例回调，所有 LLM 实例共享
_token_callback = _TokenCallback()
_langfuse_handler = None  # 懒加载，仅当环境变量配置时启用
_langsmith_handler = None  # 懒加载，LangSmith 回调（本地开发用）


def _is_langfuse_configured() -> bool:
    """检查 LangFuse 是否已配置"""
    import os
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"))


def _is_langsmith_configured() -> bool:
    """检查 LangSmith 是否已配置"""
    import os
    return bool(os.environ.get("LANGCHAIN_API_KEY"))


def _get_langfuse_handler():
    """获取 LangFuse 回调处理器（安全懒加载，配置缺失则不启用）"""
    global _langfuse_handler  # noqa: PLW0603
    if _langfuse_handler is not None and _langfuse_handler is not False:
        return _langfuse_handler

    if not _is_langfuse_configured():
        _langfuse_handler = False
        return None

    try:
        from langfuse.langchain import CallbackHandler

        _langfuse_handler = CallbackHandler()
        logger.info("[LangFuse] 链路追踪已启用")
        return _langfuse_handler
    except Exception as e:
        logger.warning(f"[LangFuse] 初始化失败，追踪功能不可用: {e}")
        _langfuse_handler = False
        return None


def _get_langsmith_handler():
    """获取 LangSmith 回调处理器（本地开发用，LangFuse 优先）"""
    global _langsmith_handler  # noqa: PLW0603
    if _langsmith_handler is not None and _langsmith_handler is not False:
        return _langsmith_handler

    # LangFuse 优先：如果已配置 LangFuse，跳过 LangSmith
    if _is_langfuse_configured():
        _langsmith_handler = False
        return None

    if not _is_langsmith_configured():
        _langsmith_handler = False
        return None

    try:
        # 启用 LangChain 原生追踪 + 回调处理器
        import os
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGCHAIN_PROJECT", settings.LANGCHAIN_PROJECT)

        from langsmith import traceable
        logger.info(f"[LangSmith] 链路追踪已启用，项目: {settings.LANGCHAIN_PROJECT}")
        # LangSmith 通过环境变量自动注入，不需要额外 callback
        _langsmith_handler = True  # 标记已启用
    except Exception as e:
        logger.warning(f"[LangSmith] 初始化失败: {e}")
        _langsmith_handler = False

    return _langsmith_handler if _langsmith_handler is True else None


def setup_tracing():
    """初始化链路追踪（应用启动时调用一次）"""
    import os
    # LangFuse 优先：将 config 中的值注入环境变量
    if settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY:
        os.environ["LANGFUSE_PUBLIC_KEY"] = settings.LANGFUSE_PUBLIC_KEY
        os.environ["LANGFUSE_SECRET_KEY"] = settings.LANGFUSE_SECRET_KEY
        if settings.LANGFUSE_HOST:
            os.environ.setdefault("LANGFUSE_HOST", settings.LANGFUSE_HOST)
        # 确保 langsmith 不会也被激活
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        _get_langfuse_handler()
    elif settings.LANGCHAIN_API_KEY:
        os.environ.setdefault("LANGCHAIN_API_KEY", settings.LANGCHAIN_API_KEY)
        _get_langsmith_handler()
    else:
        # 显式禁用所有追踪，防止环境变量残留导致 langsmith 自动激活
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        logger.debug("[Tracing] 未配置链路追踪，已显式禁用 LangSmith")


def get_llm(
    temperature: float = 0.3,
    streaming: bool = True,
    model: str | None = None,
) -> BaseChatModel:
    """获取已配置 Token 回调 + LangFuse 追踪的 LLM 实例

    所有 Agent 必须通过此函数获取 LLM，确保 token 统计不遗漏。
    """
    llm = ChatTongyi(
        model=model or settings.MODEL_NAME,
        dashscope_api_key=settings.OPENAI_API_KEY,
        temperature=temperature,
        streaming=streaming,
    )
    # 回调链: [TokenCapture, LangFuse(可选)]
    callbacks = [_token_callback]
    lf = _get_langfuse_handler()
    if lf is not None:
        callbacks.append(lf)
    llm.callbacks = callbacks
    return llm
