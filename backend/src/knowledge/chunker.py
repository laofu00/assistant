"""文档分块器 — 段落→句子层级分块 + 标题检测

对齐 Java 版 VectorizationProcessor 的自定义分块逻辑。
"""

import re
from typing import TypedDict

# 句子分隔符
_SENTENCE_PATTERN = re.compile(r"[。！？.!?]\s*")

# 标题行检测
_HEADING_PATTERN = re.compile(
    r"^("
    r"\d+(\.\d+)*[\.\)、]\s"           # "1.", "1.1)", "2、"
    r"|[一二三四五六七八九十]+[、．.]"    # "一、", "二．"
    r"|第[一二三四五六七八九十百千]+[章节条款部]"  # "第一章", "第二节"
    r"|[\[\(]\d+[\]\)]"                # "(1)", "[2]"
    r")"
)
# 短行标题：≤50 字符且以冒号结尾
_SHORT_HEADING_PATTERN = re.compile(r"^.{1,50}[：:]\s*$")
# 英文全大写标题
_CAPS_HEADING_PATTERN = re.compile(r"^[A-Z][A-Z\s\-]{3,}$")
# 分隔线
_SEPARATOR_PATTERN = re.compile(r"^[-=*_]{5,}$")


class ChunkResult(TypedDict):
    text: str
    section: str


def split_into_chunks(
    text: str, chunk_size: int = 800, overlap: int = 150
) -> list[ChunkResult]:
    """按段落→句子层级分块，附带最近标题作为 section 元数据

    1. 按空行分割段落，检测标题行
    2. 段落内按句子分隔符切句
    3. 逐句合并，超出 chunk_size 时切分
    4. overlap 保留上一块末尾若干句到下一块

    Returns:
        [{"text": "块内容", "section": "所属章节标题"}, ...]
    """
    if not text or not text.strip():
        return []

    # 1. 按段落分割，同时检测标题
    paragraphs = text.split("\n\n")
    current_section = ""
    sentences: list[tuple[str, str]] = []  # (sentence, section)

    for para in paragraphs:
        para_stripped = para.strip()
        if not para_stripped:
            continue

        # 检测是否为标题行
        if _SEPARATOR_PATTERN.match(para_stripped):
            continue
        if _is_heading(para_stripped):
            current_section = para_stripped[:100]
            # 标题本身也作为句子保留
            sentences.append((current_section, current_section))
            continue

        # 2. 段落内按句子分割
        parts = _SENTENCE_PATTERN.split(para_stripped)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if len(part) > chunk_size:
                _split_long(part, chunk_size, sentences, current_section)
            else:
                sentences.append((part, current_section))

    if not sentences:
        return []

    # 3. 逐句合并，控制块大小 + overlap
    chunks: list[ChunkResult] = []
    current_texts: list[str] = []
    current_sections: list[str] = []  # 与 current_texts 并行
    current_len = 0

    for sentence, section in sentences:
        s_len = len(sentence)
        sep = 0 if not current_texts else 1

        if current_len + s_len + sep > chunk_size and current_texts:
            chunks.append({
                "text": " ".join(current_texts),
                "section": _pick_section(current_sections),
            })

            if overlap > 0:
                # 保留尾部若干句子作为下一块 overlap
                overlap_texts: list[str] = []
                overlap_sections: list[str] = []
                overlap_len = 0
                for s, sec in reversed(list(zip(current_texts, current_sections, strict=True))):
                    s_len = len(s)
                    sep_len = 0 if not overlap_texts else 1
                    if overlap_len + s_len + sep_len > overlap:
                        break
                    overlap_texts.insert(0, s)
                    overlap_sections.insert(0, sec)
                    overlap_len += s_len + (1 if len(overlap_texts) > 1 else 0)
                current_texts = overlap_texts
                current_sections = overlap_sections
                current_len = overlap_len
            else:
                current_texts = []
                current_sections = []
                current_len = 0

        current_texts.append(sentence)
        current_sections.append(section)
        current_len += s_len + (1 if len(current_texts) > 1 else 0)

    if current_texts:
        chunks.append({
            "text": " ".join(current_texts),
            "section": _pick_section(current_sections),
        })

    # 4. 兜底：无有效分块时按字符切分
    if not chunks:
        for i in range(0, len(text), chunk_size):
            chunks.append({"text": text[i : i + chunk_size], "section": ""})

    return chunks


def _is_heading(line: str) -> bool:
    """判断一行是否为标题"""
    if _HEADING_PATTERN.match(line):
        return True
    if _SHORT_HEADING_PATTERN.match(line):
        return True
    if _CAPS_HEADING_PATTERN.match(line):
        return True
    return False


def _pick_section(sections: list[str]) -> str:
    """从 section 列表中选出现频率最高的非空值"""
    valid = [s for s in sections if s]
    if not valid:
        return ""
    if len(valid) == 1:
        return valid[0]
    from collections import Counter
    return Counter(valid).most_common(1)[0][0]


def _split_long(
    sentence: str, chunk_size: int, output: list[tuple[str, str]], section: str
) -> None:
    """将超长句子强制按 chunk_size 切分"""
    for i in range(0, len(sentence), chunk_size):
        output.append((sentence[i : i + chunk_size].strip(), section))
