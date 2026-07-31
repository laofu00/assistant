"""tools/knowledge_tool.py 知识库工具测试（5个）"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


class TestSearchKnowledge:
    async def test_found_docs(self) -> None:
        mock_retrieval = MagicMock()
        mock_retrieval.search = AsyncMock(return_value=[
            {"text": "Python异步编程", "metadata": {"section": "编程"}},
            {"text": "FastAPI最佳实践", "metadata": {}},
        ])

        with patch("src.tools.knowledge_tool.retrieval_pipeline", mock_retrieval):
            from src.tools.knowledge_tool import search_knowledge
            result = await search_knowledge.ainvoke({"query": "Python", "user_id": "u1"})
            assert "Python" in result
            assert "检索" in result

    async def test_no_results(self) -> None:
        mock_retrieval = MagicMock()
        mock_retrieval.search = AsyncMock(return_value=[])

        with patch("src.tools.knowledge_tool.retrieval_pipeline", mock_retrieval):
            from src.tools.knowledge_tool import search_knowledge
            result = await search_knowledge.ainvoke({"query": "nonexistent", "user_id": "u1"})
            assert "未找到" in result

    async def test_top_k_clamped(self) -> None:
        mock_retrieval = MagicMock()
        mock_retrieval.search = AsyncMock(return_value=[{"text": "x"}])

        with patch("src.tools.knowledge_tool.retrieval_pipeline", mock_retrieval):
            from src.tools.knowledge_tool import search_knowledge
            await search_knowledge.ainvoke({"query": "q", "user_id": "u1", "top_k": 100})
            call_k = mock_retrieval.search.call_args[0][2]
            assert call_k == 20

    async def test_search_error(self) -> None:
        mock_retrieval = MagicMock()
        mock_retrieval.search = AsyncMock(side_effect=Exception("ChromaDB down"))

        with patch("src.tools.knowledge_tool.retrieval_pipeline", mock_retrieval):
            from src.tools.knowledge_tool import search_knowledge
            result = await search_knowledge.ainvoke({"query": "q", "user_id": "u1"})
            assert "错误" in result


class TestUploadKnowledge:
    async def test_file_not_found(self) -> None:
        with patch("src.tools.knowledge_tool.vector_store"):
            from src.tools.knowledge_tool import upload_knowledge
            result = await upload_knowledge.ainvoke({"file_path": "/nonexistent/file.txt", "user_id": "u1"})
            assert "不存在" in result

    async def test_unsupported_format(self, monkeypatch) -> None:
        monkeypatch.setattr("src.tools.knowledge_tool.settings.ALLOWED_EXTENSIONS", "txt,pdf")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".exe", delete=False) as f:
            f.write("binary")
            tmp = f.name
        try:
            with patch("src.tools.knowledge_tool.vector_store"):
                from src.tools.knowledge_tool import upload_knowledge
                result = await upload_knowledge.ainvoke({"file_path": tmp, "user_id": "u1"})
                assert "不支持" in result
        finally:
            Path(tmp).unlink(missing_ok=True)

    async def test_successful_upload(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("测试文档内容。用于知识库上传测试。这是第二个句子。")
            tmp = f.name

        mock_vs = MagicMock()
        mock_vs.add_documents = AsyncMock()

        try:
            with patch("src.tools.knowledge_tool.vector_store", mock_vs):
                from src.tools.knowledge_tool import upload_knowledge
                result = await upload_knowledge.ainvoke({"file_path": tmp, "user_id": "u1"})
                assert "上传成功" in result
                mock_vs.add_documents.assert_awaited_once()
        finally:
            Path(tmp).unlink(missing_ok=True)

    async def test_empty_file(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("")
            tmp = f.name
        try:
            with patch("src.tools.knowledge_tool.vector_store"):
                from src.tools.knowledge_tool import upload_knowledge
                result = await upload_knowledge.ainvoke({"file_path": tmp, "user_id": "u1"})
                assert "为空" in result or "无法" in result
        finally:
            Path(tmp).unlink(missing_ok=True)


class TestGetDocumentContent:
    def test_found(self) -> None:
        mock_vs = MagicMock()
        mock_vs.get_by_filename = MagicMock(return_value=[{"text": "第1页内容"}, {"text": "第2页内容"}])
        with patch("src.tools.knowledge_tool.vector_store", mock_vs):
            from src.tools.knowledge_tool import get_document_content
            result = get_document_content.invoke({"filename": "doc.pdf", "user_id": "u1"})
            assert "第1页" in result

    def test_not_found(self) -> None:
        mock_vs = MagicMock()
        mock_vs.get_by_filename = MagicMock(return_value=[])
        with patch("src.tools.knowledge_tool.vector_store", mock_vs):
            from src.tools.knowledge_tool import get_document_content
            result = get_document_content.invoke({"filename": "missing.pdf", "user_id": "u1"})
            assert "未找到" in result


class TestListKnowledge:
    def test_list_files(self) -> None:
        mock_vs = MagicMock()
        mock_vs.list_filenames = MagicMock(return_value=["doc1.pdf", "doc2.txt"])
        with patch("src.tools.knowledge_tool.vector_store", mock_vs):
            from src.tools.knowledge_tool import list_knowledge
            result = list_knowledge.invoke({"user_id": "u1"})
            assert "doc1.pdf" in result

    def test_empty(self) -> None:
        mock_vs = MagicMock()
        mock_vs.list_filenames = MagicMock(return_value=[])
        with patch("src.tools.knowledge_tool.vector_store", mock_vs):
            from src.tools.knowledge_tool import list_knowledge
            result = list_knowledge.invoke({"user_id": "u1"})
            assert "没有" in result


class TestDeleteKnowledge:
    def test_delete_success(self) -> None:
        mock_vs = MagicMock()
        mock_vs.delete_by_filename = MagicMock(return_value=3)
        with patch("src.tools.knowledge_tool.vector_store", mock_vs):
            from src.tools.knowledge_tool import delete_knowledge
            result = delete_knowledge.invoke({"filename": "old.pdf", "user_id": "u1"})
            assert "删除" in result

    def test_delete_not_found(self) -> None:
        mock_vs = MagicMock()
        mock_vs.delete_by_filename = MagicMock(return_value=0)
        with patch("src.tools.knowledge_tool.vector_store", mock_vs):
            from src.tools.knowledge_tool import delete_knowledge
            result = delete_knowledge.invoke({"filename": "no.pdf", "user_id": "u1"})
            assert "未找到" in result
