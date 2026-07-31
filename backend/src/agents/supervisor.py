"""Supervisor 意图分类节点 — 轻量 LLM 调用，分类用户意图

输出 JSON {"intent": "match|general", "resume_file": "...", "jd_file": "..."}
"""

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from src.core.config import settings
from src.core.llm_factory import get_llm, update_trace_context
from src.models.state import AgentState

SUPERVISOR_PROMPT = """你是一个智能路由助手，判断用户意图。

## 意图类别

### match（简历匹配）
用户想匹配简历和JD。从消息中提取：resume_file、jd_file、jd_text、match_mode。
- match_mode: "candidate"（求职者要分析自己、"帮我分析""我的优势""怎么准备"）或 "recruiter"（招聘方评估候选人、默认值）

### general（通用对话）
其他所有请求（知识库、备忘录、邮件、日期、闲聊等）。

## 输出
只输出 JSON（不要任何解释）：
{"intent":"match","resume_file":"...","jd_file":"...","jd_text":"...","match_mode":"recruiter|candidate"}

或 {"intent":"general"}"""


def create_supervisor_node():
    """创建 Supervisor 意图分类节点"""
    llm = get_llm(temperature=0, streaming=False, model=settings.MODEL_NAME_LIGHT)

    async def supervisor_node(state: AgentState) -> dict:
        """分析用户意图，返回分类结果"""
        update_trace_context(intent_type="SUPERVISOR", call_purpose="intent_classify")
        messages = state["messages"]
        if not messages:
            return {"intent": "general"}

        # 取最后一条用户消息
        last_msg = messages[-1]
        content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

        # 简单关键词快速匹配（减少 LLM 调用）
        match_keywords = [
            "匹配", "简历匹配", "岗位匹配", "评估匹配", "对比简历", "适合这个岗位",
            "匹配度", "帮我分析", "怎么准备", "评估", "候选人", "简历", "面试", "岗位",
        ]
        is_fast_match = any(kw in str(content) for kw in match_keywords)

        # 候选视角快速判断
        candidate_keywords = ["帮我分析", "我适合", "怎么准备", "我的优势", "我的不足", "面试准备", "我能做什么"]
        is_candidate = any(kw in str(content) for kw in candidate_keywords)

        if not is_fast_match:
            logger.debug("Supervisor 快速分类: general（无匹配关键词）")
            return {"intent": "general"}

        # 有匹配关键词时才调用 LLM 精确分类
        try:
            response = await llm.ainvoke([
                SystemMessage(content=SUPERVISOR_PROMPT),
                HumanMessage(content=f"用户消息：{content}"),
            ])
            result_text = response.content
            if not isinstance(result_text, str):
                return {"intent": "general"}

            # 提取 JSON
            json_match = re.search(r"\{[^{}]*\}", result_text)
            if not json_match:
                return {"intent": "general"}

            parsed = json.loads(json_match.group())
            intent = parsed.get("intent", "general")
            match_mode = parsed.get("match_mode", "candidate" if is_candidate else "recruiter")

            logger.info(f"Supervisor 分类: intent={intent}, mode={match_mode}")

            return {
                "intent": intent,
                "resume_filename": parsed.get("resume_file") or state.get("resume_filename"),
                "jd_text": parsed.get("jd_text") or parsed.get("jd_file") or state.get("jd_text"),
                "match_mode": match_mode,
            }
        except Exception as e:
            logger.warning(f"Supervisor LLM 调用失败: {e}，默认为 general")
            return {"intent": "general"}

    return supervisor_node
