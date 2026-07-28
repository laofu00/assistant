"""邮件工具 — @tool 封装（2 个方法）

对齐 Java 版 EmailTool：sendEmail + sendFormattedEmail（HTML 模板）
"""

import json
from typing import Any

import aiosmtplib
from email.message import EmailMessage
from langchain_core.tools import tool
from loguru import logger

from src.core.config import settings


def _escape_html(text: str) -> str:
    if not text:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;")


def _build_html_email(title: str, summary: str | None, items: list[dict[str, str]]) -> str:
    """构建 HTML 邮件模板（对齐 Java 版样式）"""
    html = """<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background-color:#f0f2f5;">
<div style="max-width:600px;margin:20px auto;font-family:Arial,'Microsoft YaHei',sans-serif;background:white;border-radius:8px;box-shadow:0 2px 12px rgba(0,0,0,0.1);">
<div style="background:linear-gradient(135deg,#4A90D9,#357ABD);color:white;padding:24px 30px;border-radius:8px 8px 0 0;">
<h2 style="margin:0;font-size:20px;font-weight:600;">"""
    html += _escape_html(title)
    html += "</h2></div>"
    if summary:
        html += f'<div style="background:#f0f7ff;padding:16px 30px;border-left:4px solid #4A90D9;margin:20px 30px 0;border-radius:4px;"><p style="margin:0;color:#555;font-size:14px;line-height:1.6;">{_escape_html(summary)}</p></div>'
    if items:
        for i, item in enumerate(items):
            bg = "#fff" if i % 2 == 0 else "#fafafa"
            item_title = _escape_html(item.get("itemTitle", ""))
            item_text = _escape_html(item.get("itemText", ""))
            html += f'<div style="background:{bg};padding:18px 30px;border-bottom:1px solid #eee;"><h3 style="margin:0 0 8px 0;color:#333;font-size:16px;">{item_title}</h3><p style="margin:0;color:#666;font-size:14px;line-height:1.8;white-space:pre-wrap;">{item_text}</p></div>'
    html += """<div style="text-align:center;padding:20px;color:#999;font-size:12px;"><p style="margin:0;">由 Smart Assistant 自动生成</p></div></div></body></html>"""
    return html


async def _send_smtp(to: str, subject: str, body: str, html: bool = True) -> str:
    """底层 SMTP 发送"""
    msg = EmailMessage()
    msg["From"] = settings.SMTP_USERNAME
    msg["To"] = to
    msg["Subject"] = subject

    if html:
        msg.set_content(body[:500], subtype="plain")
        msg.add_alternative(body, subtype="html")
    else:
        msg.set_content(body)

    if settings.SMTP_SSL:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USERNAME,
            password=settings.SMTP_PASSWORD,
            use_tls=True,
        )
    else:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USERNAME,
            password=settings.SMTP_PASSWORD,
            start_tls=settings.SMTP_STARTTLS,
        )

    return f"邮件已发送至 {to}，主题：{subject}"


@tool
async def preview_email(to: str, subject: str, body: str, html: bool = True) -> str:
    """【必须首先调用】预览邮件内容和收件人，展示给用户确认。调用后系统会中断等待用户回复"确认"或"取消"。

    Args:
        to: 收件人邮箱
        subject: 邮件主题
        body: 邮件正文
        html: 是否HTML格式
    """
    return (
        "*** 邮件预览 ***\n"
        f"收件人：{to}\n"
        f"主题：{subject}\n"
        f"正文：\n{body}\n\n"
        "---\n"
        "请回复 [确认发送] 或 [取消]"
    )


@tool
async def do_send_email(to: str, subject: str, body: str, html: bool = True) -> str:
    """【仅在用户确认后调用】执行真正的邮件发送。

    Args:
        to: 收件人邮箱（多个用逗号分隔）
        subject: 邮件主题
        body: 邮件正文（支持HTML格式）
        html: 是否以HTML格式发送（默认True）
    """
    recipients = [r.strip() for r in to.split(",") if r.strip()]
    if not recipients:
        return "收件人邮箱不能为空"

    try:
        logger.info(f"发送邮件: to={to}, subject={subject}")
        result = await _send_smtp(to, subject, body, html)
        return result
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")
        return f"邮件发送失败: {e}"


@tool
async def do_send_formatted_email(
    to: str, subject: str, title: str, summary: str, content_items: str, user_id: str
) -> str:
    """【仅在用户确认后调用】执行真正的格式化HTML邮件发送。

    Args:
        to: 收件人邮箱
        subject: 邮件主题
        title: 邮件大标题
        summary: 邮件摘要
        content_items: JSON数组 [{"itemTitle":"...","itemText":"..."}]
        user_id: 当前用户ID
    """
    try:
        items: list[dict[str, str]] = json.loads(content_items)
    except json.JSONDecodeError as e:
        return f"content_items 格式错误: {e}"

    try:
        html_body = _build_html_email(title, summary, items)
        logger.info(f"发送格式化邮件: to={to}, subject={subject}, user={user_id}")
        result = await _send_smtp(to, subject, html_body, html=True)
        return result
    except Exception as e:
        logger.error(f"格式化邮件发送失败: {e}")
        return f"邮件发送失败: {e}"
