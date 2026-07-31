"""ChromaDB 向量存储封装 — CRUD + 按用户隔离，使用 API 向量化"""

import asyncio
from datetime import datetime, timezone

import chromadb
from chromadb.api import ClientAPI
from loguru import logger

from src.core.config import settings
from src.knowledge.embedding_tracker import TrackedEmbeddingFunction

# 嵌入 API 批次大小
_EMBED_BATCH_SIZE = 20
# 指数退避配置
_MAX_RETRIES = 3
_BASE_DELAY = 2.0  # 秒


class VectorStore:
    """ChromaDB 封装，按 user_id 隔离 collection

    支持两种模式：
    - 生产：CHROMA_URL=http://localhost:8001 → HttpClient 连接独立服务
    - 开发：CHROMA_URL 为空 → PersistentClient 嵌入式
    """

    def __init__(self, persist_dir: str | None = None) -> None:
        if settings.CHROMA_URL:
            self._client: ClientAPI = chromadb.HttpClient(
                host=settings.CHROMA_URL,
                settings=chromadb.Settings(anonymized_telemetry=False),
            )
        else:
            self._client: ClientAPI = chromadb.PersistentClient(
                path=persist_dir or settings.chroma_path,
            )
        self._ef = TrackedEmbeddingFunction()

    def _collection_name(self, user_id: str) -> str:
        return f"knowledge_{user_id}"

    def _get_collection(self, user_id: str):
        return self._client.get_or_create_collection(
            name=self._collection_name(user_id),
            embedding_function=self._ef,
        )

    async def add_documents(
        self,
        user_id: str,
        texts: list[str],
        metadata_list: list[dict] | None = None,
        ids: list[str] | None = None,
    ) -> None:
        """批量添加文档向量（分批 + 指数退避重试，避免 API 限流）"""
        collection = self._get_collection(user_id)
        metadatas = metadata_list or [{}] * len(texts)
        doc_ids = ids or [f"{user_id}_{i}_{datetime.now(timezone.utc).timestamp()}" for i in range(len(texts))]

        total = len(texts)
        for start in range(0, total, _EMBED_BATCH_SIZE):
            end = min(start + _EMBED_BATCH_SIZE, total)
            batch = (start // _EMBED_BATCH_SIZE) + 1
            total_batches = (total + _EMBED_BATCH_SIZE - 1) // _EMBED_BATCH_SIZE

            for attempt in range(1, _MAX_RETRIES + 1):
                try:
                    collection.add(
                        documents=texts[start:end],
                        metadatas=metadatas[start:end],
                        ids=doc_ids[start:end],
                    )
                    logger.debug(f"向量化批次 {batch}/{total_batches} 完成 ({end - start} chunks)")
                    break
                except Exception as e:
                    if attempt == _MAX_RETRIES:
                        logger.error(f"向量化批次 {batch} 失败（已重试 {_MAX_RETRIES} 次）: {e}")
                        raise
                    delay = _BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        f"向量化批次 {batch} 失败 (尝试 {attempt}/{_MAX_RETRIES})，{delay:.0f}s 后重试: {e}"
                    )
                    await asyncio.sleep(delay)

    @staticmethod
    def _with_active(where: dict | None = None) -> dict:
        """组合 active=1 过滤条件"""
        active_filter = {"active": 1}
        if where is None:
            return active_filter
        return {"$and": [where, active_filter]}

    def deactivate_by_filename(self, user_id: str, filename: str) -> int:
        """将指定文件的所有 chunk 标记为 inactive（不重新嵌入）"""
        collection = self._get_collection(user_id)
        results = collection.get(where={"source": filename}, include=["metadatas"])
        ids = results.get("ids", [])
        if not ids:
            return 0
        new_metas = []
        for meta in (results["metadatas"] or []):
            m = dict(meta) if meta else {}
            m["active"] = 0
            new_metas.append(m)
        collection.update(ids=ids, metadatas=new_metas)
        logger.debug(f"软删除 {len(ids)} 个 chunk: {filename}")
        return len(ids)

    def deactivate_by_file_id(self, user_id: str, file_id: str) -> int:
        """按 file_id 将 chunk 标记为 inactive"""
        collection = self._get_collection(user_id)
        results = collection.get(where={"file_id": file_id}, include=["metadatas"])
        ids = results.get("ids", [])
        if not ids:
            return 0
        new_metas = []
        for meta in (results["metadatas"] or []):
            m = dict(meta) if meta else {}
            m["active"] = 0
            new_metas.append(m)
        collection.update(ids=ids, metadatas=new_metas)
        return len(ids)

    def get_all_docs(self, user_id: str) -> list[dict]:
        """获取用户全部活跃文档（不触发嵌入）"""
        collection = self._get_collection(user_id)
        results = collection.get(where={"active": 1}, include=["documents", "metadatas"])
        if not results["documents"]:
            return []
        return [
            {"text": doc, "metadata": meta}
            for doc, meta in zip(results["documents"], results["metadatas"] or [{}] * len(results["documents"]))
        ]

    def search(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
        where: dict | None = None,
    ) -> list[dict]:
        """向量相似度检索"""
        collection = self._get_collection(user_id)
        results = collection.query(
            query_texts=[query],
            n_results=top_k,
            where=self._with_active(where),
        )
        if not results["documents"] or not results["documents"][0]:
            return []

        docs = results["documents"][0]
        metas = results["metadatas"][0] if results["metadatas"] else [{}] * len(docs)
        distances = results["distances"][0] if results["distances"] else [0] * len(docs)

        return [
            {
                "text": doc,
                "metadata": meta,
                "distance": dist,
            }
            for doc, meta, dist in zip(docs, metas, distances)
        ]

    def get_by_filename(self, user_id: str, filename: str) -> list[dict]:
        """按文件名获取活跃 chunk（按 chunk_index 排序）"""
        collection = self._get_collection(user_id)
        results = collection.get(
            where={"$and": [{"source": filename}, {"active": 1}]},
            include=["documents", "metadatas"],
        )
        if not results["documents"]:
            return []

        docs = results["documents"]
        metas = results["metadatas"] or [{}] * len(docs)

        items = [
            {"text": doc, "metadata": meta}
            for doc, meta in zip(docs, metas)
        ]
        items.sort(key=lambda x: x["metadata"].get("chunk_index", 0))
        return items

    def list_filenames(self, user_id: str) -> list[str]:
        """列出用户所有活跃文件"""
        collection = self._get_collection(user_id)
        results = collection.get(where={"active": 1}, include=["metadatas"])
        if not results["metadatas"]:
            return []

        filenames: set[str] = set()
        for meta in results["metadatas"]:
            src = meta.get("source")
            if src:
                filenames.add(src)
        return sorted(filenames)

    def delete_by_filename(self, user_id: str, filename: str) -> int:
        """删除指定文件的所有 chunk，返回删除数量"""
        return self._delete_by_metadata(user_id, {"source": filename})

    def delete_by_file_id(self, user_id: str, file_id: int) -> int:
        """按文件 ID 删除所有 chunk，返回删除数量"""
        return self._delete_by_metadata(user_id, {"file_id": str(file_id)})

    def _delete_by_metadata(self, user_id: str, where: dict) -> int:
        """按 metadata 条件删除 chunk"""
        collection = self._get_collection(user_id)
        results = collection.get(where=where, include=["metadatas"])
        ids = results.get("ids", [])
        if ids:
            collection.delete(ids=ids)
        return len(ids)

    def count(self, user_id: str) -> int:
        """获取用户活跃文档总数"""
        collection = self._get_collection(user_id)
        results = collection.get(where={"active": 1}, include=[])
        return len(results.get("ids", []))

    def heartbeat(self) -> int:
        """健康检查：返回心跳响应时间（毫秒）"""
        return self._client.heartbeat()


# 全局实例
vector_store = VectorStore()
