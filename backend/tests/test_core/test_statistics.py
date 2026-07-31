"""token/statistics.py 统计查询服务测试"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.token.statistics import StatisticsService, statistics_service


class TestStatisticsService:
    @pytest.fixture
    def svc(self) -> StatisticsService:
        return StatisticsService()

    async def test_query_records_empty(self, svc: StatisticsService) -> None:
        mock_session = MagicMock()
        mock_session.execute = AsyncMock()
        mock_session.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=0)),  # count
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),  # records
        ]
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        with patch("src.token.statistics.async_session_factory", mock_sf):
            result = await svc.query_records("user_x")
            assert result["total"] == 0
            assert result["records"] == []

    async def test_query_records_with_data(self, svc: StatisticsService) -> None:
        mock_records = [
            MagicMock(id=1, trace_id="t1", total_tokens=100, model_name="qwen-plus"),
            MagicMock(id=2, trace_id="t2", total_tokens=200, model_name="qwen-turbo"),
        ]
        mock_session = MagicMock()
        mock_session.execute = AsyncMock()
        mock_session.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=2)),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=mock_records)))),
        ]
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        with patch("src.token.statistics.async_session_factory", mock_sf):
            result = await svc.query_records("user_x", page=1, size=10)
            assert result["total"] == 2
            assert len(result["records"]) == 2

    async def test_query_with_time_range(self, svc: StatisticsService) -> None:
        mock_session = MagicMock()
        mock_session.execute = AsyncMock()
        mock_session.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=1)),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[MagicMock()])))),
        ]
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 12, 31, tzinfo=timezone.utc)
        with patch("src.token.statistics.async_session_factory", mock_sf):
            result = await svc.query_records("user_x", start_time=start, end_time=end)
            assert result["total"] == 1

    async def test_get_statistics(self, svc: StatisticsService) -> None:
        mock_session = MagicMock()
        # [input, output, total, cost, count, tool_called]
        mock_session.execute = AsyncMock(
            return_value=MagicMock(one_or_none=MagicMock(return_value=[1000, 500, 1500, 0.05, 10, 3]))
        )
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        with patch("src.token.statistics.async_session_factory", mock_sf):
            result = await svc.get_statistics("user_x")
            assert result["total_tokens"] == 1500
            assert result["total_cost"] == 0.05
            assert result["request_count"] == 10
            assert result["tool_call_count"] == 3
            assert result["avg_tokens_per_request"] == 150.0

    async def test_get_statistics_empty(self, svc: StatisticsService) -> None:
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(one_or_none=MagicMock(return_value=None)))
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        with patch("src.token.statistics.async_session_factory", mock_sf):
            result = await svc.get_statistics("user_x")
            assert result["total_tokens"] == 0

    async def test_get_by_model(self, svc: StatisticsService) -> None:
        rows = [
            ("qwen-plus", 5, 1000, 0.05),
            ("qwen-turbo", 3, 300, 0.01),
        ]
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(
            return_value=MagicMock(all=MagicMock(return_value=rows))
        )
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        with patch("src.token.statistics.async_session_factory", mock_sf):
            result = await svc.get_by_model("user_x")
            assert len(result) == 2
            assert result[0]["model"] == "qwen-plus"
            assert result[0]["total_tokens"] == 1000

    async def test_get_by_date(self, svc: StatisticsService) -> None:
        rows = [("2025-03-15", 3, 500, 0.02)]
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(
            return_value=MagicMock(all=MagicMock(return_value=rows))
        )
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        with patch("src.token.statistics.async_session_factory", mock_sf):
            result = await svc.get_by_date("user_x")
            assert len(result) == 1
            assert result[0]["date"] == "2025-03-15"

    async def test_get_today_usage(self, svc: StatisticsService) -> None:
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(
            return_value=MagicMock(one_or_none=MagicMock(return_value=[3000, 0.12, 8]))
        )
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        with patch("src.token.statistics.async_session_factory", mock_sf):
            result = await svc.get_today_usage("user_x")
            assert result["today_tokens"] == 3000
            assert result["today_cost"] == 0.12
            assert result["request_count"] == 8

    def test_global_instance(self) -> None:
        assert isinstance(statistics_service, StatisticsService)
