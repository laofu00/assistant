#!/usr/bin/env python
"""数据库初始化脚本 — 调用 Alembic 迁移"""

import asyncio
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent.parent))

from alembic import command
from alembic.config import Config


def main() -> None:
    alembic_cfg = Config(str(Path(__file__).parent.parent / "alembic" / "alembic.ini"))
    command.upgrade(alembic_cfg, "head")
    print("数据库迁移完成")


if __name__ == "__main__":
    main()
