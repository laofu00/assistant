"""LangGraph AgentState 定义"""

from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """Agent 全局状态 — 贯穿整个工作流图"""

    # 对话消息（自动追加）
    messages: Annotated[list[BaseMessage], add_messages]

    # 用户与会话
    user_id: str
    session_id: str
    trace_id: str

    # 工具调用
    current_tool: str
    tool_results: dict[str, Any]
    tool_chain: list[dict[str, Any]]  # [{tool, input, output, duration_ms}, ...]

    # Token 追踪
    token_usage: dict[str, Any]  # {input_tokens, output_tokens, total_tokens, model, cost}
    stream_chunks: list[Any]     # 流式 chunks（用于聚合 Token 用量）

    # 控制
    intent: str                   # general / match
    interrupt_required: bool

    # 简历匹配专用（第四/五阶段）
    resume_filename: str | None
    jd_text: str | None
    match_report: str | None
    final_score: float | None
    match_mode: str  # "recruiter" | "candidate"
    # 匹配流程中间结果
    _resume_text: str | None
    _tech_result: dict | None
    _exp_result: dict | None
    _risk_result: dict | None
