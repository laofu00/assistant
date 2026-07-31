"""core/llm_factory.py LLM工厂 + Token回调测试"""

import contextvars
from unittest.mock import MagicMock, patch

from langchain_core.outputs import LLMResult


class TestTraceContext:
    def test_set_and_get(self) -> None:
        from src.core.llm_factory import _trace_ctx, set_trace_context

        set_trace_context(trace_id="trace_1", session_id="sess_1", user_id="user_1")
        ctx = _trace_ctx.get()
        assert ctx is not None
        assert ctx["trace_id"] == "trace_1"
        assert ctx["user_id"] == "user_1"

    def test_update_context(self) -> None:
        from src.core.llm_factory import _trace_ctx, update_trace_context

        from src.core.llm_factory import set_trace_context
        set_trace_context(trace_id="t1", user_id="u1")

        update_trace_context(intent_type="REACT_AGENT", call_purpose="agent_think")
        ctx = _trace_ctx.get()
        assert ctx["intent_type"] == "REACT_AGENT"
        assert ctx["trace_id"] == "t1"  # 保留原有值

    def test_default_none(self) -> None:
        from src.core.llm_factory import _trace_ctx

        # 重置 ContextVar
        token = _trace_ctx.set(None)
        try:
            assert _trace_ctx.get() is None
        finally:
            _trace_ctx.reset(token)


class TestExtractUsage:
    def test_from_llm_output(self) -> None:
        from src.core.llm_factory import _extract_usage

        result = LLMResult(
            generations=[],
            llm_output={"token_usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}},
        )
        usage = _extract_usage(result)
        assert usage == {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}

    def test_from_generation_info(self) -> None:
        from src.core.llm_factory import _extract_usage

        from langchain_core.outputs import ChatGeneration, Generation

        gen = Generation(text="test")
        gen.generation_info = {"token_usage": {"input_tokens": 200, "output_tokens": 100, "total_tokens": 300}}
        result = LLMResult(generations=[[gen]], llm_output={})
        usage = _extract_usage(result)
        assert usage["total_tokens"] == 300

    def test_no_usage_returns_none(self) -> None:
        from src.core.llm_factory import _extract_usage

        result = LLMResult(generations=[], llm_output={})
        assert _extract_usage(result) is None

    def test_zero_tokens_skipped(self) -> None:
        from src.core.llm_factory import _extract_usage

        result = LLMResult(
            generations=[],
            llm_output={"token_usage": {"total_tokens": 0}},
        )
        assert _extract_usage(result) is None

    def test_prompt_tokens_alias(self) -> None:
        """prompt_tokens 作为 input_tokens 的别名"""
        from src.core.llm_factory import _extract_usage

        result = LLMResult(
            generations=[],
            llm_output={"token_usage": {"prompt_tokens": 80, "completion_tokens": 40, "total_tokens": 120}},
        )
        usage = _extract_usage(result)
        assert usage["input_tokens"] == 80
        assert usage["output_tokens"] == 40


class TestTokenCallback:
    def test_on_llm_end_no_context(self) -> None:
        from src.core.llm_factory import _TokenCallback, _trace_ctx

        cb = _TokenCallback()
        _trace_ctx.set(None)
        # 无上下文时不记录
        cb.on_llm_end(LLMResult(generations=[], llm_output={}))

    def test_on_llm_end_with_context(self) -> None:
        from src.core.llm_factory import _TokenCallback, set_trace_context

        set_trace_context(trace_id="t1", session_id="s1", user_id="u1", intent_type="GENERAL")

        mock_queue = MagicMock()
        cb = _TokenCallback()
        result = LLMResult(
            generations=[],
            llm_output={"token_usage": {"input_tokens": 50, "output_tokens": 25, "total_tokens": 75}},
        )

        with patch("src.token.token_callback._token_queue", mock_queue):
            cb.on_llm_end(result)

        mock_queue.append.assert_called_once()
        record = mock_queue.append.call_args[0][0]
        assert record["total_tokens"] == 75
        assert record["trace_id"] == "t1"

    def test_on_llm_end_no_trace_id(self) -> None:
        """trace_id 为空时不记录"""
        from src.core.llm_factory import _TokenCallback, set_trace_context

        set_trace_context(trace_id="", user_id="u1")
        mock_queue = MagicMock()
        cb = _TokenCallback()

        with patch("src.token.token_callback._token_queue", mock_queue):
            cb.on_llm_end(LLMResult(generations=[], llm_output={}))

        mock_queue.append.assert_not_called()


class TestGetLLM:
    def test_returns_chat_model(self) -> None:
        from src.core.llm_factory import get_llm
        llm = get_llm(temperature=0, streaming=False)
        assert hasattr(llm, "invoke") or hasattr(llm, "ainvoke")

    def test_custom_model(self) -> None:
        from src.core.llm_factory import get_llm
        llm = get_llm(temperature=0, streaming=False, model="qwen-turbo")
        assert llm is not None

    def test_has_callbacks(self) -> None:
        from src.core.llm_factory import get_llm
        llm = get_llm(temperature=0, streaming=False)
        assert hasattr(llm, "callbacks")
        assert len(llm.callbacks) >= 1


class TestLangFuseHandler:
    def test_not_configured_returns_none(self, monkeypatch) -> None:
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        from src.core.llm_factory import _get_langfuse_handler
        from src.core.llm_factory import _langfuse_handler as lfh

        # 重置模块级变量
        import src.core.llm_factory as lf
        lf._langfuse_handler = None

        result = _get_langfuse_handler()
        assert result is None

    def test_already_checked(self) -> None:
        import src.core.llm_factory as lf
        saved = lf._langfuse_handler
        lf._langfuse_handler = False
        try:
            # 已标记为 False 时直接返回 False（不重复检查环境变量）
            result = lf._get_langfuse_handler()
            assert result is False
        finally:
            lf._langfuse_handler = saved
