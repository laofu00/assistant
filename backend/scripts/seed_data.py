#!/usr/bin/env python
"""种子数据脚本 — 导入示例文档 + 创建示例备忘录"""

import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.database import async_session_factory
from src.models.memo import Memo


async def seed_memos() -> None:
    """创建 5 条示例备忘录"""
    today = date.today()
    test_data = [
        ("完成 AI Agent 开发文档", "完成智能助手 Python 重构的所有开发工作，并进行完整的单元测试和集成测试", "待办", today + timedelta(days=5)),
        ("团队周会", "讨论本周工作进展，分配下周任务，评审新功能设计方案", "工作", today + timedelta(days=1)),
        ("学习 LangGraph 框架", "阅读官方文档，完成教程中的 agent 和 supervisor 示例", "学习", today + timedelta(days=19)),
        ("张三个人生日", "准备生日礼物，晚上一起聚餐庆祝", "生活", today + timedelta(days=14)),
        ("紧急修复数据库连接池泄漏", "线上数据库连接池未正常释放，需要紧急排查并修复", "重要", today),
    ]

    async with async_session_factory() as session:
        for title, content, category, due_date in test_data:
            memo = Memo(
                user_id="test",
                title=title,
                content=content,
                category=category,
                due_date=due_date,
            )
            session.add(memo)
        await session.commit()
    print(f"已创建 {len(test_data)} 条示例备忘录")


async def main() -> None:
    await seed_memos()
    print("种子数据导入完成")


if __name__ == "__main__":
    asyncio.run(main())
