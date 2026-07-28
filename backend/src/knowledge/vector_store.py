"""ChromaDB 向量存储封装 — CRUD + 按用户隔离，使用 API 向量化"""

from datetime import datetime, timezone

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.types import EmbeddingFunction, Metadata
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

from src.core.config import settings


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
        self._ef = OpenAIEmbeddingFunction(
            api_key=settings.OPENAI_API_KEY or "sk-placeholder",
            api_base=settings.OPENAI_BASE_URL,
            model_name=settings.EMBEDDING_MODEL,
        )

    def _collection_name(self, user_id: str) -> str:
        return f"knowledge_{user_id}"

    def _get_collection(self, user_id: str):
        return self._client.get_or_create_collection(
            name=self._collection_name(user_id),
            embedding_function=self._ef,
        )

    def add_documents(
        self,
        user_id: str,
        texts: list[str],
        metadata_list: list[dict] | None = None,
        ids: list[str] | None = None,
    ) -> None:
        """批量添加文档向量"""
        collection = self._get_collection(user_id)
        metadatas = metadata_list or [{}] * len(texts)
        doc_ids = ids or [f"{user_id}_{i}_{datetime.now(timezone.utc).timestamp()}" for i in range(len(texts))]

        collection.add(
            documents=texts,
            metadatas=metadatas,
            ids=doc_ids,
        )

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
            where=where,
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
        """按文件名获取所有 chunk（按 chunk_index 排序）"""
        collection = self._get_collection(user_id)
        results = collection.get(
            where={"source": filename},
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
        """列出用户所有不重复文件名"""
        collection = self._get_collection(user_id)
        results = collection.get(include=["metadatas"])
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
        """获取用户文档总数"""
        collection = self._get_collection(user_id)
        return collection.count()


# 全局实例
vector_store = VectorStore()
