"""knowledge/document_loader.py 文档加载器测试"""

import tempfile
from pathlib import Path

import pytest

from src.knowledge.document_loader import load_document


class TestLoadTxt:
    async def test_load_utf8(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("这是测试文档内容\n第二行内容")
            tmp = f.name

        try:
            content = await load_document(tmp)
            assert "测试文档" in content
            assert "第二行" in content
        finally:
            Path(tmp).unlink(missing_ok=True)

    async def test_load_utf8_auto_detect_ext(self) -> None:
        """不传 file_type 时自动从路径推断"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("hello world")
            tmp = f.name

        try:
            content = await load_document(tmp)
            assert content == "hello world"
        finally:
            Path(tmp).unlink(missing_ok=True)

    async def test_load_with_explicit_type(self) -> None:
        """显式指定 file_type"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".dat", delete=False, encoding="utf-8") as f:
            f.write("custom extension")
            tmp = f.name

        try:
            content = await load_document(tmp, file_type="txt")
            assert content == "custom extension"
        finally:
            Path(tmp).unlink(missing_ok=True)

    async def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            await load_document("/nonexistent/file.txt")

    async def test_unsupported_format(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xyz", delete=False) as f:
            f.write("data")
            tmp = f.name

        try:
            with pytest.raises(ValueError, match="不支持"):
                await load_document(tmp)
        finally:
            Path(tmp).unlink(missing_ok=True)
