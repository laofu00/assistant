#!/usr/bin/env python
"""ChromaDB 备份 — 导出所有 collection 的 documents 为 JSON"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import settings
from src.knowledge.vector_store import VectorStore


def backup(output_dir: str | None = None) -> str:
    """备份所有用户的知识库数据"""
    vs = VectorStore(settings.chroma_path)
    client = vs._client

    output = Path(output_dir or settings.DATA_DIR / "chroma_db" / "backups")
    output.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = output / f"backup_{timestamp}.json"

    data: dict[str, list] = {}
    for collection in client.list_collections():
        name = collection.name
        result = collection.get(include=["documents", "metadatas"])
        data[name] = [
            {"text": doc, "metadata": meta}
            for doc, meta in zip(result.get("documents", []), result.get("metadatas", []))
        ]

    backup_file.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"备份完成: {backup_file} ({sum(len(v) for v in data.values())} 条记录)")
    return str(backup_file)


if __name__ == "__main__":
    backup()
