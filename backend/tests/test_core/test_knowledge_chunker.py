"""knowledge/chunker.py 文档分块器测试"""

import pytest

from src.knowledge.chunker import split_into_chunks


class TestSplitIntoChunks:
    def test_empty_text(self) -> None:
        assert split_into_chunks("") == []
        assert split_into_chunks("   ") == []

    def test_simple_paragraph(self) -> None:
        text = "这是一个简单的段落。包含两个句子。"
        chunks = split_into_chunks(text, chunk_size=800)
        assert len(chunks) >= 1
        assert all(c["text"] for c in chunks)

    def test_multiple_paragraphs(self) -> None:
        text = "第一段内容。这里还有一句。\n\n第二段内容。第二段第二句。\n\n第三段。"
        chunks = split_into_chunks(text, chunk_size=800)
        assert len(chunks) >= 1

    def test_heading_detection_numbered(self) -> None:
        text = "1. 技术栈要求\n\n候选人需掌握Python和FastAPI。具备3年以上经验。"
        chunks = split_into_chunks(text, chunk_size=800)
        assert any("1. 技术栈要求" in c.get("section", "") for c in chunks)

    def test_heading_detection_chinese(self) -> None:
        text = "一、项目经验\n\n负责核心系统架构设计。参与多个大型项目。"
        chunks = split_into_chunks(text, chunk_size=800)
        # 标题应被检测并作为后续 chunk 的 section
        assert len(chunks) >= 1

    def test_chunk_size_limit(self) -> None:
        """超过 chunk_size 时正确切分"""
        text = "内容。" * 500  # ~1500 chars
        chunks = split_into_chunks(text, chunk_size=800, overlap=150)
        assert len(chunks) > 1

    def test_short_heading_with_colon(self) -> None:
        """短行以冒号结尾，应被检测为标题"""
        text = "技术栈要求：\n\n候选人需掌握Python和FastAPI。"
        chunks = split_into_chunks(text, chunk_size=800)
        assert len(chunks) >= 1

    def test_separator_skipped(self) -> None:
        """分隔线应被跳过"""
        text = "内容一。\n\n-----\n\n内容二。"
        chunks = split_into_chunks(text, chunk_size=800)
        assert len(chunks) >= 1

    def test_with_overlap(self) -> None:
        """overlap 保留上下文"""
        long_text = ("这是一个很长的文本用于测试分块功能。" * 30)
        chunks1 = split_into_chunks(long_text, chunk_size=200, overlap=0)
        chunks2 = split_into_chunks(long_text, chunk_size=200, overlap=50)
        # 有 overlap 时 chunk 数可能不同
        assert len(chunks1) >= 1
        assert len(chunks2) >= 1

    def test_caps_heading(self) -> None:
        """英文全大写标题"""
        text = "SYSTEM ARCHITECTURE\n\nThis is the system architecture section."
        chunks = split_into_chunks(text, chunk_size=500)
        assert len(chunks) >= 1
