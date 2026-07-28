"""Token 写入容错 — 主库失败时 SQLite 兜底 + 定期重试"""

import json
from datetime import datetime, timezone
from pathlib import Path

from src.core.config import settings


class DeadLetterQueue:
    """死信队列：Token 写入主 PostgreSQL 失败时存入 SQLite 兜底

    使用 aiosqlite 异步写入，定期由后台任务重试到主库。
    """

    def __init__(self) -> None:
        self._db_path: Path | None = None

    async def _ensure_table(self) -> None:
        """确保 SQLite 表存在"""
        import aiosqlite
        path = self._get_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(str(path)) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS dead_letter (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    retry_count INTEGER DEFAULT 0
                )
            """)
            await db.commit()

    def _get_path(self) -> Path:
        if self._db_path:
            return self._db_path
        # 从 settings 解析路径
        url = settings.DEAD_LETTER_DB_URL
        if "///" in url:
            db_path = url.split("///", 1)[1]
        else:
            db_path = "data/dead_letter/dead_letter.db"
        path = Path(db_path)
        if not path.is_absolute():
            path = settings.PROJECT_ROOT / path
        self._db_path = path
        return path

    async def save(self, record: dict) -> None:
        """保存记录到死信队列"""
        import aiosqlite
        await self._ensure_table()
        path = self._get_path()
        async with aiosqlite.connect(str(path)) as db:
            await db.execute(
                "INSERT INTO dead_letter (payload, created_at) VALUES (?, ?)",
                (json.dumps(record, default=str), datetime.now(timezone.utc).isoformat()),
            )
            await db.commit()

    async def get_pending_count(self) -> int:
        """获取待处理记录数"""
        import aiosqlite
        path = self._get_path()
        if not path.exists():
            return 0
        async with aiosqlite.connect(str(path)) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM dead_letter")
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def retry_pending(self, max_retries: int = 3) -> int:
        """重试所有待处理记录到主库，返回成功数"""
        import aiosqlite
        path = self._get_path()
        if not path.exists():
            return 0

        async with aiosqlite.connect(str(path)) as db:
            cursor = await db.execute("SELECT id, payload, retry_count FROM dead_letter")
            rows = await cursor.fetchall()

        success_count = 0
        from src.core.database import async_session_factory
        from src.models.token_usage import TokenUsage

        for row_id, payload_str, retry_count in rows:
            if retry_count >= max_retries:
                continue
            try:
                data = json.loads(payload_str)
                record = TokenUsage(**data)
                async with async_session_factory() as session:
                    session.add(record)
                    await session.commit()
                # 成功后删除
                async with aiosqlite.connect(str(path)) as db:
                    await db.execute("DELETE FROM dead_letter WHERE id = ?", (row_id,))
                    await db.commit()
                success_count += 1
            except Exception:
                # 增加重试计数
                async with aiosqlite.connect(str(path)) as db:
                    await db.execute("UPDATE dead_letter SET retry_count = retry_count + 1 WHERE id = ?", (row_id,))
                    await db.commit()

        return success_count


# 全局实例
dead_letter = DeadLetterQueue()
