"""knowledge/embedding_tracker.py 嵌入追踪器测试"""

from unittest.mock import MagicMock, patch

import pytest


class TestEmbeddingTracker:
    def test_initialization(self) -> None:
        from src.knowledge.embedding_tracker import TrackedEmbeddingFunction
        tracker = TrackedEmbeddingFunction()
        assert tracker._model == "text-embedding-v3"
        assert hasattr(tracker, "_client")

    def test_is_embedding_function(self) -> None:
        from src.knowledge.embedding_tracker import TrackedEmbeddingFunction
        from chromadb.api.types import EmbeddingFunction
        tracker = TrackedEmbeddingFunction()
        assert isinstance(tracker, EmbeddingFunction)
