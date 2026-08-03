"""分析失败题目 Top-5 检索结果，分类根因

用法：
    cd backend && .venv/Scripts/python tests/rag_debug_failures.py
"""

import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import settings
from src.knowledge.retrieval import retrieval_pipeline

USER_ID = "u05c42c5b"
TEST_SET_PATH = settings.PROJECT_ROOT / "data/uploads/测试集.json"
TOP_K = 5


def _normalize(text: str) -> str:
    text = re.sub(r"\s+", "", text)
    text = text.replace("）", ")").replace("（", "(")
    text = text.replace("：", ":").replace("，", ",").replace("。", ".")
    text = text.replace(""", "\"").replace(""", "\"")
    text = text.replace("'", "'").replace("'", "'")
    text = text.replace("、", ",")
    text = text.replace("；", ";")
    return text.lower()


def _extract_keywords(text: str) -> set[str]:
    """提取答案关键词：中英文边界分离 + jieba 中文分词"""
    import jieba

    t = text
    t = t.replace("）", ")").replace("（", "(")
    t = t.replace("：", ":").replace("，", ",").replace("。", ".")
    t = t.replace(""", "\"").replace(""", "\"")
    t = t.replace("、", ",").replace("；", ";")
    t = t.lower()
    t = re.sub(r"([a-z0-9])([\u4e00-\u9fff])", r"\1 \2", t)
    t = re.sub(r"([\u4e00-\u9fff])([a-z0-9])", r"\1 \2", t)
    eng_nums = set(re.findall(r"[a-z][a-z0-9_]+", t))
    nums = set(re.findall(r"\d+", text))
    zh_text = re.sub(r"[a-z0-9_]+", " ", t)
    zh_words = {w.strip() for w in jieba.cut(zh_text) if len(w.strip()) >= 1}
    zh_words = {w for w in zh_words if len(w) >= 2 or w.isdigit()}
    return eng_nums | nums | zh_words


async def main():
    with open(TEST_SET_PATH, "r", encoding="utf-8") as f:
        test_set = json.load(f)

    print(f"测试集: {len(test_set)} 条\n")

    failures = []
    for idx, item in enumerate(test_set):
        question = item["question"]
        expected = item["answer"]

        docs = await retrieval_pipeline.search(USER_ID, question, TOP_K)

        keywords = _extract_keywords(expected)
        threshold = max(1, int(len(keywords) * 0.7))

        # 检查 Top-5 中关键词命中情况
        best_matched = 0
        best_rank = None
        any_in_candidates = False

        for rank, doc in enumerate(docs, 1):
            norm_doc = _normalize(doc["text"])
            matched = sum(1 for kw in keywords if kw in norm_doc)
            if matched > best_matched:
                best_matched = matched
                best_rank = rank
            if matched >= threshold:
                any_in_candidates = True

        hit = any_in_candidates and best_rank is not None

        if not hit:
            failures.append({
                "index": idx + 1,
                "question": question,
                "expected": expected,
                "docs": docs,
                "best_matched": best_matched,
                "best_rank": best_rank,
                "total_keywords": len(keywords),
                "keywords": keywords,
            })

    # 分类
    cat_a = []  # 正确答案在 Top-5 中关键词部分命中但未达阈值（匹配问题）
    cat_b = []  # 正确答案根本不在 Top-5 里，但候选文档中有相关内容（排序问题）
    cat_c = []  # Top-5 里完全找不到任何答案关键词（召回问题）

    for f in failures:
        keywords = f["keywords"]
        total_kw = f["total_keywords"]
        matched = f["best_matched"]
        match_ratio = matched / total_kw if total_kw > 0 else 0

        # 检查 Top-5 中是否有任何文档包含部分关键词（>= 50%）
        has_partial = matched >= max(1, total_kw * 0.5)

        if has_partial and matched < max(1, total_kw * 0.7):
            cat_a.append({**f, "ratio": match_ratio})
        elif matched == 0:
            cat_c.append({**f, "ratio": 0})
        else:
            cat_b.append({**f, "ratio": match_ratio})

    print("=" * 60)
    print(f"  失败题目分析（共 {len(failures)} 题）")
    print("=" * 60)
    print()
    print(f"  A 类（部分匹配未达阈值）: {len(cat_a)} 题")
    print(f"  B 类（有匹配但不在 Top-1）: {len(cat_b)} 题")
    print(f"  C 类（完全无匹配）: {len(cat_c)} 题")
    print()

    for label, cases in [("A 类", cat_a), ("B 类", cat_b), ("C 类", cat_c)]:
        if not cases:
            continue
        print(f"{'='*60}")
        print(f"  {label} — {len(cases)} 题")
        print(f"{'='*60}")
        for c in cases:
            print(f"\n  [{c['index']:3d}] {c['question'][:70]}")
            print(f"        预期: {c['expected'][:80]}")
            print(f"        关键词({c['total_keywords']}个): {', '.join(list(c['keywords'])[:8])}")
            print(f"        Top-5 最佳匹配: {c['best_matched']}/{c['total_keywords']} ({c['ratio']:.0%})")

            # 打印每条检索结果的关键词命中数
            for rank, doc in enumerate(c["docs"][:5], 1):
                norm = _normalize(doc["text"])
                matched_kw = sum(1 for kw in c["keywords"] if kw in norm)
                source = doc["metadata"].get("source", "?")[:50]
                # 高亮命中的关键词
                hit_kws = [kw for kw in c["keywords"] if kw in norm]
                print(f"        Rank {rank} [{source}] matched={matched_kw}/{c['total_keywords']}: {', '.join(hit_kws[:5])}")
                if matched_kw > 0:
                    # 打印文档片段中命中关键词附近的上下文
                    snippet = doc["text"][:150]
                    print(f"              \"{snippet}...\"")
            print()

    print("=" * 60)
    print("  建议")
    print("=" * 60)
    if len(cat_c) > len(cat_a) and len(cat_c) > len(cat_b):
        print("  C 类最多 → 嵌入/分块是瓶颈，调整 chunk_size 或换嵌入模型")
    elif len(cat_a) > len(cat_b) and len(cat_a) > len(cat_c):
        print("  A 类最多 → 匹配阈值偏高，但召回没问题")
    else:
        print("  B 类最多 → 排序/重排是瓶颈，调整 Rerank 或 MMR 参数")
    print()


if __name__ == "__main__":
    asyncio.run(main())
