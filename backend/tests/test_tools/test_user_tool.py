"""tools/user_tool.py 用户工具测试（1个）"""

from unittest.mock import AsyncMock, MagicMock, patch


class TestGetCurrentUserEmail:
    async def test_cache_hit(self) -> None:
        from src.tools import user_tool
        user_tool._email_cache["test_u"] = ("cached@test.com", float("inf"))
        result = await user_tool.get_current_user_email.ainvoke({"user_id": "test_u"})
        assert result == "cached@test.com"
        del user_tool._email_cache["test_u"]

    async def test_db_query_success(self) -> None:
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value="db@test.com")))
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        from src.tools import user_tool
        user_tool._email_cache.clear()
        with patch("src.core.database.async_session_factory", mock_sf):
            result = await user_tool.get_current_user_email.ainvoke({"user_id": "test_u"})
            assert result == "db@test.com"

    async def test_user_not_found(self) -> None:
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        from src.tools import user_tool
        user_tool._email_cache.clear()
        with patch("src.core.database.async_session_factory", mock_sf):
            result = await user_tool.get_current_user_email.ainvoke({"user_id": "no_such"})
            assert result is None

    async def test_db_failure_uses_stale_cache(self) -> None:
        from src.tools import user_tool
        user_tool._email_cache["test_u"] = ("stale@test.com", 0)
        mock_sf = MagicMock(side_effect=Exception("DB down"))

        with patch("src.core.database.async_session_factory", mock_sf):
            result = await user_tool.get_current_user_email.ainvoke({"user_id": "test_u"})
            assert result == "stale@test.com"

    async def test_db_failure_no_cache(self) -> None:
        from src.tools import user_tool
        user_tool._email_cache.clear()
        mock_sf = MagicMock(side_effect=Exception("DB down"))

        with patch("src.core.database.async_session_factory", mock_sf):
            result = await user_tool.get_current_user_email.ainvoke({"user_id": "x"})
            assert result is None
