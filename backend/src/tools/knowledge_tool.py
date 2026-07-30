"""知识库工具 — @tool 封装（5 个方法）"""

from datetime import UTC, datetime

from langchain_core.tools import tool
from loguru import logger

from src.core.config import settings
from src.knowledge.chunker import split_into_chunks
from src.knowledge.document_loader import load_document
from src.knowledge.retrieval import retrieval_pipeline
from src.knowledge.vector_store import vector_store


@tool
async def search_knowledge(query: str, user_id: str, top_k: int = 3) -> str:
    """从用户的知识库中检索相关信息。返回检索到的知识片段原文，由你来整理回答用户。

    Args:
        query: 检索关键词或问题
        user_id: 用户ID
        top_k: 返回最相似的K个片段（默认3）
    """
    k = max(1, min(top_k, 20))
    try:
        docs = await retrieval_pipeline.search(user_id, query, k)
        if not docs:
            return "知识库中未找到相关信息。"

        # 返回原始片段，由 Agent 自己整理回答（保证流式输出）
        parts = ["以下是从知识库中检索到的相关信息：\n"]
        for i, doc in enumerate(docs):
            section = doc.get("metadata", {}).get("section", "")
            label = f"片段 {i + 1}" + (f"（章节：{section}）" if section else "")
            parts.append(f"{label}:\n{doc['text']}\n")
        parts.append("请基于以上片段回答用户问题，使用片段中的信息，标注引用来源。")
        return "\n".join(parts)
    except Exception as e:
        logger.error(f"知识库检索失败: {e}")
        return f"检索知识库时发生错误: {e}"


@tool
async def upload_knowledge(file_path: str, user_id: str) -> str:
    """上传文档到用户知识库。

    Args:
        file_path: 本地文件路径（支持 txt/pdf/doc/docx/xlsx/xls）
        user_id: 用户ID
    """
    from pathlib import Path

    path = Path(file_path)
    if not path.exists():
        return f"文件不存在: {file_path}"

    ext = path.suffix.lstrip(".").lower()
    if ext not in settings.allowed_extensions_list:
        return f"不支持的文件格式: {ext}，支持: {settings.allowed_extensions_list}"

    try:
        content = await load_document(file_path, ext)
        chunk_results = split_into_chunks(content, settings.KNOWLEDGE_CHUNK_SIZE, settings.KNOWLEDGE_OVERLAP)

        if not chunk_results:
            return f"文件 [{path.name}] 内容为空，无法向量化"

        now = datetime.now(UTC).isoformat()
        texts = [c["text"] for c in chunk_results]
        metadatas = [
            {"source": path.name, "user_id": user_id, "version": 1, "active": 1, "upload_time": now, "chunk_index": i, "section": c.get("section", "")}
            for i, c in enumerate(chunk_results)
        ]

        await vector_store.add_documents(user_id, texts, metadatas)
        logger.info(f"知识库上传成功: {path.name}, 用户: {user_id}, 分块数: {len(chunk_results)}")
        return f"文档 [{path.name}] 上传成功，已拆分为 {len(chunk_results)} 个片段存入知识库"
    except Exception as e:
        logger.error(f"知识库上传失败: {e}")
        return f"上传文档失败: {e}"


@tool
def get_document_content(filename: str, user_id: str) -> str:
    """获取知识库中指定文档的完整内容（按 chunk_index 排序拼接）。

    Args:
        filename: 文档文件名
        user_id: 用户ID
    """
    try:
        chunks = vector_store.get_by_filename(user_id, filename)
        if not chunks:
            return f"知识库中未找到文档 [{filename}]"

        content = "\n\n".join(chunk["text"] for chunk in chunks)
        return content
    except Exception as e:
        logger.error(f"获取文档内容失败: {e}")
        return f"获取文档内容失败: {e}"


@tool
def list_knowledge(user_id: str) -> str:
    """列出用户知识库中的所有文档。

    Args:
        user_id: 用户ID
    """
    try:
        filenames = vector_store.list_filenames(user_id)
        if not filenames:
            return "知识库中没有文档，您可以上传文件来丰富知识库。"

        sb = f"知识库中共有 {len(filenames)} 个文档:\n"
        for i, name in enumerate(filenames):
            sb += f"{i + 1}. {name}\n"
        return sb.strip()
    except Exception as e:
        logger.error(f"列出文档失败: {e}")
        return f"列出文档时发生错误: {e}"


@tool
def delete_knowledge(filename: str, user_id: str) -> str:
    """删除知识库中指定文档的所有 chunk。

    Args:
        filename: 文档文件名
        user_id: 用户ID
    """
    try:
        count = vector_store.delete_by_filename(user_id, filename)
        if count > 0:
            return f"已删除文档 [{filename}]，共移除 {count} 个片段"
        return f"知识库中未找到文档 [{filename}]，无需删除"
    except Exception as e:
        logger.error(f"删除文档失败: {e}")
        return f"删除文档失败: {e}"
