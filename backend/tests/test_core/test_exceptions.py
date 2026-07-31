"""core/exceptions.py 异常体系测试"""

import pytest

from src.core.exceptions import (
    AppException,
    CircuitBreakerOpenError,
    ConfigError,
    DatabaseError,
    DeadLetterError,
    KnowledgeNotFoundError,
    LLMContentFilterError,
    LLMRateLimitError,
    LLMServiceError,
    LLMTimeoutError,
    LLMUnavailableError,
    RateLimitExceededError,
    RetryExhaustedError,
    TokenQuotaExceededError,
    ToolTimeoutError,
    ValidationError,
)


class TestAppException:
    def test_default_values(self) -> None:
        e = AppException()
        assert e.message == "应用内部错误"
        assert e.code == "APP_ERROR"
        assert str(e) == "应用内部错误"

    def test_custom_message(self) -> None:
        e = AppException(message="自定义错误")
        assert e.message == "自定义错误"
        assert e.code == "APP_ERROR"

    def test_custom_code(self) -> None:
        e = AppException("错误", code="CUSTOM_ERR")
        assert e.code == "CUSTOM_ERR"


class TestConfigError:
    def test_default(self) -> None:
        e = ConfigError()
        assert e.code == "CONFIG_ERROR"
        assert isinstance(e, AppException)

    def test_custom_message(self) -> None:
        e = ConfigError("缺少 OPENAI_API_KEY")
        assert "OPENAI_API_KEY" in e.message


class TestToolExceptions:
    def test_timeout_with_name(self) -> None:
        e = ToolTimeoutError("search_knowledge", 15)
        assert "search_knowledge" in e.message
        assert "15秒" in e.message
        assert e.code == "TOOL_TIMEOUT"

    def test_timeout_default(self) -> None:
        e = ToolTimeoutError()
        assert e.message == "工具调用超时"

    def test_retry_exhausted(self) -> None:
        e = RetryExhaustedError("send_email", 3)
        assert "send_email" in e.message
        assert "3 次" in e.message
        assert e.code == "RETRY_EXHAUSTED"

    def test_circuit_breaker_open(self) -> None:
        e = CircuitBreakerOpenError("search_knowledge")
        assert "search_knowledge" in e.message
        assert "熔断" in e.message
        assert e.code == "CIRCUIT_BREAKER_OPEN"


class TestKnowledgeNotFoundError:
    def test_default(self) -> None:
        e = KnowledgeNotFoundError()
        assert e.code == "KNOWLEDGE_NOT_FOUND"

    def test_with_filename_and_user(self) -> None:
        e = KnowledgeNotFoundError(filename="test.pdf", user_id="user123")
        assert "test.pdf" in e.message
        assert "user123" in e.message


class TestLLMErrors:
    def test_base(self) -> None:
        e = LLMServiceError()
        assert e.code == "LLM_SERVICE_ERROR"

    def test_timeout(self) -> None:
        e = LLMTimeoutError()
        assert e.code == "LLM_TIMEOUT"
        assert isinstance(e, LLMServiceError)

    def test_rate_limit(self) -> None:
        e = LLMRateLimitError()
        assert e.code == "LLM_RATE_LIMITED"

    def test_unavailable(self) -> None:
        e = LLMUnavailableError()
        assert e.code == "LLM_UNAVAILABLE"

    def test_content_filter(self) -> None:
        e = LLMContentFilterError()
        assert e.code == "LLM_CONTENT_FILTERED"


class TestTokenQuotaExceededError:
    def test_default(self) -> None:
        e = TokenQuotaExceededError()
        assert e.code == "TOKEN_QUOTA_EXCEEDED"

    def test_with_user_and_limit(self) -> None:
        e = TokenQuotaExceededError("user123", 500000)
        assert "user123" in e.message
        assert "500,000" in e.message


class TestRateLimitExceededError:
    def test_default(self) -> None:
        e = RateLimitExceededError()
        assert e.code == "RATE_LIMIT_EXCEEDED"
        assert "过于频繁" in e.message


class TestDeadLetterError:
    def test_default(self) -> None:
        e = DeadLetterError()
        assert e.code == "DEAD_LETTER"


class TestDatabaseError:
    def test_default(self) -> None:
        e = DatabaseError()
        assert e.code == "DATABASE_ERROR"


class TestExceptionHierarchy:
    """验证异常继承结构"""

    def test_all_app_exceptions(self) -> None:
        exceptions = [
            ConfigError(),
            ToolTimeoutError(),
            RetryExhaustedError(),
            CircuitBreakerOpenError(),
            KnowledgeNotFoundError(),
            TokenQuotaExceededError(),
            RateLimitExceededError(),
            DeadLetterError(),
            LLMServiceError(),
            LLMTimeoutError(),
            LLMRateLimitError(),
            LLMUnavailableError(),
            LLMContentFilterError(),
            DatabaseError(),
        ]
        for e in exceptions:
            assert isinstance(e, AppException), f"{type(e).__name__} 应该是 AppException 子类"

    def test_llm_error_hierarchy(self) -> None:
        llm_errors = [LLMTimeoutError(), LLMRateLimitError(), LLMUnavailableError(), LLMContentFilterError()]
        for e in llm_errors:
            assert isinstance(e, LLMServiceError), f"{type(e).__name__} 应该是 LLMServiceError 子类"
