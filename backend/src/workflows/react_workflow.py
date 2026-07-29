"""ReAct 工作流 — LangGraph StateGraph（Agent ↔ Tools 循环）

完整节点链：
rate_limit → quota_check → load_memory → agent → tools/capture_token → save_memory → __end__
"""

import uuid
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from loguru import logger

from src.agents.react_agent import create_agent_node
from src.core.memory import smart_memory
from src.models.state import AgentState
from src.tools import date_tool, email_tool, knowledge_tool, memo_tool, user_tool
from src.tools.tool_registry import ToolPermission, tool_registry
from src.tools.tool_wrapper import tool_executor

# ==================== 注册所有工具 ====================

_ALL_TOOLS: list = []


def _register_tools() -> list:
    """注册全部 18 个工具到 ToolRegistry"""
    global _ALL_TOOLS  # noqa: PLW0603
    if _ALL_TOOLS:
        return _ALL_TOOLS

    tools_config = [
        # KnowledgeTool (5)
        (knowledge_tool.search_knowledge, ToolPermission.READ_ONLY),
        (knowledge_tool.upload_knowledge, ToolPermission.READ_WRITE),
        (knowledge_tool.get_document_content, ToolPermission.READ_ONLY),
        (knowledge_tool.list_knowledge, ToolPermission.READ_ONLY),
        (knowledge_tool.delete_knowledge, ToolPermission.READ_WRITE),
        # MemoTool (6)
        (memo_tool.add_memo, ToolPermission.READ_WRITE),
        (memo_tool.list_memos, ToolPermission.READ_ONLY),
        (memo_tool.complete_memo, ToolPermission.READ_WRITE),
        (memo_tool.delete_memo, ToolPermission.READ_WRITE),
        (memo_tool.update_memo, ToolPermission.READ_WRITE),
        (memo_tool.list_memos_by_date, ToolPermission.READ_ONLY),
        # EmailTool (4)
        (email_tool.preview_email, ToolPermission.READ_WRITE),
        (email_tool.do_send_email, ToolPermission.READ_WRITE),
        (email_tool.do_send_formatted_email, ToolPermission.READ_WRITE),
        # DateTool (4)
        (date_tool.get_current_date, ToolPermission.READ_ONLY),
        (date_tool.get_date_after_days, ToolPermission.READ_ONLY),
        (date_tool.get_current_datetime, ToolPermission.READ_ONLY),
        (date_tool.parse_date_range, ToolPermission.READ_ONLY),
        # UserTool (1)
        (user_tool.get_current_user_email, ToolPermission.READ_ONLY),
    ]

    for func, perm in tools_config:
        tool_registry.register_tool(func, perm)

    _ALL_TOOLS = [func for func, _ in tools_config]
    logger.info(f"工具注册完成，共 {len(_ALL_TOOLS)} 个工具")
    for f in _ALL_TOOLS:
        logger.debug(f"  {getattr(f, 'name', '?')}")
    return _ALL_TOOLS


# ==================== 节点函数 ====================


async def _quota_check_node(state: AgentState) -> dict:
    """配额检查节点"""
    from src.token.quota import quota_checker

    user_id = state.get("user_id", "")
    try:
        await quota_checker.check_quota(user_id)
    except Exception as e:
        logger.warning(f"配额检查不通过: {e}")
        return {"messages": [AIMessage(content=str(e))]}
    return {}


async def _load_memory_node(state: AgentState) -> dict:
    """加载历史记忆节点"""
    session_id = state.get("session_id", "")
    messages = state["messages"]
    if not messages:
        return {}

    # 获取最后一条用户消息
    user_msgs = [m for m in messages if isinstance(m, HumanMessage)]
    if not user_msgs:
        return {}

    last_user = user_msgs[-1]
    current_message = last_user.content if isinstance(last_user.content, str) else ""

    # 拼接历史 + 用户ID提示
    formatted = await smart_memory.get_formatted_history(session_id, current_message)
    formatted += f"\n\n[系统信息] 当前用户ID: {state.get('user_id', '')}"
    formatted += "\n注意：所有需要 userId 参数的工具调用都必须使用上述用户ID。"

    # 替换最后一条用户消息：返回新消息替换旧的
    # add_messages reducer 通过 ID 去重，需用相同 ID
    replacement = HumanMessage(content=formatted, id=last_user.id)
    return {"messages": [replacement]}


async def _tools_node(state: AgentState) -> dict:
    """工具执行节点（带 ToolExecutor 包装）"""
    last_message = state["messages"][-1] if state["messages"] else None
    if not last_message or not isinstance(last_message, AIMessage):
        return {}

    tool_calls = getattr(last_message, "tool_calls", [])
    if not tool_calls:
        return {}

    user_id = state.get("user_id", "")
    session_id = state.get("session_id", "")
    trace_id = state.get("trace_id", "")
    tool_messages: list[ToolMessage] = []
    chain_entries: list[dict] = []

    for tc in tool_calls:
        tool_name = tc.get("name", "")
        tool_args = tc.get("args", {})
        tool_id = tc.get("id", "")

        # 通过 ToolExecutor 执行（含超时/缓存/审计/熔断/重复检测）
        try:
            # 找到原始工具函数
            tool_callable = None
            for t in _ALL_TOOLS:
                t_name = getattr(t, "name", None) or getattr(t, "__name__", "")
                if t_name == tool_name:
                    # StructuredTool: 异步取 coroutine，同步取 func
                    tool_callable = getattr(t, "coroutine", None) or getattr(t, "func", None) or t
                    break

            if tool_callable:
                result = await tool_executor.execute(
                    tool_name=tool_name,
                    tool_func=tool_callable,
                    args=tool_args,
                    user_id=user_id,
                    session_id=session_id,
                    trace_id=trace_id,
                )
            else:
                def _fallback(tool: str = tool_name, **kw: object) -> str:  # noqa: B023
                    return f"工具 [{tool}] 未注册"
                fallback = _fallback
                result = await tool_executor._invoke(fallback, tool_args)

            chain_entries.append({
                "tool": tool_name,
                "input": str(tool_args)[:200],
                "output": str(result)[:200],
            })
            tool_messages.append(ToolMessage(content=str(result), tool_call_id=tool_id, name=tool_name))

            # preview_email 调用后：强制 LLM 把预览内容完整展示给用户
            if tool_name == "preview_email":
                tool_messages.append(SystemMessage(
                    content=(
                        "[系统指令 - 最高优先级] 你刚才调用了邮件预览工具 preview_email。"
                        "现在你必须立即执行以下步骤，不可跳过：\n"
                        "1. 查看上面 ToolMessage 中返回的邮件预览内容\n"
                        "2. 将预览内容**逐字逐句完整展示**给用户，包括收件人、主题、正文的每一个字\n"
                        "3. 绝对禁止总结、省略、概括——必须展示完整原文\n"
                        "4. 绝对禁止只说'请确认发送'而不展示内容\n"
                        "5. 展示完预览后，最后询问：'请回复确认发送或取消'"
                    )
                ))

        except Exception as e:
            error_msg = f"工具执行异常: {e}"
            logger.error(f"工具 [{tool_name}] 执行异常: {e}")
            tool_messages.append(ToolMessage(content=error_msg, tool_call_id=tool_id, name=tool_name))
            chain_entries.append({"tool": tool_name, "input": str(tool_args)[:200], "output": error_msg})

    return {
        "messages": tool_messages,
        "tool_chain": state.get("tool_chain", []) + chain_entries,
    }


async def _capture_token_node(state: AgentState) -> dict:
    """Token 捕获（由 TokenCaptureCallback 在 LLM 调用时实时写入）"""
    return {}


async def _save_memory_node(state: AgentState) -> dict:
    """保存对话记忆节点"""
    session_id = state.get("session_id", "")
    messages = state["messages"]

    # 只保存 user + assistant 的消息对
    user_msgs = [m for m in messages if isinstance(m, HumanMessage)]
    assistant_msgs = [m for m in messages if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None)]

    if user_msgs and assistant_msgs:
        smart_memory.add_messages(session_id, [user_msgs[-1], assistant_msgs[-1]])

    return {}


# ==================== 路由函数 ====================


def _route_after_agent(state: AgentState) -> Literal["tools", "capture_token"]:
    """代理节点后的条件路由：有 tool_calls → tools，否则 → capture_token"""
    last_message = state["messages"][-1] if state["messages"] else None
    if last_message and isinstance(last_message, AIMessage):
        tool_calls = getattr(last_message, "tool_calls", [])
        if tool_calls:
            return "tools"
    return "capture_token"


# ==================== 图构建 ====================


def create_react_workflow() -> StateGraph:
    """创建 ReAct 工作流图"""
    tools = _register_tools()

    workflow = StateGraph(AgentState)

    # 添加节点
    agent_node = create_agent_node(tools)
    workflow.add_node("quota_check", _quota_check_node)
    workflow.add_node("load_memory", _load_memory_node)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", _tools_node)
    workflow.add_node("capture_token", _capture_token_node)
    workflow.add_node("save_memory", _save_memory_node)

    # 边
    workflow.set_entry_point("quota_check")
    workflow.add_edge("quota_check", "load_memory")
    workflow.add_edge("load_memory", "agent")
    workflow.add_conditional_edges("agent", _route_after_agent, {"tools": "tools", "capture_token": "capture_token"})
    workflow.add_edge("tools", "agent")  # 工具结果返回 agent 继续推理
    workflow.add_edge("capture_token", "save_memory")
    workflow.add_edge("save_memory", END)

    return workflow


# ==================== 编译应用 ====================


# MemorySaver 按 thread_id 隔离多轮对话
checkpointer = MemorySaver()

react_app = create_react_workflow().compile(checkpointer=checkpointer)


async def run_react_agent(
    message: str,
    user_id: str = "test",
    session_id: str | None = None,
) -> dict:
    """运行 ReAct Agent 的便捷入口

    Args:
        message: 用户消息
        user_id: 用户ID
        session_id: 会话ID（None 则自动生成）

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
    }

    config = {"configurable": {"thread_id": user_id}}
    result = await react_app.ainvoke(initial_state, config)
    return result
