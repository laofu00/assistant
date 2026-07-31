"""agents/supervisor.py 意图分类节点测试"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

from src.models.state import AgentState


def make_state(**overrides) -> AgentState:
    state: AgentState = {
        "messages": [HumanMessage(content="你好")],
        "user_id": "user1",
        "session_id": "sess1",
        "trace_id": "trace1",
        "current_tool": "",
        "tool_results": {},
        "tool_chain": [],
        "token_usage": {},
        "stream_chunks": [],
        "intent": "general",
        "interrupt_required": False,
        "resume_filename": None,
        "jd_text": None,
        "match_report": None,
        "final_score": None,
        "match_mode": "recruiter",
        "_resume_text": None,
        "_tech_result": None,
        "_exp_result": None,
        "_risk_result": None,
    }
    state.update(overrides)
    return state


class FakeLLMResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class TestSupervisorNode:
    async def test_no_messages(self) -> None:
        from src.agents.supervisor import create_supervisor_node

        with patch("src.agents.supervisor.get_llm"):
            node = create_supervisor_node()
        state = make_state(messages=[])
        result = await node(state)
        assert result["intent"] == "general"

    async def test_no_match_keywords(self) -> None:
        """无匹配关键词时快速返回 general"""
        from src.agents.supervisor import create_supervisor_node

        with patch("src.agents.supervisor.get_llm"):
            node = create_supervisor_node()
        state = make_state(messages=[HumanMessage(content="今天天气怎么样")])
        result = await node(state)
        assert result["intent"] == "general"

    async def test_match_keyword_triggers_llm(self) -> None:
        """有匹配关键词时调用 LLM"""
        from src.agents.supervisor import create_supervisor_node

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=FakeLLMResponse('{"intent":"match","match_mode":"recruiter"}'))

        with patch("src.agents.supervisor.get_llm", return_value=mock_llm):
            node = create_supervisor_node()
            state = make_state(messages=[HumanMessage(content="帮我匹配一下简历")])
            result = await node(state)
            assert result["intent"] == "match"

    async def test_candidate_mode_detection(self) -> None:
        """候选视角关键词触发 candidate 模式"""
        from src.agents.supervisor import create_supervisor_node

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=FakeLLMResponse('{"intent":"match","match_mode":"candidate"}'))

        with patch("src.agents.supervisor.get_llm", return_value=mock_llm):
            node = create_supervisor_node()
            state = make_state(messages=[HumanMessage(content="帮我分析一下我适合这个岗位吗")])
            result = await node(state)
            assert result["intent"] == "match"

    async def test_llm_fails_gracefully(self) -> None:
        """LLM 失败时降级为 general"""
        from src.agents.supervisor import create_supervisor_node

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM down"))

        with patch("src.agents.supervisor.get_llm", return_value=mock_llm):
            node = create_supervisor_node()
            state = make_state(messages=[HumanMessage(content="帮我匹配简历和JD")])
            result = await node(state)
            assert result["intent"] == "general"

    async def test_llm_returns_non_string(self) -> None:
        """LLM 返回非字符串时降级为 general"""
        from src.agents.supervisor import create_supervisor_node

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=FakeLLMResponse([1, 2, 3]))  # 返回列表

        with patch("src.agents.supervisor.get_llm", return_value=mock_llm):
            node = create_supervisor_node()
            state = make_state(messages=[HumanMessage(content="帮我匹配一下")])
            result = await node(state)
            assert result["intent"] == "general"

    async def test_extracts_resume_and_jd(self) -> None:
        """从 LLM 返回中提取 resume_file 和 jd_text"""
        from src.agents.supervisor import create_supervisor_node

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=FakeLLMResponse(
            '{"intent":"match","resume_file":"my_resume.pdf","jd_text":"Python工程师","match_mode":"recruiter"}'
        ))

        with patch("src.agents.supervisor.get_llm", return_value=mock_llm):
            node = create_supervisor_node()
            state = make_state(messages=[HumanMessage(content="用my_resume.pdf匹配Python工程师岗位")])
            result = await node(state)
            assert result["intent"] == "match"
            assert result["resume_filename"] == "my_resume.pdf"
            assert result["jd_text"] == "Python工程师"

    async def test_falls_back_to_state_values(self) -> None:
        """LLM 未返回时回退到 state 中的已有值"""
        from src.agents.supervisor import create_supervisor_node

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=FakeLLMResponse('{"intent":"match","match_mode":"recruiter"}'))

        with patch("src.agents.supervisor.get_llm", return_value=mock_llm):
            node = create_supervisor_node()
            state = make_state(
                messages=[HumanMessage(content="匹配")],
                resume_filename="existing.pdf",
                jd_text="existing JD",
            )
            result = await node(state)
            assert result["resume_filename"] == "existing.pdf"
            assert result["jd_text"] == "existing JD"

    async def test_no_json_in_response(self) -> None:
        """LLM 返回不含 JSON 时降级为 general"""
        from src.agents.supervisor import create_supervisor_node

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=FakeLLMResponse("这是一段没有JSON的回复"))

        with patch("src.agents.supervisor.get_llm", return_value=mock_llm):
            node = create_supervisor_node()
            state = make_state(messages=[HumanMessage(content="帮我匹配")])
            result = await node(state)
            assert result["intent"] == "general"
