"""文档分块器 — 段落→句子层级分块算法

对齐 Java 版 VectorizationProcessor 的自定义分块逻辑。
"""

import re

# 句子分隔符
_SENTENCE_PATTERN = re.compile(r"[。！？.!?]\s*")


def split_into_chunks(text: str, chunk_size: int = 800, overlap: int = 150) -> list[str]:
    """按段落→句子层级分块

    1. 按空行分割段落
    2. 段落内按句子分隔符切句
    3. 逐句合并，超出 chunk_size 时切分
    4. overlap 保留上一块末尾若干句到下一块

    Args:
        text: 原始文本
        chunk_size: 块大小（字符数）
        overlap: 重叠字符数

    Returns:
        分块列表
    """
    if not text or not text.strip():
        return []

    # 1. 按段落分割
    paragraphs = text.split("\n\n")

    # 2. 段落内按句子分割
    sentences: list[str] = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        parts = _SENTENCE_PATTERN.split(para)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if len(part) > chunk_size:
                # 超长句强制切分
                _split_long(part, chunk_size, sentences)
            else:
                sentences.append(part)

    if not sentences:
        return []

    # 3. 逐句合并，控制块大小 + overlap
    chunks: list[str] = []
    current_sentences: list[str] = []
    current_len = 0

    for sentence in sentences:
        s_len = len(sentence)
        sep = 0 if not current_sentences else 1

        if current_len + s_len + sep > chunk_size and current_sentences:
            chunks.append(" ".join(current_sentences))

            if overlap > 0:
                # 保留尾部若干句子作为下一块 overlap（对齐 Java）
                overlap_sentences: list[str] = []
                overlap_len = 0
                for s in reversed(current_sentences):
                    s_len = len(s)
                    sep_len = 0 if not overlap_sentences else 1
                    if overlap_len + s_len + sep_len > overlap:
                        break
                    overlap_sentences.insert(0, s)
                    overlap_len += s_len + (1 if len(overlap_sentences) > 1 else 0)
                current_sentences = overlap_sentences
                current_len = overlap_len
            else:
                current_sentences = []
                current_len = 0

        current_sentences.append(sentence)
        current_len += s_len + (1 if len(current_sentences) > 1 else 0)

    if current_sentences:
        chunks.append(" ".join(current_sentences))

    # 4. 兜底：无有效分块时按字符切分
    if not chunks:
        for i in range(0, len(text), chunk_size):
            chunks.append(text[i : i + chunk_size])

    return chunks


def _split_long(sentence: str, chunk_size: int, output: list[str]) -> None:
    """将超长句子强制按 chunk_size 切分"""
    for i in range(0, len(sentence), chunk_size):
        output.append(sentence[i : i + chunk_size].strip())
