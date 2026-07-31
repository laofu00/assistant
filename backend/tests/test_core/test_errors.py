"""core/errors.py LLM 错误分类器测试"""

import pytest

from src.core.errors import classify
from src.core.exceptions import (
    LLMContentFilterError,
    LLMRateLimitError,
    LLMServiceError,
    LLMTimeoutError,
    LLMUnavailableError,
)


class TestClassify:
    def test_none_exception(self) -> None:
        result = classify(None)  # type: ignore[arg-type]
        assert isinstance(result, LLMServiceError)
        assert result.code == "LLM_SERVICE_ERROR"

    def test_timeout_patterns(self) -> None:
        """各种 timeout 关键词应匹配 LLMTimeoutError"""
        cases = [
            Exception("Request timeout"),
            Exception("read timed out"),
            Exception("connection timeout"),
            Exception("504 Gateway Timeout"),
        ]
        for exc in cases:
            result = classify(exc)
            assert isinstance(result, LLMTimeoutError), f"{exc} 应为 LLMTimeoutError"

    def test_rate_limit_patterns(self) -> None:
        cases = [
            Exception("rate limit exceeded"),
            Exception("too many requests"),
            Exception("429 Too Many Requests"),
            Exception("quota exceeded"),
            Exception("throttled"),
        ]
        for exc in cases:
            result = classify(exc)
            assert isinstance(result, LLMRateLimitError), f"{exc} 应为 LLMRateLimitError"

    def test_content_filter_patterns(self) -> None:
        cases = [
            Exception("content filter triggered"),
            Exception("safety check failed"),
            Exception("blocked by moderation"),
            Exception("inappropriate content"),
            Exception("request refused"),
        ]
        for exc in cases:
            result = classify(exc)
            assert isinstance(result, LLMContentFilterError), f"{exc} 应为 LLMContentFilterError"

    def test_unavailable_patterns(self) -> None:
        cases = [
            Exception("service unavailable"),
            Exception("503 Service Unavailable"),
            Exception("502 Bad Gateway"),
            Exception("no route to host"),
            Exception("network error"),
        ]
        for exc in cases:
            result = classify(exc)
            assert isinstance(result, LLMUnavailableError), f"{exc} 应为 LLMUnavailableError"

    def test_generic_unknown_error(self) -> None:
        """无法匹配的错误应返回通用 LLMServiceError"""
        result = classify(Exception("something weird happened"))
        assert isinstance(result, LLMServiceError)
        assert result.code == "LLM_SERVICE_ERROR"

    def test_empty_message(self) -> None:
        exc = Exception()
        result = classify(exc)
        assert isinstance(result, LLMServiceError)

    def test_chained_exception(self) -> None:
        """顶层消息为空时检查 __cause__ 的消息"""
        cause = Exception("rate limit exceeded")
        exc = Exception("")
        exc.__cause__ = cause
        result = classify(exc)
        assert isinstance(result, LLMRateLimitError)

    def test_pattern_priority(self) -> None:
        """timeout 应优先于其他模式（pattern 列表顺序）"""
        # "timed out" 出现在 rate_limit 前面，应返回 LLMTimeoutError
        exc = Exception("request timed out")
        result = classify(exc)
        assert isinstance(result, LLMTimeoutError)
