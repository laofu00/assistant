"""Supervisor 意图分类节点 — 轻量 LLM 调用，分类用户意图

输出 JSON {"intent": "match|general", "resume_file": "...", "jd_file": "..."}
"""

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from src.core.llm_factory import get_llm, update_trace_context
from src.models.state import AgentState

SUPERVISOR_PROMPT = """你是一个智能路由助手。请分析用户的消息，判断其意图类别。

## 意图类别

### match（简历匹配）
用户想要匹配/评估简历和JD（岗位描述），关键词包括：
- "匹配"、"简历匹配"、"岗位匹配"、"评估匹配度"
- "对比简历和JD"、"帮我看看这个岗位"
- "我适合这个岗位吗"、"匹配度怎么样"
- "帮我分析"、"怎么准备面试"、"我的优势"、"我的不足"

如果识别为 match，请从用户消息中提取并判断：
- resume_file：简历文件名（如 "my_resume.txt"），没有则留空
- jd_file：JD文件名（如 "jd_1.txt"），没有则留空
- jd_text：用户直接粘贴的JD文本内容，没有则留空
- match_mode：视角类型
  - "candidate"（候选人视角）：用户以求职者身份分析，关键词包括"帮我分析"、"我适合"、"怎么准备"、"我的优势"、"我的不足"、"面试准备"、"我能做什么"
  - "recruiter"（招聘方视角）：用户以招聘方角度评估候选人，关键词包括"评估匹配度"、"这个候选人"、"帮我判断"、"是否合适"
  - 默认为 "recruiter"

### general（通用对话）
所有不属于简历匹配的请求，包括：
- 知识库检索、文档管理
- 备忘录创建、查询、管理
- 邮件发送
- 日期查询
- 其他日常对话

## 输出格式
只输出一个JSON对象，不要加任何解释：

{"intent": "match", "resume_file": "...", "jd_file": "...", "jd_text": "...", "match_mode": "recruiter|candidate"}

或

{"intent": "general"}"""


def create_supervisor_node():
    """创建 Supervisor 意图分类节点"""
    llm = get_llm(temperature=0, streaming=False)

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
        match_keywords = ["匹配", "简历匹配", "岗位匹配", "评估匹配", "对比简历", "适合这个岗位", "匹配度", "帮我分析", "怎么准备", "评估", "候选人", "简历", "面试", "岗位"]
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
