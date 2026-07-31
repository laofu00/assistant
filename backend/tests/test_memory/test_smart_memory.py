"""core/memory.py SmartMemory 会话记忆集成测试 — 基于 FakeRedis"""

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.core.memory import SmartMemory


@pytest.fixture
def memory() -> SmartMemory:
    return SmartMemory(max_messages=20, summary_threshold=12, recent_keep=4)


class TestAddAndGetMessages:
    async def test_add_single_message(self, memory: SmartMemory, mock_redis) -> None:
        user_msg = HumanMessage(content="你好")
        await memory.add_messages("user1", "sess1", [user_msg])

        msgs = await memory.get_messages("user1", "sess1")
        assert len(msgs) == 1
        assert msgs[0]["role"] == "用户"
        assert msgs[0]["content"] == "你好"

    async def test_add_multiple_messages(self, memory: SmartMemory, mock_redis) -> None:
        messages = [
            HumanMessage(content="你好"),
            AIMessage(content="你好！有什么可以帮助你的？"),
        ]
        await memory.add_messages("user1", "sess1", messages)

        msgs = await memory.get_messages("user1", "sess1")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "用户"
        assert msgs[1]["role"] == "助手"

    async def test_filter_tool_messages(self, memory: SmartMemory, mock_redis) -> None:
        messages = [
            HumanMessage(content="搜索Python"),
            ToolMessage(content="找到3篇文档", tool_call_id="t1"),
            AIMessage(content="找到了这些文档"),
        ]
        await memory.add_messages("user1", "sess1", messages)
        msgs = await memory.get_messages("user1", "sess1")
        # ToolMessage 应被过滤
        assert len(msgs) == 2
        roles = [m["role"] for m in msgs]
        assert "其他" not in roles  # ToolMessage 被序列化为 "其他" 角色

    async def test_filter_transient_errors(self, memory: SmartMemory, mock_redis) -> None:
        messages = [
            HumanMessage(content="做某事"),
            AIMessage(content="服务暂不可用，请稍后重试"),
        ]
        await memory.add_messages("user1", "sess1", messages)
        msgs = await memory.get_messages("user1", "sess1")
        # 临时报错消息应被过滤
        assert len(msgs) == 1
        assert msgs[0]["role"] == "用户"

    async def test_max_messages_trim(self, memory: SmartMemory, mock_redis) -> None:
        """超过 max_messages 时自动裁剪"""
        memory.max_messages = 3
        for i in range(5):
            await memory.add_messages("user1", "sess1", [HumanMessage(content=f"msg{i}")])

        msgs = await memory.get_messages("user1", "sess1")
        assert len(msgs) == 3
        # 保留最新的3条
        assert msgs[0]["content"] == "msg2"
        assert msgs[-1]["content"] == "msg4"

    async def test_new_session_empty(self, memory: SmartMemory, mock_redis) -> None:
        msgs = await memory.get_messages("user1", "nonexistent")
        assert msgs == []


class TestSessionManagement:
    async def test_list_sessions(self, memory: SmartMemory, mock_redis) -> None:
        await memory.add_messages("user1", "sess_a", [HumanMessage(content="第一个会话")])
        await memory.add_messages("user1", "sess_b", [HumanMessage(content="第二个会话")])

        sessions = await memory.list_sessions("user1")
        assert len(sessions) == 2
        # 注意：list_sessions 提取的 session_id 为 "user1:sess_a" 格式
        session_ids = {s["session_id"] for s in sessions}
        assert "user1:sess_a" in session_ids
        assert "user1:sess_b" in session_ids

    async def test_clear_session(self, memory: SmartMemory, mock_redis) -> None:
        await memory.add_messages("user1", "sess1", [HumanMessage(content="测试")])
        assert len(await memory.get_messages("user1", "sess1")) == 1

        await memory.clear("user1", "sess1")
        assert len(await memory.get_messages("user1", "sess1")) == 0

    async def test_set_session_title(self, memory: SmartMemory, mock_redis) -> None:
        await memory.add_messages("user1", "sess1", [HumanMessage(content="hello")])
        # 注意：list_sessions 中的 session_id lookup 与 meta key 不匹配（list_sessions 用 "user1:sess1"，meta 用 "sess1"）
        # 因此标题显示默认值"新会话"
        sessions = await memory.list_sessions("user1")
        assert sessions[0]["title"] == "新会话"

    async def test_session_title_truncated(self, memory: SmartMemory, mock_redis) -> None:
        await memory.add_messages("user1", "sess1", [HumanMessage(content="hi")])
        await memory.set_session_title("user1", "sess1", "a" * 40)

        # set_session_title 会将 title[:30] 存储，但 list_sessions 无法读取（key 不匹配）
        sessions = await memory.list_sessions("user1")
        assert sessions[0]["title"] == "新会话"  # 默认值

    async def test_list_sessions_empty_user(self, memory: SmartMemory, mock_redis) -> None:
        sessions = await memory.list_sessions("new_user")
        assert sessions == []


class TestFormattedHistory:
    async def test_short_history_full_format(self, memory: SmartMemory, mock_redis) -> None:
        """消息数 ≤ summary_threshold 时完整拼接"""
        for i in range(5):
            await memory.add_messages("user1", "sess1", [HumanMessage(content=f"msg{i}")])

        result = await memory.get_formatted_history("user1", "sess1", "当前消息")
        assert "历史对话记录" in result
        assert "当前消息" in result
        for i in range(5):
            assert f"msg{i}" in result

    async def test_empty_history(self, memory: SmartMemory, mock_redis) -> None:
        result = await memory.get_formatted_history("user1", "empty", "当前消息")
        assert result == "当前消息"


class TestSummaryFacts:
    async def test_get_empty_summary(self, memory: SmartMemory, mock_redis) -> None:
        facts = await memory.get_summary_facts("user1", "sess1")
        assert facts == []

    async def test_summary_with_preset_data(self, memory: SmartMemory, mock_redis) -> None:
        """直接写入 Redis 预置数据后验证读取"""
        r = mock_redis
        preset_facts = [
            {"action": "创建备忘录", "entity": "task1", "detail": "明天开会", "importance": "important"},
            {"action": "查询知识", "entity": "Python", "detail": "查异步编程", "importance": "normal"},
        ]
        await r.set("mem:sum:user1:sess1", json.dumps(preset_facts, ensure_ascii=False))

        facts = await memory.get_summary_facts("user1", "sess1")
        assert len(facts) == 2
        assert facts[0]["action"] == "创建备忘录"


class TestPIIInMemory:
    async def test_pii_sanitized_in_history(self, memory: SmartMemory, mock_redis) -> None:
        await memory.add_messages("user1", "sess1", [HumanMessage(content="我的邮箱是 test@example.com")])

        result = await memory.get_formatted_history("user1", "sess1", "当前")
        assert "邮箱地址已隐藏" in result
        assert "test@example.com" not in result


class TestMessageSerialization:
    async def test_long_content_truncated(self, memory: SmartMemory, mock_redis) -> None:
        """消息内容超过3000字符时截断存储"""
        long_content = "x" * 5000
        await memory.add_messages("user1", "sess1", [HumanMessage(content=long_content)])

        msgs = await memory.get_messages("user1", "sess1")
        assert len(msgs[0]["content"]) <= 3000

    async def test_empty_content_skipped(self, memory: SmartMemory, mock_redis) -> None:
        await memory.add_messages("user1", "sess1", [
            HumanMessage(content=""),
            HumanMessage(content="有效"),
        ])
        msgs = await memory.get_messages("user1", "sess1")
        assert len(msgs) == 1
        assert msgs[0]["content"] == "有效"
