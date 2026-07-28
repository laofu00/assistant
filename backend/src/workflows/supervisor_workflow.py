"""Supervisor 统一入口工作流 — 顶层路由图

Supervisor 意图分类 → 条件路由
  ├── match   → match_workflow（简历匹配子图）
  └── general → react_workflow（ReAct 工作流）
"""

import uuid
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from loguru import logger

from src.agents.supervisor import create_supervisor_node
from src.core.memory import sanitize_output, smart_memory
from src.models.state import AgentState
from src.token.quota import quota_checker
from src.workflows.match_workflow import match_app
from src.workflows.react_workflow import react_app


# ==================== 节点 ====================


async def _quota_check_node(state: AgentState) -> dict:
    """配额检查（入口第一关）"""
    user_id = state.get("user_id", "")
    try:
        await quota_checker.check_quota(user_id)
    except Exception as e:
        logger.warning(f"配额检查不通过: {e}")
        return {"messages": [AIMessage(content=f"今日用量已达上限：{e}")]}
    return {}


async def _supervisor_node(state: AgentState) -> dict:
    """Supervisor 意图分类"""
    supervisor = create_supervisor_node()
    return await supervisor(state)


async def _react_subgraph(state: AgentState) -> dict:
    """React 子图：完整 ReAct 工作流"""
    logger.info(f"路由到 ReAct 工作流, user={state.get('user_id')}")

    config = {"configurable": {"thread_id": state.get("user_id", "default")}}
    result = await react_app.ainvoke(state, config)

    # 保存记忆
    messages = result.get("messages", [])
    if messages:
        smart_memory.add_messages(state.get("session_id", ""), messages)

    return result


async def _match_subgraph(state: AgentState) -> dict:
    """匹配子图：简历匹配"""
    logger.info(f"路由到匹配工作流, user={state.get('user_id')}, resume={state.get('resume_filename')}")

    # 如果还没有 resume_filename 和 jd_text，尝试从消息中提取
    if not state.get("resume_filename") and not state.get("jd_text"):
        messages = state.get("messages", [])
        for m in reversed(messages):
            content = m.content if hasattr(m, "content") else str(m)
            if "简历" in str(content) or "resume" in str(content).lower():
                # 提示用户提供
                return {
                    "messages": messages + [AIMessage(content="请提供以下信息：\n1. 简历文件名（已上传到知识库的文件名）\n2. JD文本内容（直接粘贴或提供文件名）")],
                    "match_report": None,
                }

    result = await match_app.ainvoke(state)

    # 将报告作为 AI 消息返回
    report = result.get("match_report", "")
    messages = list(state.get("messages", []))
    if report:
        messages.append(AIMessage(content=report))

    return {"messages": messages, "match_report": report, "final_score": result.get("final_score")}


async def _capture_token_node(state: AgentState) -> dict:
    """Token 捕获（由 TokenCaptureCallback 在 LLM 调用时实时写入）"""
    return {}


# ==================== 路由 ====================


def _supervisor_router(state: AgentState) -> Literal["react_subgraph", "match_subgraph"]:
    """Supervisor 条件路由"""
    intent = state.get("intent", "general")
    if intent == "match":
        return "match_subgraph"
    return "react_subgraph"


def _check_quota_error(state: AgentState) -> Literal["supervisor", "__end__"]:
    """检查配额是否通过"""
    messages = state.get("messages", [])
    if messages and isinstance(messages[-1], AIMessage):
        content = messages[-1].content
        if content and isinstance(content, str) and "已达上限" in content:
            return END
    return "supervisor"


# ==================== 图构建 ====================


def create_supervisor_workflow() -> StateGraph:
    """创建 Supervisor 统一入口工作流"""
    workflow = StateGraph(AgentState)

    workflow.add_node("quota_check", _quota_check_node)
    workflow.add_node("supervisor", _supervisor_node)
    workflow.add_node("react_subgraph", _react_subgraph)
    workflow.add_node("match_subgraph", _match_subgraph)
    workflow.add_node("capture_token", _capture_token_node)

    workflow.set_entry_point("quota_check")
    workflow.add_conditional_edges("quota_check", _check_quota_error, {"supervisor": "supervisor", "__end__": END})
    workflow.add_conditional_edges("supervisor", _supervisor_router, {"react_subgraph": "react_subgraph", "match_subgraph": "match_subgraph"})
    workflow.add_edge("react_subgraph", "capture_token")
    workflow.add_edge("match_subgraph", "capture_token")
    workflow.add_edge("capture_token", END)

    return workflow


# ==================== 编译 ====================

# MemorySaver 按 thread_id 隔离多轮对话
checkpointer = MemorySaver()
supervisor_app = create_supervisor_workflow().compile(checkpointer=checkpointer)


async def run_chat(
    message: str,
    user_id: str = "test",
    session_id: str | None = None,
) -> dict:
    """统一对话入口

    Args:
        message: 用户消息
        user_id: 用户ID
        session_id: 会话ID

    Returns:
        最终 AgentState
    """
    sid = session_id or f"session_{uuid.uuid4().hex[:8]}"
    trace_id = uuid.uuid4().hex

    initial_state: AgentState = {
        "messages": [HumanMessage(content=message)],
        "user_id": user_id,
        "session_id": sid,
        "trace_id": trace_id,
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

    config = {"configurable": {"thread_id": user_id}}
    result = await supervisor_app.ainvoke(initial_state, config)
    return result
