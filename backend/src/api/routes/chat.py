"""对话路由 — POST /api/v1/chat（SSE 流式）+ GET /audit-logs"""

import asyncio
import json

from fastapi import APIRouter, Query
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from src.api.schemas import ChatRequest
from src.core.schema import R
from src.models.state import AgentState
from src.workflows.supervisor_workflow import supervisor_app

router = APIRouter(tags=["对话"])


async def _stream_chat(message: str, user_id: str, session_id: str | None):
    """SSE 流式生成器"""
    import uuid

    sid = session_id or f"session_{uuid.uuid4().hex[:8]}"
    trace_id = uuid.uuid4().hex

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

    config = {"configurable": {"thread_id": user_id}}

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
                        yield {"event": "message", "data": output.content}
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
                        report = output["match_report"]
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


@router.get("/chat/audit-logs")
async def get_audit_logs(
    user_id: str = Query(default="test"),
    tool_name: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
):
    """查询工具审计日志"""
    from sqlalchemy import and_, func, select

    from src.core.database import async_session_factory
    from src.models.tool_audit import ToolAuditLog

    async with async_session_factory() as session:
        conditions = []
        if user_id:
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

        records = [
            {
                "id": log.id,
                "trace_id": log.trace_id,
                "user_id": log.user_id,
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
