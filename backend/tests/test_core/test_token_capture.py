"""token/capture.py Token捕获服务测试"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.token.capture import _infer_provider, capture_tokens


class TestInferProvider:
    def test_dashscope_qwen(self) -> None:
        assert _infer_provider("qwen-plus") == "dashscope"
        assert _infer_provider("qwen-turbo") == "dashscope"

    def test_dashscope_embedding(self) -> None:
        assert _infer_provider("text-embedding-v3") == "dashscope"

    def test_dashscope_rerank(self) -> None:
        assert _infer_provider("gte-rerank") == "dashscope"

    def test_dashscope_tongyi(self) -> None:
        assert _infer_provider("tongyi") == "dashscope"

    def test_openai(self) -> None:
        assert _infer_provider("gpt-4o") == "openai"
        assert _infer_provider("gpt-4o-mini") == "openai"

    def test_anthropic(self) -> None:
        assert _infer_provider("claude-3.5-sonnet") == "anthropic"

    def test_ollama(self) -> None:
        assert _infer_provider("deepseek-r1:8b") == "ollama"
        assert _infer_provider("llama3.2") == "ollama"
        assert _infer_provider("mistral") == "ollama"

    def test_unknown(self) -> None:
        assert _infer_provider("some-random-model") == "unknown"

    def test_none(self) -> None:
        assert _infer_provider(None) == "unknown"


class TestCaptureTokens:
    async def test_capture_success(self) -> None:
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        with patch("src.token.capture.async_session_factory", mock_sf):
            await capture_tokens(
                trace_id="trace_1", session_id="sess_1", user_id="user_1",
                model_name="qwen-plus", input_tokens=100, output_tokens=50,
            )
            mock_session.add.assert_called_once()
            mock_session.commit.assert_awaited_once()

    async def test_capture_zero_tokens_skipped(self) -> None:
        mock_sf = MagicMock()
        with patch("src.token.capture.async_session_factory", mock_sf):
            await capture_tokens(
                trace_id="t", session_id="s", user_id="u",
                model_name="qwen-plus", input_tokens=0, output_tokens=0,
            )
            mock_sf.assert_not_called()

    async def test_capture_db_failure_sends_to_dead_letter(self) -> None:
        mock_session = MagicMock()
        mock_session.commit = AsyncMock(side_effect=Exception("DB down"))
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session
        mock_dl = MagicMock()
        mock_dl.save = AsyncMock()

        with (
            patch("src.token.capture.async_session_factory", mock_sf),
            patch("src.token.capture.dead_letter", mock_dl),
        ):
            await capture_tokens(
                trace_id="t", session_id="s", user_id="u",
                model_name="qwen-plus", input_tokens=100, output_tokens=50,
            )
            mock_dl.save.assert_awaited_once()

    async def test_tool_called_field(self) -> None:
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        with patch("src.token.capture.async_session_factory", mock_sf):
            await capture_tokens(
                trace_id="t", session_id="s", user_id="u",
                model_name="qwen-plus", input_tokens=100, output_tokens=50,
                tool_called=True, tool_names="list_memos", tool_input="{}", tool_output="3条",
            )
            mock_session.add.assert_called_once()
            record = mock_session.add.call_args[0][0]
            assert record.tool_called == 1
            assert record.tool_names == "list_memos"

    async def test_total_tokens_auto_calculated(self) -> None:
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        with patch("src.token.capture.async_session_factory", mock_sf):
            await capture_tokens(
                trace_id="t", session_id="s", user_id="u",
                model_name="qwen-plus", input_tokens=200, output_tokens=300,
            )
            record = mock_session.add.call_args[0][0]
            assert record.total_tokens == 500

    async def test_input_output_truncated(self) -> None:
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        with patch("src.token.capture.async_session_factory", mock_sf):
            await capture_tokens(
                trace_id="t", session_id="s", user_id="u",
                model_name="qwen-plus", input_tokens=100, output_tokens=50,
                tool_input="x" * 600, tool_output="y" * 600, query_text="z" * 600,
            )
            record = mock_session.add.call_args[0][0]
            assert len(record.tool_input) <= 500
            assert len(record.query_text) <= 500
