"""token/quota.py 配额检查器测试"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.token.quota import QuotaChecker, quota_checker


class TestQuotaChecker:
    @pytest.fixture
    def checker(self) -> QuotaChecker:
        return QuotaChecker()

    async def test_get_today_usage(self, checker: QuotaChecker) -> None:
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(one_or_none=MagicMock(return_value=[500, 0.05, 3])))
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        with patch("src.token.quota.async_session_factory", mock_sf):
            usage = await checker.get_today_usage("user_x")
            assert usage["tokens"] == 500
            assert usage["cost"] == 0.05
            assert usage["requests"] == 3

    async def test_get_today_usage_none(self, checker: QuotaChecker) -> None:
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(one_or_none=MagicMock(return_value=None)))
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        with patch("src.token.quota.async_session_factory", mock_sf):
            usage = await checker.get_today_usage("user_x")
            assert usage["tokens"] == 0
            assert usage["cost"] == 0.0

    async def test_check_quota_pass(self, checker: QuotaChecker) -> None:
        with patch.object(checker, "get_today_usage", return_value={"tokens": 100, "cost": 1.0, "requests": 2}):
            await checker.check_quota("user_x")  # 不抛异常

    async def test_check_quota_token_exceeded(self, checker: QuotaChecker, monkeypatch) -> None:
        monkeypatch.setattr("src.token.quota.settings.TOKEN_DAILY_LIMIT", 100)
        with patch.object(checker, "get_today_usage", return_value={"tokens": 100, "cost": 0, "requests": 1}):
            with pytest.raises(Exception):  # TokenQuotaExceededError
                await checker.check_quota("user_x")

    async def test_check_quota_cost_exceeded(self, checker: QuotaChecker, monkeypatch) -> None:
        monkeypatch.setattr("src.token.quota.settings.TOKEN_DAILY_COST_LIMIT", 5.0)
        with patch.object(checker, "get_today_usage", return_value={"tokens": 10, "cost": 5.0, "requests": 1}):
            with pytest.raises(Exception):
                await checker.check_quota("user_x")

    async def test_check_quota_alert_threshold(self, checker: QuotaChecker, monkeypatch) -> None:
        monkeypatch.setattr("src.token.quota.settings.TOKEN_DAILY_LIMIT", 1000)
        monkeypatch.setattr("src.token.quota.settings.TOKEN_ALERT_THRESHOLD", 0.5)
        monkeypatch.setattr("src.token.quota.settings.TOKEN_ALERT_WEBHOOK", "")
        with patch.object(checker, "get_today_usage", return_value={"tokens": 600, "cost": 1.0, "requests": 5}):
            await checker.check_quota("user_x")  # 告警但不抛异常

    async def test_alert_webhook_sent(self, checker: QuotaChecker, monkeypatch) -> None:
        monkeypatch.setattr("src.token.quota.settings.TOKEN_DAILY_LIMIT", 1000)
        monkeypatch.setattr("src.token.quota.settings.TOKEN_ALERT_THRESHOLD", 0.5)
        monkeypatch.setattr("src.token.quota.settings.TOKEN_ALERT_WEBHOOK", "http://hook.example.com")
        with patch.object(checker, "get_today_usage", return_value={"tokens": 600, "cost": 1.0, "requests": 5}):
            await checker.check_quota("user_x")

    def test_global_instance(self) -> None:
        assert isinstance(quota_checker, QuotaChecker)
