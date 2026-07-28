"""LLM 错误分类器 — 根据异常消息关键词识别具体错误类型"""

import re
from src.core.exceptions import (
    LLMContentFilterError,
    LLMRateLimitError,
    LLMServiceError,
    LLMTimeoutError,
    LLMUnavailableError,
)

# 按优先级排列的匹配规则
_PATTERNS: list[tuple[str, type[LLMServiceError]]] = [
    (r"timeout|timed.out|read.timeout|connect.timeout|504", LLMTimeoutError),
    (r"rate.?limit|too.many.requests|429|throttl|quota.exceeded", LLMRateLimitError),
    (r"content.?filter|safety|blocked|inappropriate|refused|rejected", LLMContentFilterError),
    (r"unavailable|service.unavailable|503|bad.gateway|502|downstream", LLMUnavailableError),
    (r"connection.refused|unknown.host|no.route.to.host|network", LLMUnavailableError),
]


def classify(exception: Exception) -> LLMServiceError:
    """根据异常消息分类为具体的 LLM 错误类型。无法识别时返回通用 LLMServiceError。"""
    if exception is None:
        return LLMServiceError("未知 LLM 错误")

    msg = str(exception).lower()
    if not msg and exception.__cause__:
        msg = str(exception.__cause__).lower()
    if not msg:
        return LLMServiceError(str(exception))

    for pattern, error_cls in _PATTERNS:
        if re.search(pattern, msg):
            return error_cls(str(exception))

    return LLMServiceError(str(exception))
