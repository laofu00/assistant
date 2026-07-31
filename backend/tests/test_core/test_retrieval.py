"""knowledge/retrieval.py 检索流水线测试"""

from unittest.mock import MagicMock, patch

import pytest

from src.knowledge.retrieval import _is_simple_query, _tokenize


class TestIsSimpleQuery:
    def test_short_keyword_query(self) -> None:
        assert _is_simple_query("Python FastAPI") is True

    def test_short_with_question_mark(self) -> None:
        assert _is_simple_query("Python?") is False

    def test_short_with_help_me(self) -> None:
        assert _is_simple_query("帮我查一下") is False

    def test_long_query(self) -> None:
        assert _is_simple_query("这是一个很长的查询文本超过了20个字符限制") is False

    def test_short_technical_term(self) -> None:
        assert _is_simple_query("FastAPI") is True


class TestTokenize:
    def test_chinese(self) -> None:
        tokens = _tokenize("Python异步编程")
        assert "python" in tokens or "异步" in tokens or "编程" in tokens
        assert len(tokens) > 0

    def test_english_only(self) -> None:
        tokens = _tokenize("Python FastAPI async")
        assert "python" in tokens
        assert "fastapi" in tokens
        assert "async" in tokens

    def test_empty(self) -> None:
        tokens = _tokenize("")
        assert tokens == []

    def test_mixed(self) -> None:
        tokens = _tokenize("使用FastAPI构建API")
        assert len(tokens) > 0


class TestRerankUsageTracking:
    def test_no_context_skips(self) -> None:
        from src.knowledge.retrieval import _track_rerank_usage

        mock_queue = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.get.return_value = {}

        with (
            patch("src.token.token_callback._token_queue", mock_queue),
            patch("src.core.llm_factory._trace_ctx", mock_ctx),
        ):
            _track_rerank_usage(1000, 5)
            mock_queue.append.assert_not_called()

    def test_with_context_tracks(self) -> None:
        from src.knowledge.retrieval import _track_rerank_usage

        mock_queue = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.get.return_value = {"trace_id": "t1", "session_id": "s1", "user_id": "u1"}

        with (
            patch("src.token.token_callback._token_queue", mock_queue),
            patch("src.core.llm_factory._trace_ctx", mock_ctx),
        ):
            _track_rerank_usage(2000, 10)
            mock_queue.append.assert_called_once()
            record = mock_queue.append.call_args[0][0]
            assert record["model_name"] == "gte-rerank"
            assert record["total_tokens"] == 2000
            assert record["intent_type"] == "RERANK"
