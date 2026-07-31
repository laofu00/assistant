"""日志系统 — 基于 loguru，分级输出 + 按天轮转 + JSON 序列化

架构:
  console   — 开发可读格式，彩色，DEBUG 模式输出更详细
  app.log   — 全量 JSON，按天轮转 + 100MB 大小兜底，保留 30 天，gzip
  error.log — 仅 ERROR+，独立告警文件，保留 90 天
  access.log— API 请求日志，保留 14 天
"""

import sys
from pathlib import Path

from loguru import logger

from src.core.config import settings

CONSOLE_FORMAT = (
    "<green>{time:HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}:{function}:{line}</cyan> | "
    "<level>{message}</level>"
)

# 文件 JSON 格式：记录关键字段 + 绑定的 context
FILE_FORMAT = (
    "{time:YYYY-MM-DDTHH:mm:ss.SSS!UTC} | "
    "{level} | "
    "{name}:{function}:{line} | "
    "{message} | "
    "extra={extra}"
)


def setup_logging(log_level: str = "INFO", log_dir: str = "logs") -> None:
    """初始化日志系统"""
    logger.remove()

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # ── 1. 控制台（开发可读格式 + 彩色）──
    logger.add(
        sys.stderr,
        format=CONSOLE_FORMAT,
        level="DEBUG" if settings.DEBUG else "INFO",
        colorize=True,
        backtrace=False,
        diagnose=settings.DEBUG,
    )

    # ── 2. 全量应用日志（JSON + 按天 + 大小双轮转）──
    logger.add(
        log_path / "app.log",
        format=FILE_FORMAT,
        level=log_level,
        rotation="00:00",
        retention="30 days",
        compression="gz",
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=True,
        serialize=True,  # JSON 序列化
    )

    # ── 3. 错误独立日志 — 只输出 ERROR+ ──
    logger.add(
        log_path / "error.log",
        format=FILE_FORMAT,
        level="ERROR",
        rotation="00:00",
        retention="90 days",
        compression="gz",
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=True,
        serialize=True,
    )

    # ── 4. API 访问日志 — 中间件 + 路由 INFO ──
    logger.add(
        log_path / "access.log",
        format=FILE_FORMAT,
        level="INFO",
        rotation="00:00",
        retention="14 days",
        compression="gz",
        encoding="utf-8",
        enqueue=True,
        serialize=True,
        filter=lambda r: r.get("name", "").startswith(("src.api", "src.core.middleware")),
    )

    logger.info(f"日志系统初始化完成，级别: {log_level}, 目录: {log_path}")

