"""workflows/react_workflow.py ReAct 工作流集成测试 — mock LLM + 真实图结构"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.models.state import AgentState


def make_state(**overrides) -> AgentState:
    state: AgentState = {
        "messages": [HumanMessage(content="测试消息")],
        "user_id": "test_user_react",
        "session_id": "test_session",
        "trace_id": "test_trace",
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


class FakeToolCall:
    """模拟 LLM 返回的 tool_call 对象"""
    def __init__(self, name: str, args: dict, call_id: str = "fake_call_1"):
        self.name = name
        self.args = args
        self.id = call_id
        self.type = "tool_call"


class TestReActNodes:
    async def test_quota_check_passes(self) -> None:
        from src.workflows.react_workflow import _quota_check_node

        mock_qc = MagicMock()
        mock_qc.check_quota = AsyncMock()
        with patch("src.token.quota.quota_checker", mock_qc):
            result = await _quota_check_node(make_state())
            assert result == {}

    async def test_quota_check_blocked(self) -> None:
        from src.workflows.react_workflow import _quota_check_node

        mock_qc = MagicMock()
        mock_qc.check_quota = AsyncMock(side_effect=Exception("额度超限"))
        with patch("src.token.quota.quota_checker", mock_qc):
            result = await _quota_check_node(make_state())
            msgs = result.get("messages", [])
            assert len(msgs) == 1
            assert isinstance(msgs[0], AIMessage)

    async def test_route_after_agent_no_tool_calls(self) -> None:
        """agent 返回无 tool_calls 的 AIMessage → 路由到 save_memory"""
        from src.workflows.react_workflow import _route_after_agent

        state = make_state(messages=[AIMessage(content="直接回复")])
        assert _route_after_agent(state) == "save_memory"

    async def test_route_after_agent_with_tool_calls(self) -> None:
        """agent 返回带 tool_calls 的 AIMessage → 路由到 tools"""
        from src.workflows.react_workflow import _route_after_agent

        msg = AIMessage(content="")
        msg.tool_calls = [{"name": "list_memos", "args": {"user_id": "u1"}, "id": "call_1"}]
        state = make_state(messages=[msg])
        assert _route_after_agent(state) == "tools"

    async def test_route_after_agent_empty_messages(self) -> None:
        from src.workflows.react_workflow import _route_after_agent

        state = make_state(messages=[])
        assert _route_after_agent(state) == "save_memory"

    async def test_tools_node_no_tool_calls(self) -> None:
        """最后一条消息不是 AIMessage → 返回空"""
        from src.workflows.react_workflow import _tools_node

        state = make_state(messages=[HumanMessage(content="你好")])
        result = await _tools_node(state)
        assert result == {}

    async def test_tools_node_no_tool_calls_in_ai_message(self) -> None:
        """AIMessage 无 tool_calls 属性 → 返回空"""
        from src.workflows.react_workflow import _tools_node

        state = make_state(messages=[AIMessage(content="普通回复")])
        result = await _tools_node(state)
        assert result == {}

    async def test_save_memory_node(self, mock_redis) -> None:
        """保存记忆节点：保存用户+助手消息对"""
        from src.workflows.react_workflow import _save_memory_node

        state = make_state(messages=[
            HumanMessage(content="帮我查备忘录"),
            AIMessage(content="好的，找到3条备忘录"),
        ])
        result = await _save_memory_node(state)
        assert result == {}

    async def test_save_memory_node_skip_tool_call_msg(self, mock_redis) -> None:
        """tool_calls 的 AIMessage 不保存到记忆"""
        from src.workflows.react_workflow import _save_memory_node

        tool_msg = AIMessage(content="")
        tool_msg.tool_calls = [{"name": "list_memos", "args": {}, "id": "x"}]
        state = make_state(messages=[HumanMessage(content="查"), tool_msg])
        result = await _save_memory_node(state)
        assert result == {}


class TestReActGraphStructure:
    def test_create_workflow_nodes(self) -> None:
        """验证图节点完整性"""
        from src.workflows.react_workflow import create_react_workflow

        wf = create_react_workflow()
        nodes = set(wf.nodes.keys())
        expected = {"quota_check", "load_memory", "agent", "tools", "save_memory"}
        assert expected.issubset(nodes), f"Missing nodes: {expected - nodes}"


class TestReActAgent:
    def test_create_agent_node_with_tools(self) -> None:
        """验证 Agent 节点能正常创建（不调 LLM）"""
        from src.agents.react_agent import create_agent_node

        fake_tools = [MagicMock(name="tool_a"), MagicMock(name="tool_b")]
        for t in fake_tools:
            t.name = getattr(t, "name", None) or "unknown"

        with patch("src.agents.react_agent.get_llm") as mock_llm:
            mock_chat = MagicMock()
            mock_chat.bind_tools = MagicMock(return_value=mock_chat)
            mock_llm.return_value = mock_chat

            node = create_agent_node(fake_tools)
            assert callable(node)

    async def test_agent_node_direct_response(self) -> None:
        """Agent 直接回复（无 tool_call）"""
        from unittest.mock import AsyncMock

        from src.agents.react_agent import create_agent_node

        mock_chat = MagicMock()
        mock_response = AIMessage(content="你好！有什么可以帮助你的？")
        mock_chat.invoke = MagicMock(return_value=mock_response)
        mock_chat.bind_tools = MagicMock(return_value=mock_chat)

        with patch("src.agents.react_agent.get_llm", return_value=mock_chat):
            node = create_agent_node([])
            state = make_state(messages=[HumanMessage(content="你好")])

            result = node(state)
            msgs = result.get("messages", [])
            assert len(msgs) == 1
            assert isinstance(msgs[0], AIMessage)
            assert "你好" in str(msgs[0].content)

    async def test_agent_node_with_tool_calls(self) -> None:
        """Agent 返回 tool_call（同步 invoke）"""
        from src.agents.react_agent import create_agent_node

        mock_chat = MagicMock()
        ai_msg = AIMessage(content="我来帮你查一下")
        ai_msg.tool_calls = [{"name": "list_memos", "args": {"user_id": "u1"}, "id": "call_1"}]
        mock_chat.invoke = MagicMock(return_value=ai_msg)
        mock_chat.bind_tools = MagicMock(return_value=mock_chat)

        with patch("src.agents.react_agent.get_llm", return_value=mock_chat):
            node = create_agent_node([])
            state = make_state(messages=[HumanMessage(content="帮我查备忘录")])

            result = node(state)
            msgs = result.get("messages", [])
            assert len(msgs) == 1
            tool_calls = getattr(msgs[0], "tool_calls", None)
            assert tool_calls is not None
            assert tool_calls[0]["name"] == "list_memos"


class TestCreateReactWorkflow:
    def test_workflow_compiles(self) -> None:
        """验证工作流能正常编译"""
        from src.workflows.react_workflow import create_react_workflow

        wf = create_react_workflow()
        assert wf is not None
        # 验证 entry point
        compiled = wf.compile()
        assert compiled is not None
