"""日志系统 — 基于 loguru，控制台可读格式 + 文件 JSON 序列化"""

import sys
from pathlib import Path

from loguru import logger

CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<level>{message}</level>"
)


def setup_logging(log_level: str = "INFO", log_dir: str = "logs") -> None:
    """初始化日志系统"""
    logger.remove()

    # 控制台输出（可读格式 + 彩色）
    logger.add(
        sys.stderr,
        format=CONSOLE_FORMAT,
        level=log_level,
        colorize=True,
    )

    # 文件输出（loguru serialize=True 直接输出 JSON）
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    logger.add(
        log_path / "app.log",
        format="{time:YYYY-MM-DDTHH:mm:ss.SSS} | {level} | {name}:{function}:{line} | {message}",
        level=log_level,
        rotation="00:00",
        retention="30 days",
        compression="gz",
        encoding="utf-8",
        enqueue=True,
        serialize=True,
    )

    logger.info(f"日志系统初始化完成，级别: {log_level}")
