"""带 Token 追踪的 EmbeddingFunction — ChromaDB 兼容接口

替换 chromadb.utils.embedding_functions.OpenAIEmbeddingFunction，
在调用 OpenAI 兼容 embeddings API 时自动捕获 token 用量。
"""

from __future__ import annotations

from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from loguru import logger
from openai import OpenAI

from src.core.config import settings


class TrackedEmbeddingFunction(EmbeddingFunction[Documents]):
    """OpenAI 兼容嵌入函数，自动追踪 token 用量并写入统一队列"""

    def __init__(self) -> None:
        self._client = OpenAI(
            api_key=settings.OPENAI_API_KEY or "sk-placeholder",
            base_url=settings.OPENAI_BASE_URL,
        )
        self._model = settings.EMBEDDING_MODEL

    def __call__(self, input: Documents) -> Embeddings:
        # 调用 OpenAI embeddings API，获取完整响应（含 usage）
        response = self._client.embeddings.create(
            input=input,
            model=self._model,
        )

        total_tokens = getattr(response.usage, "total_tokens", 0)
        if total_tokens > 0:
            self._track_usage(
                input_texts=input,
                total_tokens=total_tokens,
            )

        # 按输入顺序返回 embedding 列表
        return [d.embedding for d in response.data]

    def _track_usage(self, input_texts: list[str], total_tokens: int) -> None:
        """将嵌入 token 用量写入统一统计队列"""
        try:
            from src.core.llm_factory import _trace_ctx

            ctx = _trace_ctx.get()
            if ctx is None or not ctx.get("trace_id"):
                logger.debug(f"[Embedding] 无追踪上下文，跳过写入: tokens={total_tokens}")
                return

            from src.token.token_callback import _token_queue

            _token_queue.append({
                "trace_id": ctx["trace_id"],
                "session_id": ctx.get("session_id", ""),
                "user_id": ctx.get("user_id", ""),
                "model_name": self._model,
                "input_tokens": total_tokens,
                "output_tokens": 0,
                "total_tokens": total_tokens,
                "intent_type": "EMBEDDING",
                "call_purpose": f"embed_{len(input_texts)}_texts",
                "tool_called": False,
                "tool_names": "",
            })
            logger.debug(f"[Embedding] tokens={total_tokens}, texts={len(input_texts)}")
        except Exception as e:
            logger.warning(f"[Embedding] Token 追踪异常: {e}")
