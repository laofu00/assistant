"""token/dead_letter.py 死信队列测试"""

import tempfile
from pathlib import Path

import pytest


class TestDeadLetterQueue:
    async def test_get_path_from_settings(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "src.token.dead_letter.settings.DEAD_LETTER_DB_URL",
            "sqlite+aiosqlite:///data/dead_letter/test_dead.db",
        )
        from src.token.dead_letter import DeadLetterQueue

        dlq = DeadLetterQueue()
        path = dlq._get_path()
        assert "dead_letter" in str(path)

    async def test_custom_path(self) -> None:
        from src.token.dead_letter import DeadLetterQueue

        with tempfile.TemporaryDirectory() as tmpdir:
            dlq = DeadLetterQueue()
            dlq._db_path = Path(tmpdir) / "custom.db"
            assert dlq._get_path() == Path(tmpdir) / "custom.db"

    async def test_ensure_table_creates(self, monkeypatch) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dl_path = Path(tmpdir) / "dead.db"
            monkeypatch.setattr(
                "src.token.dead_letter.settings.DEAD_LETTER_DB_URL",
                f"sqlite+aiosqlite:///{dl_path}",
            )
            from src.token.dead_letter import DeadLetterQueue

            dlq = DeadLetterQueue()
            await dlq._ensure_table()
            assert dl_path.exists()

            import aiosqlite
            async with aiosqlite.connect(str(dl_path)) as db:
                cursor = await db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='dead_letter'"
                )
                assert await cursor.fetchone() is not None

    async def test_save_and_count(self, monkeypatch) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dl_path = Path(tmpdir) / "dead_save.db"
            monkeypatch.setattr(
                "src.token.dead_letter.settings.DEAD_LETTER_DB_URL",
                f"sqlite+aiosqlite:///{dl_path}",
            )
            from src.token.dead_letter import DeadLetterQueue

            dlq = DeadLetterQueue()
            await dlq.save({
                "trace_id": "trace_x", "user_id": "user_x",
                "model_name": "qwen-plus", "total_tokens": 500,
            })
            count = await dlq.get_pending_count()
            assert count == 1

    async def test_save_multiple(self, monkeypatch) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dl_path = Path(tmpdir) / "dead_multi.db"
            monkeypatch.setattr(
                "src.token.dead_letter.settings.DEAD_LETTER_DB_URL",
                f"sqlite+aiosqlite:///{dl_path}",
            )
            from src.token.dead_letter import DeadLetterQueue

            dlq = DeadLetterQueue()
            for i in range(3):
                await dlq.save({"trace_id": f"t{i}", "user_id": "u"})
            assert await dlq.get_pending_count() == 3

    async def test_get_pending_count_empty(self) -> None:
        from src.token.dead_letter import DeadLetterQueue

        dlq = DeadLetterQueue()
        dlq._db_path = Path("/nonexistent/path.db")
        assert await dlq.get_pending_count() == 0

    async def test_retry_pending_empty(self, monkeypatch) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dl_path = Path(tmpdir) / "dead_retry_empty.db"
            monkeypatch.setattr(
                "src.token.dead_letter.settings.DEAD_LETTER_DB_URL",
                f"sqlite+aiosqlite:///{dl_path}",
            )
            from src.token.dead_letter import DeadLetterQueue

            dlq = DeadLetterQueue()
            await dlq._ensure_table()
            count = await dlq.retry_pending()
            assert count == 0
