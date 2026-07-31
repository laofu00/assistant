"""knowledge/vector_store.py 向量存储测试"""

from unittest.mock import MagicMock, patch

import pytest


class TestVectorStore:
    def test_collection_name(self) -> None:
        from src.knowledge.vector_store import VectorStore

        with patch("src.knowledge.vector_store.chromadb.PersistentClient"):
            with patch("src.knowledge.vector_store.TrackedEmbeddingFunction"):
                vs = VectorStore(persist_dir="/tmp/test")
                assert vs._collection_name("user123") == "knowledge_user123"

    def test_uses_http_client_when_url_set(self, monkeypatch) -> None:
        monkeypatch.setattr("src.knowledge.vector_store.settings.CHROMA_URL", "http://localhost:8001")

        mock_http = MagicMock()
        with patch("src.knowledge.vector_store.chromadb.HttpClient", return_value=mock_http):
            with patch("src.knowledge.vector_store.TrackedEmbeddingFunction"):
                from src.knowledge.vector_store import VectorStore

                vs = VectorStore()
                assert vs._client is mock_http

    def test_uses_persistent_when_no_url(self, monkeypatch) -> None:
        monkeypatch.setattr("src.knowledge.vector_store.settings.CHROMA_URL", "")

        mock_pc = MagicMock()
        with patch("src.knowledge.vector_store.chromadb.PersistentClient", return_value=mock_pc):
            with patch("src.knowledge.vector_store.TrackedEmbeddingFunction"):
                from src.knowledge.vector_store import VectorStore

                vs = VectorStore(persist_dir="/tmp/chroma_test")
                assert vs._client is mock_pc

    def test_get_or_create_collection(self) -> None:
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection

        with patch("src.knowledge.vector_store.chromadb.PersistentClient", return_value=mock_client):
            with patch("src.knowledge.vector_store.TrackedEmbeddingFunction"):
                from src.knowledge.vector_store import VectorStore

                vs = VectorStore(persist_dir="/tmp/test")
                col = vs._get_collection("user_x")
                mock_client.get_or_create_collection.assert_called_once()
                assert col is mock_collection
