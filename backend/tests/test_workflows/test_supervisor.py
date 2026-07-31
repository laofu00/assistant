"""workflows/supervisor_workflow.py Supervisor 统一入口测试"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

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


class TestQuotaCheckNode:
    async def test_quota_passes(self) -> None:
        from src.workflows.supervisor_workflow import _quota_check_node

        mock_checker = AsyncMock()
        with patch("src.workflows.supervisor_workflow.quota_checker", mock_checker):
            result = await _quota_check_node(make_state())
            assert result == {}

    async def test_quota_exceeded(self) -> None:
        from src.workflows.supervisor_workflow import _quota_check_node

        mock_checker = AsyncMock()
        mock_checker.check_quota.side_effect = Exception("每日 500,000 tokens 已达上限")

        with patch("src.workflows.supervisor_workflow.quota_checker", mock_checker):
            result = await _quota_check_node(make_state())
            msgs = result.get("messages", [])
            assert len(msgs) == 1
            assert "已达上限" in str(msgs[0].content)


class TestSupervisorRouter:
    def test_general_intent(self) -> None:
        from src.workflows.supervisor_workflow import _supervisor_router

        state = make_state(intent="general")
        result = _supervisor_router(state)
        assert result == "react_subgraph"

    def test_match_intent(self) -> None:
        from src.workflows.supervisor_workflow import _supervisor_router

        state = make_state(intent="match")
        result = _supervisor_router(state)
        assert result == "match_subgraph"


class TestCheckQuotaError:
    def test_no_error(self) -> None:
        from src.workflows.supervisor_workflow import _check_quota_error

        state = make_state(messages=[HumanMessage(content="你好")])
        result = _check_quota_error(state)
        assert result == "supervisor"

    def test_with_quota_error(self) -> None:
        from src.workflows.supervisor_workflow import _check_quota_error

        state = make_state(messages=[AIMessage(content="今日用量已达上限")])
        result = _check_quota_error(state)
        assert result == "__end__"

    def test_empty_messages(self) -> None:
        from src.workflows.supervisor_workflow import _check_quota_error

        state = make_state(messages=[])
        result = _check_quota_error(state)
        assert result == "supervisor"


class TestMatchSubgraph:
    async def test_missing_both(self) -> None:
        from src.workflows.supervisor_workflow import _match_subgraph

        state = make_state(intent="match", resume_filename=None, jd_text=None)
        result = await _match_subgraph(state)
        msgs = result.get("messages", [])
        assert any("简历文件名" in str(m.content) for m in msgs)

    async def test_missing_resume_only(self) -> None:
        from src.workflows.supervisor_workflow import _match_subgraph

        state = make_state(intent="match", resume_filename=None, jd_text="Python工程师 JD 内容不少于10字")
        result = await _match_subgraph(state)
        msgs = result.get("messages", [])
        assert any("简历文件名" in str(m.content) for m in msgs)

    async def test_missing_jd_only(self) -> None:
        from src.workflows.supervisor_workflow import _match_subgraph

        state = make_state(intent="match", resume_filename="resume.pdf", jd_text=None)
        result = await _match_subgraph(state)
        msgs = result.get("messages", [])
        assert any("JD" in str(m.content) for m in msgs)

    async def test_jd_too_short(self) -> None:
        from src.workflows.supervisor_workflow import _match_subgraph

        state = make_state(intent="match", resume_filename="r.pdf", jd_text="短")
        result = await _match_subgraph(state)
        msgs = result.get("messages", [])
        assert any("JD" in str(m.content) for m in msgs)


class TestSupervisorGraph:
    def test_graph_structure(self) -> None:
        """验证工作流图的节点和边结构"""
        from src.workflows.supervisor_workflow import create_supervisor_workflow

        wf = create_supervisor_workflow()
        # 验证入口节点
        assert "quota_check" in wf.nodes
        assert "supervisor" in wf.nodes
        assert "react_subgraph" in wf.nodes
        assert "match_subgraph" in wf.nodes

    def test_all_nodes_present(self) -> None:
        from src.workflows.supervisor_workflow import create_supervisor_workflow

        wf = create_supervisor_workflow()
        nodes = set(wf.nodes.keys())
        expected = {"quota_check", "supervisor", "react_subgraph", "match_subgraph"}
        assert expected.issubset(nodes)
