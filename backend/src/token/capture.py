"""Token 捕获服务 — 同步 + 流式 chunk 聚合

对齐 Java 版 TokenCaptureService：captureSyncCall / captureStreamCall
"""

from datetime import datetime, timezone
from typing import Any

from loguru import logger

from src.core.config import settings
from src.core.database import async_session_factory
from src.models.token_usage import TokenUsage
from src.token.cost import CostCalculator, cost_calculator
from src.token.dead_letter import dead_letter


def _infer_provider(model_name: str | None) -> str:
    """从模型名称推断提供商"""
    if not model_name:
        return "unknown"
    lower = model_name.lower()
    if any(k in lower for k in ("qwen", "dashscope", "tongyi")):
        return "dashscope"
    if "gpt" in lower or "openai" in lower:
        return "openai"
    if "claude" in lower:
        return "anthropic"
    if any(k in lower for k in ("llama", "mistral", "deepseek")):
        return "ollama"
    return "unknown"


async def capture_tokens(
    *,
    trace_id: str,
    session_id: str,
    user_id: str,
    model_name: str | None,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int | None = None,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
    intent_type: str = "REACT_AGENT",
    call_purpose: str = "",
    tool_called: bool = False,
    tool_names: str = "",
    tool_input: str = "",
    tool_output: str = "",
    tool_duration_ms: int | None = None,
    query_text: str = "",
    response_length: int = 0,
) -> None:
    """捕获并持久化 Token 使用记录"""
    total = total_tokens or (input_tokens + output_tokens)
    if total == 0:
        return

    provider = _infer_provider(model_name)
    cost = cost_calculator.calculate(provider, model_name or "", input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens)

    record = TokenUsage(
        trace_id=trace_id,
        session_id=session_id,
        user_id=user_id,
        provider=provider,
        model_name=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total,
        cache_creation_tokens=cache_creation_tokens,
        cache_read_tokens=cache_read_tokens,
        cost_amount=float(cost),
        intent_type=intent_type,
        call_purpose=call_purpose,
        tool_called=1 if tool_called else 0,
        tool_names=tool_names,
        tool_input=tool_input[:500] if tool_input else "",
        tool_output=tool_output[:500] if tool_output else "",
        tool_duration_ms=tool_duration_ms,
        query_text=query_text[:500] if query_text else "",
        response_length=response_length,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )

    try:
        async with async_session_factory() as session:
            session.add(record)
            await session.commit()
        logger.debug(f"Token 记录写入: trace_id={trace_id}, model={model_name}, tokens={total}, cost={cost}")
    except Exception as e:
        logger.error(f"Token 记录写入失败，转入死信队列: {e}")
        try:
            await dead_letter.save({
                "trace_id": trace_id,
                "user_id": user_id,
                "provider": provider,
                "model_name": model_name,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total,
                "cost_amount": float(cost),
                "intent_type": intent_type,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as dl_e:
            logger.error(f"死信队列写入也失败: {dl_e}")


def aggregate_stream_usage(chunks: list[Any]) -> dict[str, int]:
    """从流式 chunks 中聚合 Token 用量

    Args:
        chunks: langchain AIMessageChunk 列表

    Returns:
        {"input_tokens": N, "output_tokens": N, "total_tokens": N}
    """
    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for chunk in reversed(chunks):
        meta = getattr(chunk, "response_metadata", {}) or {}
        token_usage = meta.get("token_usage", {}) or meta.get("usage", {}) or {}
        if token_usage:
            usage["input_tokens"] = max(usage["input_tokens"], token_usage.get("prompt_tokens", 0) or token_usage.get("input_tokens", 0))
            usage["output_tokens"] = max(usage["output_tokens"], token_usage.get("completion_tokens", 0) or token_usage.get("output_tokens", 0))
            usage["total_tokens"] = max(usage["total_tokens"], token_usage.get("total_tokens", 0))
            if usage["total_tokens"] > 0:
                break
    return usage
