"""简历匹配多智能体 — TechMatchAgent + ExpMatchAgent + RiskAssessAgent 并行评估

三个 Agent 通过 LangGraph Send 机制并行执行，汇总节点加权平均生成 Markdown 报告。
"""

import json
import re

from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from src.core.config import settings

# ==================== System Prompts ====================

TECH_MATCH_PROMPT = """你是资深技术面试官，负责评估候选人的技术匹配度。

请对照JD（岗位描述）的技术栈要求，逐项核对简历中的技能：
1. 列出JD要求的关键技术栈
2. 逐项确认简历中是否具备对应的技能（具备/部分具备/缺失）
3. 综合技术栈匹配程度，给出1-10分的评分

评分标准：
- 9-10分：技术栈完全匹配，核心技术全部具备且有深度
- 7-8分：核心技术大部分匹配，缺少1-2项非关键技能
- 5-6分：部分匹配，缺少2-4项关键技能
- 3-4分：匹配度较低，核心技术多数缺失
- 1-2分：几乎不匹配

**重要**：只依据提供的简历和JD文本作答，禁止补充外部知识。不要假设候选人具备文本中未提及的技能。

输出格式（JSON）：
{"score": 8, "reason": "详细评估理由", "matched_skills": ["技能1", "技能2"], "missing_skills": ["缺失技能1"]}"""

EXP_MATCH_PROMPT = """你是业务负责人，负责评估候选人项目经验与JD职责的相关度。

请对照JD的职责要求，评估简历中的项目经验：
1. 行业领域是否匹配（如金融、电商、教育等）
2. 项目规模与复杂度是否满足JD要求
3. 使用的技术栈是否与JD一致
4. 项目中的角色和职责是否与JD要求匹配

评分标准：
- 9-10分：行业完全匹配，项目经验深度和广度均满足要求
- 7-8分：行业相关，项目经验基本满足
- 5-6分：行业部分相关，经验有差距
- 3-4分：行业不太相关，经验差异较大
- 1-2分：行业不相关，经验完全不匹配

**重要**：只依据提供的简历和JD文本作答，禁止补充外部知识。

输出格式（JSON）：
{"score": 7, "reason": "详细评估理由", "highlights": ["亮点1", "亮点2"], "gaps": ["差距1"]}"""

RISK_ASSESS_PROMPT = """你是HR，负责评估候选人的职业稳定性和综合风险。

请从以下维度评估简历：
1. 职业稳定性：跳槽频率（年均跳槽次数）、最近一份工作时长
2. 空窗期：是否存在较长的工作空窗期（3个月以上）
3. 学历背景：学历与JD要求是否匹配
4. 职业发展：职业路径是否合理，是否有成长性
5. 其他软性风险因素

评分标准：
- 9-10分：职业稳定，无空窗期，学历匹配，职业发展良好
- 7-8分：总体稳定，有轻微可接受的风险
- 5-6分：存在一定风险（如1次短期工作、小空窗期等）
- 3-4分：风险较高（频繁跳槽、较长空窗期、学历不匹配）
- 1-2分：高风险（极不稳定、长期空窗、学历严重不匹配）

**注意**：如果简历中未提及学历信息或跳槽频率，请在评估理由中说明"简历中未提及"，并基于已有信息给出保守评分。

输出格式（JSON）：
{"score": 6, "reason": "详细评估理由", "risks": ["风险1", "风险2"], "notes": "补充说明"}"""

# ==================== 候选人视角 Prompts ====================

CANDIDATE_TECH_PROMPT = """你是资深技术导师，正在帮一位求职者分析岗位JD，提供面试准备建议。

请对照JD的技术要求，分析简历中的技术储备：
1. 列出JD要求的关键技术栈
2. 逐项确认求职者已掌握哪些技能、哪些需要加强
3. 哪些技能在面试中要重点展示，哪些需要坦诚说明不熟悉
4. 给出面试技术准备建议

输出格式（JSON）：
{"score": 8, "reason": "详细分析说明", "strengths": ["优势技能1", "优势技能2"], "weaknesses": ["需加强的技能1"], "preparation_tips": ["准备建议1", "准备建议2"]}"""

CANDIDATE_EXP_PROMPT = """你是资深职业规划师，正在帮一位求职者对照JD准备面试话术。

请分析JD职责与求职者项目经验的匹配情况：
1. 求职者哪些项目经验最吻合JD要求，面试时要重点讲
2. 求职者经验中的短板如何用积极方式表述
3. 针对JD职责，准备STAR面试案例
4. 给出面试中展示个人价值的策略

输出格式（JSON）：
{"score": 7, "reason": "详细分析说明", "highlight_projects": ["可重点展示的项目1", "项目2"], "gap_strategies": ["短板应对策略1"], "star_examples": ["STAR案例1", "STAR案例2"]}"""

CANDIDATE_RISK_PROMPT = """你是资深HR面试教练，帮求职者分析在面试中可能面临的质疑点，提前准备应对策略。

请分析求职者在面试中可能被质疑的方面：
1. 职业稳定性：跳槽频率、最近工作时长是否会被追问
2. 空窗期：是否存在，如何合理解释
3. 学历背景：与JD要求是否匹配
4. 职业发展：路径是否清晰，换方向的原因如何表述
5. 其他软性风险及应对

输出格式（JSON）：
{"score": 8, "reason": "详细分析说明", "risks": ["可能的质疑点1", "质疑点2"], "response_strategies": ["应对策略1", "策略2"], "overall_advice": "整体面试策略建议"}"""

# ==================== LLM 调用 ====================

def _create_llm() -> ChatTongyi:
    return ChatTongyi(
        model=settings.MODEL_NAME,
        dashscope_api_key=settings.OPENAI_API_KEY,
        temperature=0,  # 评分场景要求可重现
    )


async def _invoke_agent(system_prompt: str, resume_text: str, jd_text: str, mode: str = "recruiter") -> dict:
    """调用单个 Agent，返回 parsed JSON"""
    llm = _create_llm()
    if mode == "candidate":
        user_prompt = f"""请帮助这位求职者分析以下JD和简历，为面试准备提供建议。

===== 求职者简历 =====
{resume_text}

===== 岗位JD =====
{jd_text}

请严格按照要求的JSON格式输出分析结果和建议。"""
    else:
        user_prompt = f"""请评估以下简历与JD的匹配度。

===== 简历内容 =====
{resume_text}

===== JD内容 =====
{jd_text}

请严格按照要求的JSON格式输出评估结果。"""

    try:
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        content = response.content
        if not isinstance(content, str):
            return {"error": "LLM 返回非文本内容"}

        # 提取 JSON（可能包裹在 markdown 代码块中）
        json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return {"error": "无法解析 JSON", "raw": content[:200]}
    except json.JSONDecodeError as e:
        logger.error(f"Agent JSON 解析失败: {e}")
        return {"error": f"JSON 解析失败: {e}"}
    except Exception as e:
        logger.error(f"Agent 调用失败: {e}")
        return {"error": str(e)}


# ==================== 汇总 ====================

# 权重
W_TECH = 0.40
W_EXP = 0.35
W_RISK = 0.25


def summarize_results(tech: dict, exp: dict, risk: dict, resume_name: str = "") -> str:
    """加权汇总，生成 Markdown 评估报告"""
    tech_score = _safe_score(tech)
    exp_score = _safe_score(exp)
    risk_score = _safe_score(risk)

    final = round(tech_score * W_TECH + exp_score * W_EXP + risk_score * W_RISK, 1)

    if final >= 8:
        decision = "匹配度高，建议面试"
    elif final >= 5:
        decision = "部分匹配，可考虑"
    else:
        decision = "匹配度低，建议放弃"

    report = f"""# 岗位匹配度评估报告

{f"**简历**：{resume_name}  " if resume_name else ""}
**评估模型**：{settings.MODEL_NAME}

---

## 综合评分：{final} / 10

### 结论：{decision}

---

## 各维度明细

### 技术匹配：{tech_score} / 10（权重 {int(W_TECH * 100)}%）
{_format_agent_section(tech, "matched_skills", "missing_skills")}

### 经验匹配：{exp_score} / 10（权重 {int(W_EXP * 100)}%）
{_format_agent_section(exp, "highlights", "gaps")}

### 风险评估：{risk_score} / 10（权重 {int(W_RISK * 100)}%）
{_format_risk_section(risk)}

---

## 综合评价

- 技术维度权重 {int(W_TECH * 100)}%：{"技术匹配度" if tech_score >= 7 else "技术存在" if tech_score >= 5 else "技术"} {"高" if tech_score >= 7 else "中等" if tech_score >= 5 else "不足"}
- 经验维度权重 {int(W_EXP * 100)}%：{"经验匹配度" if exp_score >= 7 else "经验" if exp_score >= 5 else "经验"} {"高" if exp_score >= 7 else "中等" if exp_score >= 5 else "不足"}
- 风险维度权重 {int(W_RISK * 100)}%：综合风险{"较低" if risk_score >= 7 else "中等" if risk_score >= 5 else "较高"}

## 建议

{_generate_recommendations(tech_score, exp_score, risk_score, final)}
"""
    return report


def _safe_score(result: dict) -> float:
    """安全获取评分，默认 5 分"""
    score = result.get("score", 5)
    if isinstance(score, (int, float)):
        return float(max(1, min(10, score)))
    return 5.0


def _format_agent_section(result: dict, positive_key: str, negative_key: str) -> str:
    """格式化 Agent 评估结果"""
    lines = [f"**评估理由**：{result.get('reason', 'N/A')}", ""]
    items = result.get(positive_key, [])
    if items:
        lines.append(f"**{_key_label(positive_key)}**：")
        for item in items:
            lines.append(f"- ✅ {item}")
    items2 = result.get(negative_key, [])
    if items2:
        lines.append(f"**{_key_label(negative_key)}**：")
        for item in items2:
            lines.append(f"- ❌ {item}")
    return "\n".join(lines) if len(lines) > 1 else "无详细信息"


def _format_risk_section(result: dict) -> str:
    """格式化风险评估结果"""
    lines = [f"**评估理由**：{result.get('reason', 'N/A')}", ""]
    risks = result.get("risks", [])
    if risks:
        lines.append("**风险点**：")
        for r in risks:
            lines.append(f"- ⚠️ {r}")
    notes = result.get("notes", "")
    if notes:
        lines.append(f"\n**备注**：{notes}")
    return "\n".join(lines)


def _key_label(key: str) -> str:
    labels = {
        "matched_skills": "匹配技能",
        "missing_skills": "缺失技能",
        "highlights": "亮点",
        "gaps": "差距",
    }
    return labels.get(key, key)


def _generate_recommendations(tech: float, exp: float, risk: float, final: float) -> str:
    """生成建议"""
    recs = []
    if final >= 8:
        recs.append("该候选人与岗位匹配度高，建议尽快安排面试。重点关注其过往项目中的技术深度和团队协作能力。")
    elif final >= 5:
        recs.append("该候选人部分匹配岗位要求。")
        if tech < 7:
            recs.append("- 技术方面存在差距，面试中重点考察其学习能力和技术广度。")
        if exp < 7:
            recs.append("- 经验方面有提升空间，可了解其过往项目中是否具备可迁移的能力。")
        if risk < 7:
            recs.append("- 存在一定职业风险因素，面试时需了解其职业规划。")
    else:
        recs.append("该候选人与岗位匹配度较低，建议放弃或安排初筛电话沟通确认其实际情况。")

    recs.append(f"\n---\n*报告由 Smart Assistant 自动生成，评估模型：{settings.MODEL_NAME}*")
    return "\n".join(recs)


# ==================== 候选人视角汇总 ====================


def summarize_candidate_results(tech: dict, exp: dict, risk: dict, resume_name: str = "") -> str:
    """加权汇总，生成候选人视角 Markdown 面试准备报告"""
    tech_score = _safe_score(tech)
    exp_score = _safe_score(exp)
    risk_score = _safe_score(risk)

    final = round(tech_score * W_TECH + exp_score * W_EXP + risk_score * W_RISK, 1)

    if final >= 8:
        decision = "竞争力强，积极争取"
    elif final >= 5:
        decision = "有竞争力，充分准备面试"
    else:
        decision = "岗位要求有较大差距，建议合理选择目标"

    report = f"""# 面试准备报告

{f"**简历**：{resume_name}  " if resume_name else ""}
**评估模型**：{settings.MODEL_NAME}

---

## 综合竞争力评分：{final} / 10

### 结论：{decision}

---

## 各维度分析

### 技术准备：{tech_score} / 10（权重 {int(W_TECH * 100)}%）
{_format_candidate_tech_section(tech)}

### 经验匹配：{exp_score} / 10（权重 {int(W_EXP * 100)}%）
{_format_candidate_exp_section(exp)}

### 风险应对：{risk_score} / 10（权重 {int(W_RISK * 100)}%）
{_format_candidate_risk_section(risk)}

---

## 面试策略总结

- 技术方面：{"充分展示技术深度" if tech_score >= 7 else "坦诚沟通，突出学习能力" if tech_score >= 5 else "明确表达学习意愿与转型决心"}
- 经验方面：{"重点讲与JD匹配的核心项目" if exp_score >= 7 else "强调可迁移能力和快速上手能力" if exp_score >= 5 else "突出个人成长性和相关技能"}
- 风险方面：{"面试表现自信稳定" if risk_score >= 7 else "提前准备好质疑点的回应" if risk_score >= 5 else "重点准备空窗/跳槽等敏感问题的合理解释"}

## 建议

{_generate_candidate_recommendations(tech_score, exp_score, risk_score, final)}
"""
    return report


def _format_candidate_tech_section(result: dict) -> str:
    lines = [f"**分析**：{result.get('reason', 'N/A')}", ""]
    strengths = result.get("strengths", [])
    if strengths:
        lines.append("**面试中要重点展示的技能**：")
        for s in strengths:
            lines.append(f"- ✅ {s}")
    weaknesses = result.get("weaknesses", [])
    if weaknesses:
        lines.append("**需要加强或坦诚说明的技能**：")
        for w in weaknesses:
            lines.append(f"- ⚠️ {w}")
    tips = result.get("preparation_tips", [])
    if tips:
        lines.append("**技术准备建议**：")
        for t in tips:
            lines.append(f"- 💡 {t}")
    return "\n".join(lines) if len(lines) > 1 else "无详细信息"


def _format_candidate_exp_section(result: dict) -> str:
    lines = [f"**分析**：{result.get('reason', 'N/A')}", ""]
    projects = result.get("highlight_projects", [])
    if projects:
        lines.append("**面试重点展示的项目**：")
        for p in projects:
            lines.append(f"- ✅ {p}")
    gaps = result.get("gap_strategies", [])
    if gaps:
        lines.append("**短板应对策略**：")
        for g in gaps:
            lines.append(f"- 💡 {g}")
    stars = result.get("star_examples", [])
    if stars:
        lines.append("**可准备的STAR案例**：")
        for s in stars:
            lines.append(f"- 📋 {s}")
    return "\n".join(lines) if len(lines) > 1 else "无详细信息"


def _format_candidate_risk_section(result: dict) -> str:
    lines = [f"**分析**：{result.get('reason', 'N/A')}", ""]
    risks = result.get("risks", [])
    if risks:
        lines.append("**面试中可能被质疑的点**：")
        for r in risks:
            lines.append(f"- ⚠️ {r}")
    strategies = result.get("response_strategies", [])
    if strategies:
        lines.append("**应对策略**：")
        for s in strategies:
            lines.append(f"- 💡 {s}")
    advice = result.get("overall_advice", "")
    if advice:
        lines.append(f"\n**整体建议**：{advice}")
    return "\n".join(lines)


def _generate_candidate_recommendations(tech: float, exp: float, risk: float, final: float) -> str:
    recs = []
    if final >= 8:
        recs.append("你的竞争力很强，面试中要自信展示。重点突出技术深度和项目价值，准备1-2个有亮点的STAR案例。")
    elif final >= 5:
        recs.append("你的基础不错，做好充分准备完全有机会。")
        if tech < 7:
            recs.append("- 技术方面有1-2项不熟悉是正常的，诚实表达学习意愿+展示快速学习案例。")
        if exp < 7:
            recs.append("- 经验不完全对口时，强调你的可迁移能力和对新领域的学习热情。")
        if risk < 7:
            recs.append("- 提前准备好空窗期或跳槽等问题的回答话术，化被动为主动。")
    else:
        recs.append("这个岗位要求较高，建议考虑以下策略：")
        recs.append("- 重点准备简历中与JD重叠的部分，最大化展示匹配点。")
        recs.append("- 也可以同时关注要求稍低的相邻岗位，积累经验后再冲刺。")

    recs.append(f"\n---\n*报告由 Smart Assistant 自动生成，评估模型：{settings.MODEL_NAME}*")
    return "\n".join(recs)
