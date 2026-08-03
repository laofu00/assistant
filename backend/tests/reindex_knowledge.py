"""重索引脚本：将修改后的文档重新切片入库 ChromaDB

用法：
    cd backend && .venv/Scripts/python tests/reindex_knowledge.py
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chromadb import PersistentClient

from src.core.config import settings
from src.knowledge.chunker import split_into_chunks
from src.knowledge.vector_store import vector_store

USER_ID = "u05c42c5b"
UPLOAD_DIR = Path("data/uploads")

# 需要重新入库的 5 个文件
FILES = [
    "6c3782488a5345f3ad78c6ff8645b855_LangGraph 智能体架构与状态管理.txt",
    "37eb8ce74696476a948c697d20c40ada_高级 RAG 检索架构与评估.txt",
    "a98b8dca5f384e0599b82e021a0d7d6b_工具治理体系与韧性工程.txt",
    "0eccdab369ce4f04a68e07ae1f9c9033_分层记忆体系与长上下文处理.txt",
    "2ab8a3b62cbe4ee2a24b7387adb09687_安全防护、可观测性与成本控制.txt",
]


async def reindex():
    # 1. 清空现有 collection
    client = PersistentClient(path=settings.chroma_path)
    collection_name = f"knowledge_{USER_ID}"
    try:
        col = client.get_collection(collection_name)
        count = col.count()
        if count > 0:
            # 删除所有 chunks
            all_ids = col.get(include=[])["ids"]
            col.delete(ids=all_ids)
            print(f"[1/4] 已删除 {len(all_ids)} 个旧 chunk")
        else:
            print("[1/4] collection 为空，跳过删除")
    except Exception as e:
        print(f"[1/4] collection 不存在或已清空: {e}")

    # 2. 读取文件并分块
    print("[2/4] 读取文件并分块...")
    all_texts: list[str] = []
    all_metas: list[dict] = []
    all_ids: list[str] = []

    for i, fname in enumerate(FILES):
        filepath = UPLOAD_DIR / fname
        if not filepath.exists():
            print(f"  ⚠ {fname} 不存在，跳过")
            continue

        text = filepath.read_text(encoding="utf-8")
        chunks = split_into_chunks(text, chunk_size=800, overlap=150)
        print(f"  ✓ {fname}: {len(chunks)} chunks")

        for ci, chunk in enumerate(chunks):
            all_texts.append(chunk["text"])
            all_metas.append({
                "source": fname,
                "user_id": USER_ID,
                "file_id": str(i + 1),
                "chunk_index": ci,
                "section": chunk.get("section", ""),
                "active": 1,
            })
            all_ids.append(f"reindex_{USER_ID}_{i}_{ci}")

    print(f"  总计: {len(all_texts)} chunks")

    # 3. 向量化入库
    print("[3/4] 向量化入库（需调用 DashScope embedding API）...")
    await vector_store.add_documents(
        user_id=USER_ID,
        texts=all_texts,
        metadata_list=all_metas,
        ids=all_ids,
    )

    # 4. 验证
    print("[4/4] 验证...")
    col2 = client.get_collection(collection_name)
    final_count = col2.count()
    print(f"  ChromaDB collection '{collection_name}': {final_count} chunks")

    # 列出文件分布
    results = col2.get(include=["metadatas"])
    sources: dict[str, int] = {}
    for m in results["metadatas"]:
        src = m.get("source", "?")
        sources[src] = sources.get(src, 0) + 1
    for src, cnt in sources.items():
        print(f"    {src}: {cnt} chunks")

    # 验证旧缓存失效
    from src.knowledge.retrieval import retrieval_pipeline
    retrieval_pipeline.invalidate_bm25(USER_ID)
    print("  BM25 缓存已失效")

    print("\n✅ 重索引完成！")


if __name__ == "__main__":
    asyncio.run(reindex())
