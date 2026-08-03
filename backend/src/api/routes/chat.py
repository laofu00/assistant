"""对话路由 — POST /api/v1/chat（SSE 流式）+ GET /audit-logs"""

import asyncio
import json

from fastapi import APIRouter, Query, Request
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from src.api.schemas import ChatRequest
from src.core.config import settings
from src.core.llm_factory import set_trace_context
from src.core.memory import sanitize_output
from src.core.schema import R
from src.models.state import AgentState
from src.workflows.supervisor_workflow import supervisor_app

router = APIRouter(tags=["对话"])


async def _stream_chat(message: str, user_id: str, session_id: str | None):
    """SSE 流式生成器"""
    import uuid

    sid = session_id or f"session_{uuid.uuid4().hex[:8]}"
    trace_id = uuid.uuid4().hex

    # 设置当前请求的 token 追踪上下文（后续所有 LLM 调用自动覆盖）
    set_trace_context(
        trace_id=trace_id,
        session_id=sid,
        user_id=user_id,
    )

    from langchain_core.messages import HumanMessage

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
        "match_mode": "recruiter",
        "final_score": None,
        "_resume_text": None,
        "_tech_result": None,
        "_exp_result": None,
        "_risk_result": None,
    }

    config = {"configurable": {"thread_id": user_id}, "recursion_limit": settings.AGENT_RECURSION_LIMIT}

    try:
        has_streamed = False
        match_depth = 0
        pending_tools: list[str] = []
        streamed_len = 0  # 本轮已流式的字符数（工具调用前需回退）
        async for event in supervisor_app.astream_events(initial_state, config, version="v2"):
            kind = event.get("event", "")
            name = event.get("name", "")

            # 跟踪匹配子图嵌套深度
            if kind == "on_chain_start" and name == "match_subgraph":
                match_depth += 1
            elif kind == "on_chain_end" and name == "match_subgraph":
                match_depth -= 1

            # 过滤匹配子图内部的事件
            if name != "ChatTongyi" and kind.startswith("on_chat_model"):
                continue

            if kind == "on_chat_model_stream":
                if match_depth > 0:
                    continue
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    has_streamed = True
                    streamed_len += len(chunk.content)
                    yield {"event": "message", "data": chunk.content}

            elif kind == "on_chat_model_end":
                if match_depth > 0:
                    continue
                output = event.get("data", {}).get("output")
                if output and hasattr(output, "tool_calls") and output.tool_calls:
                    # 有工具调用：通知前端回退推理文字
                    pending_tools = [tc.get("name", "") for tc in output.tool_calls if tc.get("name")]
                    if streamed_len > 0:
                        yield {"event": "undo", "data": str(streamed_len)}
                    has_streamed = False
                    streamed_len = 0
                else:
                    if not has_streamed and output and hasattr(output, "content") and output.content:
                        yield {"event": "message", "data": sanitize_output(str(output.content), user_id)}
                    streamed_len = 0

            # 工具节点开始执行 → 发送思考过程事件
            elif kind == "on_chain_start" and name == "tools":
                for tool_name in pending_tools:
                    yield {
                        "event": "thinking",
                        "data": json.dumps({"tool": tool_name, "status": "start"}, ensure_ascii=False),
                    }

            # 工具节点执行完成
            elif kind == "on_chain_end" and name == "tools":
                for tool_name in pending_tools:
                    yield {
                        "event": "thinking",
                        "data": json.dumps({"tool": tool_name, "status": "done"}, ensure_ascii=False),
                    }
                pending_tools = []

            elif kind == "on_chain_end":
                output = event.get("data", {}).get("output")
                if output and isinstance(output, dict):
                    # 只在最外层 match_subgraph 完成时输出一次报告，避免嵌套节点重复
                    if match_depth == 0 and name == "match_subgraph" and output.get("match_report"):
                        report = sanitize_output(output["match_report"], user_id)
                        has_streamed = True
                        lines = report.split('\n')
                        for line in lines:
                            yield {"event": "message", "data": json.dumps(line + '\n', ensure_ascii=False)}
                            await asyncio.sleep(0.04)  # 逐行流式，~25行/秒
                    meta = {
                        "intent": output.get("intent", "general"),
                        "tool_called": len(output.get("tool_chain", [])) > 0,
                        "session_id": sid,
                    }
                    yield {"event": "metadata", "data": json.dumps(meta, ensure_ascii=False)}

    except Exception as e:
        logger.error(f"SSE 流式异常: {e}")
        yield {"event": "error", "data": str(e)}

    yield {"event": "done", "data": "[DONE]"}


@router.post("/chat")
async def chat(request: ChatRequest):
    """统一对话入口（SSE 流式返回）"""
    logger.info(f"POST /chat user={request.user_id}, session={request.session_id}, msg_len={len(request.message)}")
    return EventSourceResponse(_stream_chat(request.message, request.user_id, request.session_id))


# ==================== Mock（压测专用） ====================

_MOCK_RESPONSE = (
    "好的，我理解您的问题。让我来分析一下。"
    "根据系统架构文档，这个问题可以从以下几个方面来回答："
    "首先，系统的核心设计遵循了模块化和高内聚低耦合的原则。"
    "其次，在实现层面采用了异步非阻塞的 IO 模型，确保了高并发下的性能表现。"
    "最后，通过多层次的缓存和限流机制，保障了服务的稳定性。"
    "综上所述，这是一个经过充分设计的系统方案。"
)

_MOCK_TOOL_NAME = "search_knowledge"


async def _mock_stream():
    """模拟 12 步防护链耗时 + LLM 推理延迟 + SSE 分块输出（压测用，延迟极简）"""
    # 模拟 thinking 事件
    yield {
        "event": "thinking",
        "data": json.dumps({"tool": _MOCK_TOOL_NAME, "status": "start"}, ensure_ascii=False),
    }
    await asyncio.sleep(0.005)

    yield {
        "event": "thinking",
        "data": json.dumps({"tool": _MOCK_TOOL_NAME, "status": "done"}, ensure_ascii=False),
    }
    await asyncio.sleep(0.005)

    # 模拟 LLM 流式输出：3 个块
    for chunk in [_MOCK_RESPONSE[:60], _MOCK_RESPONSE[60:120], _MOCK_RESPONSE[120:]]:
        yield {"event": "message", "data": chunk}
        await asyncio.sleep(0.005)

    yield {
        "event": "metadata",
        "data": json.dumps(
            {"intent": "general", "tool_called": True, "session_id": "mock_session"},
            ensure_ascii=False,
        ),
    }
    yield {"event": "done", "data": "[DONE]"}


@router.post("/chat/mock")
async def chat_mock(request: ChatRequest):
    """压测专用 mock 端点：完整中间件链路 + 模拟 SSE 流式输出，不调用真实 LLM"""
    logger.info(f"POST /chat/mock user={request.user_id}, msg_len={len(request.message)}")
    return EventSourceResponse(_mock_stream())


@router.get("/chat/audit-logs")
async def get_audit_logs(
    request: Request,
    tool_name: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
):
    """查询工具审计日志 — 管理员查看全部用户"""
    from sqlalchemy import and_, func, select

    from src.core.auth_deps import is_admin_user
    from src.core.database import async_session_factory
    from src.models.tool_audit import ToolAuditLog
    from src.models.user import User

    user_id = getattr(request.state, "user_id", "anonymous")
    is_admin = await is_admin_user(user_id)

    async with async_session_factory() as session:
        conditions = []
        if not is_admin:
            conditions.append(ToolAuditLog.user_id == user_id)
        if tool_name:
            conditions.append(ToolAuditLog.tool_name == tool_name)

        total_q = select(func.count(ToolAuditLog.id))
        if conditions:
            total_q = total_q.where(and_(*conditions))
        total = (await session.execute(total_q)).scalar() or 0

        offset = (page - 1) * size
        q = select(ToolAuditLog)
        if conditions:
            q = q.where(and_(*conditions))
        q = q.order_by(ToolAuditLog.created_at.desc()).offset(offset).limit(size)
        result = await session.execute(q)
        logs = result.scalars().all()

        # 批量查找用户名
        user_ids = list({log.user_id for log in logs})
        username_map: dict[str, str] = {}
        if user_ids:
            user_result = await session.execute(select(User.user_id, User.username, User.nickname).where(User.user_id.in_(user_ids)))
            for row in user_result:
                username_map[row[0]] = row[2] or row[1]  # nickname > username

        records = [
            {
                "id": log.id,
                "trace_id": log.trace_id,
                "user_id": log.user_id,
                "user_name": username_map.get(log.user_id, log.user_id),
                "tool_name": log.tool_name,
                "tool_input": log.tool_input,
                "tool_output": log.tool_output,
                "duration_ms": log.duration_ms,
                "result": log.result,
                "error_msg": log.error_msg,
                "created_at": str(log.created_at) if log.created_at else None,
            }
            for log in logs
        ]
        return R.ok({"records": records, "total": total, "page": page, "size": size})
