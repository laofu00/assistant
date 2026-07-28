"""全局异常类体系（企业级，含 LLM 错误细分）"""


class AppException(Exception):
    """应用基础异常"""

    def __init__(self, message: str = "应用内部错误", code: str = "APP_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


# ==================== 配置与校验 ====================


class ConfigError(AppException):
    """配置错误"""

    def __init__(self, message: str = "配置错误"):
        super().__init__(message, code="CONFIG_ERROR")


class ValidationError(AppException):
    """参数校验异常"""

    def __init__(self, message: str = "参数校验失败"):
        super().__init__(message, code="VALIDATION_ERROR")


# ==================== 工具 ====================


class ToolTimeoutError(AppException):
    """工具调用超时"""

    def __init__(self, tool_name: str = "", timeout: int = 0):
        msg = f"工具 [{tool_name}] 调用超时（{timeout}秒）" if tool_name else "工具调用超时"
        super().__init__(msg, code="TOOL_TIMEOUT")


class RetryExhaustedError(AppException):
    """重试耗尽"""

    def __init__(self, operation: str = "", retries: int = 0):
        msg = f"操作 [{operation}] 重试 {retries} 次后仍失败" if operation else "重试耗尽"
        super().__init__(msg, code="RETRY_EXHAUSTED")


class CircuitBreakerOpenError(AppException):
    """熔断器打开"""

    def __init__(self, tool_name: str = ""):
        msg = f"工具 [{tool_name}] 已熔断，请稍后重试" if tool_name else "服务已熔断，请稍后重试"
        super().__init__(msg, code="CIRCUIT_BREAKER_OPEN")


# ==================== 知识库 ====================


class KnowledgeNotFoundError(AppException):
    """知识库文档未找到"""

    def __init__(self, filename: str = "", user_id: str = ""):
        msg = f"知识库中未找到文档 [{filename}]" if filename else "知识库文档未找到"
        if user_id:
            msg += f"（用户: {user_id}）"
        super().__init__(msg, code="KNOWLEDGE_NOT_FOUND")


# ==================== Token / 配额 ====================


class TokenQuotaExceededError(AppException):
    """Token 配额超限"""

    def __init__(self, user_id: str = "", daily_limit: int = 0):
        msg = f"用户 [{user_id}] 今日 Token 用量已达上限" if user_id else "Token 配额超限"
        if daily_limit:
            msg += f"（{daily_limit:,} tokens）"
        super().__init__(msg, code="TOKEN_QUOTA_EXCEEDED")


# ==================== 限流 ====================


class RateLimitExceededError(AppException):
    """API 限流"""

    def __init__(self, message: str = "请求过于频繁，请稍后重试"):
        super().__init__(message, code="RATE_LIMIT_EXCEEDED")


# ==================== 死信 ====================


class DeadLetterError(AppException):
    """死信队列异常"""

    def __init__(self, message: str = "消息写入死信队列"):
        super().__init__(message, code="DEAD_LETTER")


# ==================== LLM 服务 ====================


class LLMServiceError(AppException):
    """LLM 服务基类异常 — 9004"""

    def __init__(self, message: str = "LLM 服务异常"):
        super().__init__(message, code="LLM_SERVICE_ERROR")


class LLMTimeoutError(LLMServiceError):
    """LLM 调用超时 — 9005"""

    def __init__(self, message: str = "LLM 调用超时"):
        super().__init__(message)
        self.code = "LLM_TIMEOUT"


class LLMRateLimitError(LLMServiceError):
    """LLM 限流 — 9006"""

    def __init__(self, message: str = "LLM 调用频率超限"):
        super().__init__(message)
        self.code = "LLM_RATE_LIMITED"


class LLMUnavailableError(LLMServiceError):
    """LLM 服务不可用 — 9007"""

    def __init__(self, message: str = "LLM 服务暂不可用"):
        super().__init__(message)
        self.code = "LLM_UNAVAILABLE"


class LLMContentFilterError(LLMServiceError):
    """LLM 内容过滤 — 9008"""

    def __init__(self, message: str = "LLM 内容被安全过滤"):
        super().__init__(message)
        self.code = "LLM_CONTENT_FILTERED"


# ==================== 数据库 ====================


class DatabaseError(AppException):
    """数据库异常"""

    def __init__(self, message: str = "数据库操作异常"):
        super().__init__(message, code="DATABASE_ERROR")
