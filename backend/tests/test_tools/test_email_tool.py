"""tools/email_tool.py 邮件工具测试（3个）"""

from unittest.mock import patch


class TestPreviewEmail:
    async def test_returns_preview(self) -> None:
        from src.tools.email_tool import preview_email
        result = await preview_email.ainvoke({"to": "user@example.com", "subject": "测试邮件", "body": "这是正文"})
        assert "收件人" in result
        assert "user@example.com" in result
        assert "测试邮件" in result
        assert "确认" in result

    async def test_html_flag(self) -> None:
        from src.tools.email_tool import preview_email
        result = await preview_email.ainvoke({"to": "a@b.com", "subject": "s", "body": "b", "html": False})
        assert "收件人" in result


class TestDoSendEmail:
    async def test_send_success(self) -> None:
        from src.tools.email_tool import do_send_email
        with patch("src.tools.email_tool._send_smtp", return_value="邮件已发送至 a@b.com，主题：test"):
            result = await do_send_email.ainvoke({"to": "a@b.com", "subject": "test", "body": "hello"})
            assert "已发送" in result

    async def test_multiple_recipients(self) -> None:
        from src.tools.email_tool import do_send_email
        with patch("src.tools.email_tool._send_smtp", return_value="邮件已发送至 a@b.com,c@d.com，主题：m"):
            result = await do_send_email.ainvoke({"to": "a@b.com, c@d.com", "subject": "m", "body": "body"})
            assert "已发送" in result

    async def test_empty_recipients(self) -> None:
        from src.tools.email_tool import do_send_email
        result = await do_send_email.ainvoke({"to": "  ,  ", "subject": "s", "body": "b"})
        assert "不能为空" in result

    async def test_send_failure(self) -> None:
        from src.tools.email_tool import do_send_email
        with patch("src.tools.email_tool._send_smtp", side_effect=Exception("SMTP down")):
            result = await do_send_email.ainvoke({"to": "a@b.com", "subject": "s", "body": "b"})
            assert "失败" in result


class TestDoSendFormattedEmail:
    async def test_send_success(self) -> None:
        from src.tools.email_tool import do_send_formatted_email
        items = '[{"itemTitle":"任务1","itemText":"详情1"}]'
        with patch("src.tools.email_tool._send_smtp", return_value="邮件已发送至 a@b.com，主题：日报"):
            result = await do_send_formatted_email.ainvoke({
                "to": "a@b.com", "subject": "日报", "title": "每日报告",
                "summary": "今日摘要", "content_items": items, "user_id": "u1",
            })
            assert "已发送" in result

    async def test_invalid_json(self) -> None:
        from src.tools.email_tool import do_send_formatted_email
        result = await do_send_formatted_email.ainvoke({
            "to": "a@b.com", "subject": "s", "title": "t", "summary": "m",
            "content_items": "not json", "user_id": "u1",
        })
        assert "格式错误" in result

    async def test_send_failure(self) -> None:
        from src.tools.email_tool import do_send_formatted_email
        items = '[{"itemTitle":"t","itemText":"d"}]'
        with patch("src.tools.email_tool._send_smtp", side_effect=Exception("SMTP auth failed")):
            result = await do_send_formatted_email.ainvoke({
                "to": "a@b.com", "subject": "s", "title": "t", "summary": "m",
                "content_items": items, "user_id": "u1",
            })
            assert "失败" in result


class TestBuildHtmlEmail:
    def test_escape_html(self) -> None:
        from src.tools.email_tool import _escape_html
        assert "<script>" not in _escape_html("<script>alert(1)</script>")

    def test_build_html_email(self) -> None:
        from src.tools.email_tool import _build_html_email
        items = [{"itemTitle": "任务A", "itemText": "完成开发"}]
        html = _build_html_email("周报", "本周总结", items)
        assert "周报" in html
        assert "任务A" in html
        assert "<!DOCTYPE html>" in html

    def test_build_html_no_summary(self) -> None:
        from src.tools.email_tool import _build_html_email
        items = [{"itemTitle": "T", "itemText": "D"}]
        html = _build_html_email("标题", None, items)
        assert "标题" in html
