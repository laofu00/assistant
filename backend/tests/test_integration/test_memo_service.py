"""services/memo_service.py 备忘录分类服务集成测试"""

import pytest

from src.services.memo_service import CATEGORY_LIST, CATEGORY_RULES, async_classify_memo, classify_memo


class TestClassifyMemo:
    def test_work_keyword(self) -> None:
        assert classify_memo("代码审查会议", "讨论技术方案") == "工作"
        assert classify_memo("周报提交") == "工作"
        assert classify_memo("修复线上bug") == "工作"

    def test_life_keyword(self) -> None:
        assert classify_memo("周末爬山", "带上帐篷") == "生活"
        assert classify_memo("妈妈生日") == "生活"
        assert classify_memo("换季洗衣") == "生活"

    def test_study_keyword(self) -> None:
        assert classify_memo("刷题leetcode", "动态规划") == "学习"
        assert classify_memo("看书笔记") == "学习"

    def test_todo_keyword(self) -> None:
        assert classify_memo("记得交费", "水电费") == "待办"
        r = classify_memo("DEADLINE is today", "")
        assert r == "待办", f"Expected 待办, got: {repr(r)}"

    def test_important_priority(self) -> None:
        """重要关键词优先于其他分类"""
        assert classify_memo("紧急修复线上重要bug") == "重要"

    def test_longest_match_priority(self) -> None:
        """同分类下最长关键词优先"""
        assert classify_memo("代码审查") == "工作"  # "代码审查" 匹配

    def test_default_uncategorized(self) -> None:
        assert classify_memo("随便写点什么", "") == "未分类"

    def test_content_fallback(self) -> None:
        """标题无匹配时从内容中分类"""
        assert classify_memo("记一下", "明天的代码审查会议") == "工作"

    def test_case_insensitive(self) -> None:
        assert classify_memo("Fix BUG in PROD") == "工作"
        assert classify_memo("DEADLINE approaching") == "待办"


class TestAsyncClassifyMemo:
    async def test_keyword_match_no_llm(self) -> None:
        """关键词命中时不调用 LLM"""
        cat = await async_classify_memo("代码审查", "讨论设计模式")
        assert cat == "工作"

    async def test_llm_fallback(self, monkeypatch) -> None:
        """关键词未命中时调用 LLM"""
        from unittest.mock import AsyncMock, MagicMock

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "工作"
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        monkeypatch.setattr("src.core.llm_factory.get_llm", lambda **kw: mock_llm)

        cat = await async_classify_memo("xyzabc", "nokeyword content")
        assert cat in CATEGORY_LIST

    async def test_uncategorized_no_llm_hit(self, monkeypatch) -> None:
        """关键词和 LLM 都未命中时返回未分类"""
        from unittest.mock import AsyncMock, MagicMock

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "其他"
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        monkeypatch.setattr("src.core.llm_factory.get_llm", lambda **kw: mock_llm)

        cat = await async_classify_memo("xyz", "noclassify")
        assert cat == "未分类"

    async def test_llm_exception_graceful(self, monkeypatch) -> None:
        """LLM 异常时降级返回未分类"""
        from unittest.mock import AsyncMock, MagicMock

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM down"))

        monkeypatch.setattr("src.core.llm_factory.get_llm", lambda **kw: mock_llm)

        cat = await async_classify_memo("xyz", "no keyword")
        assert cat == "未分类"
