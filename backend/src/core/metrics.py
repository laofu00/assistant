"""Prometheus 指标定义 — 工具调用可观测性

暴露端点: GET /metrics（prometheus_client 自动处理）
"""

from prometheus_client import Counter, Gauge, Histogram, generate_latest

# ==================== 工具调用 ====================

tool_calls_total = Counter(
    "assistant_tool_calls_total",
    "工具调用总量",
    ["tool_name", "category", "permission", "result"],
)

tool_call_duration_seconds = Histogram(
    "assistant_tool_call_duration_seconds",
    "工具调用耗时分布（秒）",
    ["tool_name"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 15.0],
)

tool_active_calls = Gauge(
    "assistant_tool_active_calls",
    "当前活跃工具调用数",
    ["tool_name"],
)

# ==================== 限流 ====================

tool_rate_limit_hits_total = Counter(
    "assistant_tool_rate_limit_hits_total",
    "限流命中次数",
    ["tool_name", "layer"],  # layer: user_tool / global_tool / user_total
)

# ==================== 健康检查 ====================

tool_health_status = Gauge(
    "assistant_tool_health_status",
    "工具依赖健康状态（1=健康 0=不健康）",
    ["tool_name", "dependency"],
)

# ==================== 熔断 ====================

tool_circuit_breaker_state = Gauge(
    "assistant_tool_circuit_breaker_state",
    "熔断器状态（1=打开 0=关闭）",
    ["tool_name"],
)

# ==================== 审计 ====================

tool_audit_queue_size = Gauge(
    "assistant_tool_audit_queue_size",
    "审计日志队列待写入数量",
)


def get_metrics() -> bytes:
    """生成 Prometheus 文本格式指标（供 /metrics 端点使用）"""
    return generate_latest()
