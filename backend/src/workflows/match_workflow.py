"""简历匹配子图 — LangGraph StateGraph（fetch_docs → fan-out 3 agents → summarize）

封装为独立子图，输入 resume_filename + jd_text，输出 match_report + final_score + decision
三个评估 Agent（tech/exp/risk）通过 LangGraph Send 并行执行，结果逐步反馈前端
"""

import time

from langgraph.graph import END, StateGraph
from langgraph.types import Send
from loguru import logger

from src.agents.match_agents import (
    CANDIDATE_EXP_PROMPT,
    CANDIDATE_RISK_PROMPT,
    CANDIDATE_TECH_PROMPT,
    EXP_MATCH_PROMPT,
    RISK_ASSESS_PROMPT,
    TECH_MATCH_PROMPT,
    _invoke_agent,
    summarize_candidate_results,
    summarize_results,
)
from src.core.llm_factory import set_trace_context, update_trace_context
from src.core.metrics import (
    match_agent_duration_seconds,
    match_score_distribution,
    match_total,
)
from src.knowledge.vector_store import vector_store
from src.models.state import AgentState


async def _fetch_docs_node(state: AgentState) -> dict:
    """前置处理：从知识库获取简历和JD完整内容"""
    user_id = state.get("user_id", "")
    resume_filename = state.get("resume_filename")
    jd_text = state.get("jd_text")

    # 获取简历内容
    resume_text = ""
    if resume_filename:
        chunks = vector_store.get_by_filename(user_id, resume_filename)
        if chunks:
            resume_text = "\n\n".join(c["text"] for c in chunks)
            logger.info(f"简历 [{resume_filename}] 加载完成: {len(chunks)} chunks, {len(resume_text)} chars")
        else:
            logger.warning(f"知识库中未找到简历 [{resume_filename}]")

    # 获取 JD 内容
    jd_text = jd_text or ""
    if jd_text and jd_text.endswith((".txt", ".pdf", ".docx", ".doc")):
        jd_chunks = vector_store.get_by_filename(user_id, jd_text)
        if jd_chunks:
            jd_text = "\n\n".join(c["text"] for c in jd_chunks)
            logger.info(f"JD [{jd_text}] 加载完成")
        else:
            logger.warning(f"知识库中未找到 JD [{jd_text}]，作为文本处理")

    return {"resume_filename": resume_filename, "jd_text": jd_text, "_resume_text": resume_text}


def _fanout_decision(state: AgentState) -> list[Send]:
    """决定 fan-out 目标：文档就绪 → 3个Agent并行，文档缺失 → 直接到汇总报错"""
    resume_text = state.get("_resume_text", "")
    jd_text = state.get("jd_text", "")

    if not resume_text:
        # 直接跳到汇总节点，传入错误
        return [Send("summarize", {"match_report": "## 错误\n\n未找到简历内容。请确认简历文件已上传到知识库。", "final_score": 0.0, "_tech_result": {"error": "no_resume"}, "_exp_result": {"error": "no_resume"}, "_risk_result": {"error": "no_resume"}})]

    if not jd_text or len(jd_text.strip()) < 10:
        return [Send("summarize", {"match_report": "## 错误\n\nJD内容不足，请提供完整的岗位描述文本。", "final_score": 0.0, "_tech_result": {"error": "no_jd"}, "_exp_result": {"error": "no_jd"}, "_risk_result": {"error": "no_jd"}})]

    # 并行评估三个维度
    return [
        Send("tech_agent", state),
        Send("exp_agent", state),
        Send("risk_agent", state),
    ]


async def _tech_agent_node(state: AgentState) -> dict:
    """技术评估（根据 match_mode 切换视角）"""
    update_trace_context(intent_type="MATCH_TECH", call_purpose="tech_eval")
    resume_text = state.get("_resume_text", "")
    jd_text = state.get("jd_text", "")
    mode = state.get("match_mode", "recruiter")
    prompt = CANDIDATE_TECH_PROMPT if mode == "candidate" else TECH_MATCH_PROMPT
    start = time.monotonic()
    try:
        result = await _invoke_agent(prompt, resume_text, jd_text, mode)
        match_agent_duration_seconds.labels(agent="tech").observe(time.monotonic() - start)
        return {"_tech_result": result}
    except Exception as e:
        logger.error(f"技术评估失败: {e}")
        match_agent_duration_seconds.labels(agent="tech").observe(time.monotonic() - start)
        return {"_tech_result": {"error": str(e)}}


async def _exp_agent_node(state: AgentState) -> dict:
    """经验评估（根据 match_mode 切换视角）"""
    update_trace_context(intent_type="MATCH_EXP", call_purpose="exp_eval")
    resume_text = state.get("_resume_text", "")
    jd_text = state.get("jd_text", "")
    mode = state.get("match_mode", "recruiter")
    prompt = CANDIDATE_EXP_PROMPT if mode == "candidate" else EXP_MATCH_PROMPT
    start = time.monotonic()
    try:
        result = await _invoke_agent(prompt, resume_text, jd_text, mode)
        match_agent_duration_seconds.labels(agent="exp").observe(time.monotonic() - start)
        return {"_exp_result": result}
    except Exception as e:
        logger.error(f"经验评估失败: {e}")
        match_agent_duration_seconds.labels(agent="exp").observe(time.monotonic() - start)
        return {"_exp_result": {"error": str(e)}}


async def _risk_agent_node(state: AgentState) -> dict:
    """风险评估（根据 match_mode 切换视角）"""
    update_trace_context(intent_type="MATCH_RISK", call_purpose="risk_eval")
    resume_text = state.get("_resume_text", "")
    jd_text = state.get("jd_text", "")
    mode = state.get("match_mode", "recruiter")
    prompt = CANDIDATE_RISK_PROMPT if mode == "candidate" else RISK_ASSESS_PROMPT
    start = time.monotonic()
    try:
        result = await _invoke_agent(prompt, resume_text, jd_text, mode)
        match_agent_duration_seconds.labels(agent="risk").observe(time.monotonic() - start)
        return {"_risk_result": result}
    except Exception as e:
        logger.error(f"风险评估失败: {e}")
        match_agent_duration_seconds.labels(agent="risk").observe(time.monotonic() - start)
        return {"_risk_result": {"error": str(e)}}


async def _summarize_node(state: AgentState) -> dict:
    """汇总：加权平均 + 生成 Markdown 报告（根据 match_mode 切换格式）"""
    tech = state.get("_tech_result", {})
    exp = state.get("_exp_result", {})
    risk = state.get("_risk_result", {})
    resume_name = state.get("resume_filename", "")
    mode = state.get("match_mode", "recruiter")

    # 文档缺失等前置错误：直接返回 _fanout_decision 设置的错误消息
    if tech.get("error") and exp.get("error") and risk.get("error"):
        match_total.labels(mode=mode, result="error").inc()
        return {
            "match_report": state.get("match_report", ""),
            "final_score": 0.0,
            "messages": state.get("messages", []),
        }

    tech_score = tech.get("score", 0)
    exp_score = exp.get("score", 0)
    risk_score = risk.get("score", 0)

    if isinstance(tech_score, str):
        tech_score = 0
    if isinstance(exp_score, str):
        exp_score = 0
    if isinstance(risk_score, str):
        risk_score = 0

    final = round(float(tech_score) * 0.40 + float(exp_score) * 0.35 + float(risk_score) * 0.25, 1)

    match_total.labels(mode=mode, result="success").inc()
    match_score_distribution.observe(final)

    if mode == "candidate":
        report = summarize_candidate_results(tech, exp, risk, resume_name or "")
    else:
        report = summarize_results(tech, exp, risk, resume_name or "")

    return {
        "match_report": report,
        "final_score": final,
        "messages": state.get("messages", []),
    }


# ==================== 图构建 ====================


def create_match_workflow() -> StateGraph:
    """创建简历匹配子图（fan-out 并行评估）"""
    workflow = StateGraph(AgentState)

    workflow.add_node("fetch_docs", _fetch_docs_node)
    workflow.add_node("tech_agent", _tech_agent_node)
    workflow.add_node("exp_agent", _exp_agent_node)
    workflow.add_node("risk_agent", _risk_agent_node)
    workflow.add_node("summarize", _summarize_node)

    workflow.set_entry_point("fetch_docs")
    workflow.add_conditional_edges("fetch_docs", _fanout_decision, ["tech_agent", "exp_agent", "risk_agent", "summarize"])
    workflow.add_edge("tech_agent", "summarize")
    workflow.add_edge("exp_agent", "summarize")
    workflow.add_edge("risk_agent", "summarize")
    workflow.add_edge("summarize", END)

    return workflow


# 编译子图
match_app = create_match_workflow().compile()


async def run_match(
    resume_filename: str,
    jd_text: str,
    user_id: str = "test",
) -> dict:
    """运行简历匹配的便捷入口"""
    import uuid

    sid = f"match_{uuid.uuid4().hex[:8]}"
    trace_id = uuid.uuid4().hex
    set_trace_context(
        trace_id=trace_id,
        session_id=sid,
        user_id=user_id,
    )

    initial_state: AgentState = {
        "messages": [],
        "user_id": user_id,
        "session_id": f"match_{uuid.uuid4().hex[:8]}",
        "trace_id": uuid.uuid4().hex,
        "current_tool": "",
        "tool_results": {},
        "tool_chain": [],
        "token_usage": {},
        "stream_chunks": [],
        "intent": "match",
        "interrupt_required": False,
        "resume_filename": resume_filename,
        "jd_text": jd_text,
        "match_report": None,
        "final_score": None,
        "match_mode": "recruiter",
    }

    result = await match_app.ainvoke(initial_state)
    return result
