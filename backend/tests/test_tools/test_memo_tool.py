"""tools/memo_tool.py 备忘录工具测试（6个）"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAddMemo:
    async def test_add_success(self) -> None:
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        with patch("src.tools.memo_tool.async_session_factory", mock_sf):
            from src.tools.memo_tool import add_memo
            result = await add_memo.ainvoke({"title": "测试备忘", "content": "测试内容", "due_date": None, "user_id": "u1"})
            assert "创建成功" in result

    async def test_empty_title(self) -> None:
        with patch("src.tools.memo_tool.async_session_factory"):
            from src.tools.memo_tool import add_memo
            result = await add_memo.ainvoke({"title": "", "content": "内容", "due_date": None, "user_id": "u1"})
            assert "不能为空" in result

    async def test_empty_content(self) -> None:
        with patch("src.tools.memo_tool.async_session_factory"):
            from src.tools.memo_tool import add_memo
            result = await add_memo.ainvoke({"title": "标题", "content": "", "due_date": None, "user_id": "u1"})
            assert "不能为空" in result

    async def test_with_due_date(self) -> None:
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        with patch("src.tools.memo_tool.async_session_factory", mock_sf):
            from src.tools.memo_tool import add_memo
            result = await add_memo.ainvoke({"title": "备忘", "content": "内容", "due_date": "2025-12-31", "user_id": "u1"})
            assert "创建成功" in result
            assert "2025-12-31" in result


class TestListMemos:
    async def test_list_with_results(self) -> None:
        mock_memo = MagicMock()
        mock_memo.id = 1
        mock_memo.category = "工作"
        mock_memo.title = "测试"
        mock_memo.due_date = None
        mock_memo.content = "内容"

        mock_session = MagicMock()
        mock_session.execute = AsyncMock()
        mock_session.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=1)),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_memo])))),
        ]
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        with patch("src.tools.memo_tool.async_session_factory", mock_sf):
            from src.tools.memo_tool import list_memos
            result = await list_memos.ainvoke({"user_id": "u1"})
            assert "测试" in result


class TestCompleteMemo:
    async def test_success(self) -> None:
        mock_memo = MagicMock()
        mock_memo.title = "待完成"
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_memo)))
        mock_session.commit = AsyncMock()
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        with patch("src.tools.memo_tool.async_session_factory", mock_sf):
            from src.tools.memo_tool import complete_memo
            result = await complete_memo.ainvoke({"memo_id": 1, "user_id": "u1"})
            assert "完成" in result

    async def test_not_found(self) -> None:
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        with patch("src.tools.memo_tool.async_session_factory", mock_sf):
            from src.tools.memo_tool import complete_memo
            result = await complete_memo.ainvoke({"memo_id": 999, "user_id": "u1"})
            assert "未找到" in result


class TestDeleteMemo:
    async def test_success(self) -> None:
        mock_memo = MagicMock()
        mock_memo.title = "待删除"
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_memo)))
        mock_session.commit = AsyncMock()
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        with patch("src.tools.memo_tool.async_session_factory", mock_sf):
            from src.tools.memo_tool import delete_memo
            result = await delete_memo.ainvoke({"memo_id": 1, "user_id": "u1"})
            assert "已删除" in result

    async def test_not_found(self) -> None:
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        with patch("src.tools.memo_tool.async_session_factory", mock_sf):
            from src.tools.memo_tool import delete_memo
            result = await delete_memo.ainvoke({"memo_id": 999, "user_id": "u1"})
            assert "未找到" in result


class TestUpdateMemo:
    async def test_success(self) -> None:
        mock_memo = MagicMock()
        mock_memo.title = "旧标题"
        mock_memo.content = "旧内容"
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_memo)))
        mock_session.commit = AsyncMock()
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        with patch("src.tools.memo_tool.async_session_factory", mock_sf):
            from src.tools.memo_tool import update_memo
            result = await update_memo.ainvoke({"memo_id": 1, "title": "新标题", "content": "新内容", "due_date": None, "user_id": "u1"})
            assert "更新成功" in result

    async def test_invalid_id(self) -> None:
        with patch("src.tools.memo_tool.async_session_factory"):
            from src.tools.memo_tool import update_memo
            result = await update_memo.ainvoke({"memo_id": 0, "title": "x", "content": None, "due_date": None, "user_id": "u1"})
            assert "无效" in result

    async def test_no_title_no_content(self) -> None:
        with patch("src.tools.memo_tool.async_session_factory"):
            from src.tools.memo_tool import update_memo
            result = await update_memo.ainvoke({"memo_id": 1, "title": "", "content": "", "due_date": None, "user_id": "u1"})
            assert "至少需要" in result

    async def test_not_found(self) -> None:
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        with patch("src.tools.memo_tool.async_session_factory", mock_sf):
            from src.tools.memo_tool import update_memo
            result = await update_memo.ainvoke({"memo_id": 999, "title": "x", "content": None, "due_date": None, "user_id": "u1"})
            assert "未找到" in result


class TestListMemosByDate:
    async def test_valid_range_empty(self) -> None:
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        with patch("src.tools.memo_tool.async_session_factory", mock_sf):
            from src.tools.memo_tool import list_memos
            result = await list_memos.ainvoke({"user_id": "u1", "due_before": "2025-12-31", "due_after": "2025-01-01"})
            assert "没有找到" in result

    async def test_valid_range_with_results(self) -> None:
        mock_memo = MagicMock()
        mock_memo.id = 1
        mock_memo.category = "工作"
        mock_memo.title = "任务"
        mock_memo.due_date = None
        mock_memo.content = "详情"
        mock_memo.status = 1
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_memo])))))
        mock_sf = MagicMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        with patch("src.tools.memo_tool.async_session_factory", mock_sf):
            from src.tools.memo_tool import list_memos
            result = await list_memos.ainvoke({"user_id": "u1", "due_before": "2025-12-31"})
            assert "任务" in result
