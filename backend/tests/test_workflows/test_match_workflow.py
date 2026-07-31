"""workflows/match_workflow.py 简历匹配子图测试 — mock ChromaDB + LLM"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.state import AgentState


def make_state(**overrides) -> AgentState:
    state: AgentState = {
        "messages": [],
        "user_id": "test_user_match",
        "session_id": "match_test",
        "trace_id": "trace_match",
        "current_tool": "",
        "tool_results": {},
        "tool_chain": [],
        "token_usage": {},
        "stream_chunks": [],
        "intent": "match",
        "interrupt_required": False,
        "resume_filename": "resume.pdf",
        "jd_text": "Python后端工程师JD，要求3年以上经验，熟悉FastAPI和PostgreSQL",
        "match_report": None,
        "final_score": None,
        "match_mode": "recruiter",
        "_resume_text": "张三的简历，5年Python开发经验，熟悉FastAPI、Django、PostgreSQL、Redis",
        "_tech_result": None,
        "_exp_result": None,
        "_risk_result": None,
    }
    state.update(overrides)
    return state


# ==================== Fetch Docs ====================


class TestFetchDocs:
    async def test_fetch_resume_from_chroma(self) -> None:
        from src.workflows.match_workflow import _fetch_docs_node

        mock_chunks = [{"text": "简历内容第1段"}, {"text": "简历内容第2段"}]
        mock_vs = MagicMock()
        mock_vs.get_by_filename = MagicMock(return_value=mock_chunks)

        with patch("src.workflows.match_workflow.vector_store", mock_vs):
            result = await _fetch_docs_node(make_state(
                resume_filename="resume.pdf",
                jd_text="Python工程师 JD",
            ))
            assert "_resume_text" in result
            assert "第1段" in result["_resume_text"]

    async def test_fetch_resume_not_found(self) -> None:
        from src.workflows.match_workflow import _fetch_docs_node

        mock_vs = MagicMock()
        mock_vs.get_by_filename = MagicMock(return_value=[])

        with patch("src.workflows.match_workflow.vector_store", mock_vs):
            result = await _fetch_docs_node(make_state(
                resume_filename="missing.pdf",
                jd_text="Python工程师 JD",
            ))
            assert result["_resume_text"] == ""

    async def test_no_resume_filename(self) -> None:
        from src.workflows.match_workflow import _fetch_docs_node

        result = await _fetch_docs_node(make_state(
            resume_filename=None,
            jd_text="Python工程师 JD",
        ))
        assert result["_resume_text"] == ""

    async def test_jd_from_file(self) -> None:
        """JD 以文件名形式提供时从 ChromaDB 读取"""
        from src.workflows.match_workflow import _fetch_docs_node

        mock_vs = MagicMock()
        mock_vs.get_by_filename = MagicMock(return_value=[{"text": "JD详细内容"}])

        with patch("src.workflows.match_workflow.vector_store", mock_vs):
            result = await _fetch_docs_node(make_state(
                resume_filename="r.pdf",
                jd_text="jd_content.pdf",  # 以 .pdf 结尾，触发文件模式
            ))
            assert "JD" in result["jd_text"]


# ==================== Fan-out Decision ====================


class TestFanoutDecision:
    def test_both_present(self) -> None:
        from src.workflows.match_workflow import _fanout_decision

        state = make_state(
            _resume_text="简历内容",
            jd_text="Python工程师，3年经验",
        )
        result = _fanout_decision(state)
        # 应该 fan-out 到 3 个 agent
        names = {s.node for s in result}
        assert names == {"tech_agent", "exp_agent", "risk_agent"}

    def test_no_resume(self) -> None:
        from src.workflows.match_workflow import _fanout_decision

        state = make_state(_resume_text="", jd_text="JD")
        result = _fanout_decision(state)
        assert len(result) == 1
        assert result[0].node == "summarize"
        assert "error" in result[0].arg["_tech_result"]

    def test_jd_too_short(self) -> None:
        from src.workflows.match_workflow import _fanout_decision

        state = make_state(_resume_text="简历", jd_text="短")
        result = _fanout_decision(state)
        assert len(result) == 1
        assert result[0].node == "summarize"


# ==================== Summarize Node ====================


class TestSummarizeNode:
    async def test_weighted_scoring_recruiter(self) -> None:
        """加权评分：tech 40% + exp 35% + risk 25%"""
        from src.workflows.match_workflow import _summarize_node

        state = make_state(
            resume_filename="resume.pdf",
            _tech_result={"score": 8, "reason": "技术匹配"},
            _exp_result={"score": 7, "reason": "经验相关"},
            _risk_result={"score": 6, "reason": "风险可控"},
        )
        result = await _summarize_node(state)

        # 加权：8*0.4 + 7*0.35 + 6*0.25 = 3.2 + 2.45 + 1.5 = 7.15 → 7.2 (四舍五入到1位)
        expected = round(8 * 0.40 + 7 * 0.35 + 6 * 0.25, 1)
        assert result["final_score"] == expected
        assert "match_report" in result

    async def test_string_scores_converted_to_zero(self) -> None:
        """字符串型分数自动转为 0"""
        from src.workflows.match_workflow import _summarize_node

        state = make_state(
            resume_filename="r.pdf",
            _tech_result={"score": "N/A"},
            _exp_result={"score": 7},
            _risk_result={"score": 6},
        )
        result = await _summarize_node(state)
        assert result["final_score"] == round(0 + 7 * 0.35 + 6 * 0.25, 1)

    async def test_all_agents_error(self) -> None:
        """三个 Agent 全部报错时返回 0 分"""
        from src.workflows.match_workflow import _summarize_node

        state = make_state(
            resume_filename="r.pdf",
            _tech_result={"error": "no_resume"},
            _exp_result={"error": "no_resume"},
            _risk_result={"error": "no_resume"},
            match_report="## 错误\n\n未找到简历内容",
        )
        result = await _summarize_node(state)
        assert result["final_score"] == 0.0

    async def test_candidate_mode(self) -> None:
        """候选视角的汇总逻辑"""
        from src.workflows.match_workflow import _summarize_node

        state = make_state(
            match_mode="candidate",
            resume_filename="resume.pdf",
            _tech_result={"score": 7, "reason": ""},
            _exp_result={"score": 8, "reason": ""},
            _risk_result={"score": 5, "reason": ""},
        )
        result = await _summarize_node(state)
        assert result["match_report"] != ""


# ==================== Match Agents ====================


class TestMatchAgents:
    async def test_tech_agent_recruiter(self) -> None:
        from src.workflows.match_workflow import _tech_agent_node

        mock_result = {"score": 8, "reason": "技术栈完全匹配", "matched_skills": ["Python", "FastAPI"], "missing_skills": []}

        with patch("src.workflows.match_workflow._invoke_agent", return_value=mock_result):
            result = await _tech_agent_node(make_state())
            assert result["_tech_result"]["score"] == 8
            assert "FastAPI" in result["_tech_result"]["matched_skills"]

    async def test_tech_agent_candidate_mode(self) -> None:
        from src.workflows.match_workflow import _tech_agent_node

        mock_result = {"score": 7, "reason": "", "strengths": ["Python"], "gaps": ["Go"]}

        with patch("src.workflows.match_workflow._invoke_agent", return_value=mock_result):
            result = await _tech_agent_node(make_state(match_mode="candidate"))
            assert result["_tech_result"]["score"] == 7

    async def test_tech_agent_failure(self) -> None:
        from src.workflows.match_workflow import _tech_agent_node

        with patch("src.workflows.match_workflow._invoke_agent", side_effect=Exception("LLM timeout")):
            result = await _tech_agent_node(make_state())
            assert "error" in result["_tech_result"]

    async def test_exp_agent(self) -> None:
        from src.workflows.match_workflow import _exp_agent_node

        with patch("src.workflows.match_workflow._invoke_agent", return_value={"score": 7, "reason": ""}):
            result = await _exp_agent_node(make_state())
            assert result["_exp_result"]["score"] == 7

    async def test_risk_agent(self) -> None:
        from src.workflows.match_workflow import _risk_agent_node

        with patch("src.workflows.match_workflow._invoke_agent", return_value={"score": 6, "reason": ""}):
            result = await _risk_agent_node(make_state())
            assert result["_risk_result"]["score"] == 6

    async def test_invoke_agent_function(self) -> None:
        """测试 _invoke_agent 核心调用逻辑"""
        from src.agents.match_agents import _invoke_agent

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content='{"score": 9, "reason": "优秀"}'))

        with patch("src.agents.match_agents.get_llm", return_value=mock_llm):
            result = await _invoke_agent("test prompt", "resume text", "jd text", "recruiter")
            assert result["score"] == 9

    async def test_invoke_agent_no_json(self) -> None:
        """LLM 返回无 JSON 时降级"""
        from src.agents.match_agents import _invoke_agent

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="这个候选人不错"))

        with patch("src.agents.match_agents.get_llm", return_value=mock_llm):
            result = await _invoke_agent("prompt", "resume", "jd", "recruiter")
            assert "error" in result

    async def test_invoke_agent_exception(self) -> None:
        """LLM 异常时降级"""
        from src.agents.match_agents import _invoke_agent

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("API error"))

        with patch("src.agents.match_agents.get_llm", return_value=mock_llm):
            result = await _invoke_agent("prompt", "resume", "jd", "recruiter")
            assert "error" in result


# ==================== Match Workflow Graph ====================


class TestMatchWorkflowGraph:
    def test_create_workflow_nodes(self) -> None:
        from src.workflows.match_workflow import create_match_workflow

        wf = create_match_workflow()
        nodes = set(wf.nodes.keys())
        expected = {"fetch_docs", "tech_agent", "exp_agent", "risk_agent", "summarize"}
        assert expected.issubset(nodes)


class TestSummarizeFunctions:
    def test_summarize_results(self) -> None:
        from src.agents.match_agents import summarize_results

        tech = {"score": 8, "reason": "技术匹配", "matched_skills": ["Python"], "missing_skills": []}
        exp = {"score": 7, "reason": "经验相关", "highlights": ["5年经验"]}
        risk = {"score": 6, "reason": "风险可控", "risks": []}
        report = summarize_results(tech, exp, risk, "resume.pdf")
        assert "技术" in report or "经验" in report or "风险" in report

    def test_summarize_candidate_results(self) -> None:
        from src.agents.match_agents import summarize_candidate_results

        tech = {"score": 7, "strengths": ["Python"], "gaps": []}
        exp = {"score": 8, "strengths": ["项目管理"]}
        risk = {"score": 5, "risks": ["跨行业"]}
        report = summarize_candidate_results(tech, exp, risk, "resume.pdf")
        assert isinstance(report, str)
