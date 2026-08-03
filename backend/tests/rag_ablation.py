"""RAG 消融实验 — 逐个开关检索组件，量化每个组件的净贡献

用法：
    cd backend && .venv/Scripts/python tests/rag_ablation.py
"""

import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import settings
from src.knowledge.retrieval import retrieval_pipeline

USER_ID = "u05c42c5b"
TOP_K = 5


# ── 从 rag_eval.py 复用的辅助函数 ──

def _extract_keywords(text: str) -> set[str]:
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


def _normalize(text: str) -> str:
    text = re.sub(r"\s+", "", text)
    text = text.replace("）", ")").replace("（", "(")
    text = text.replace("：", ":").replace("，", ",").replace("。", ".")
    text = text.replace(""", "\"").replace(""", "\"")
    text = text.replace("'", "'").replace("'", "'")
    text = text.replace("、", ",").replace("；", ";")
    return text.lower()


def _doc_is_relevant(doc_text: str, keywords: set[str]) -> bool:
    if not keywords:
        return False
    threshold = max(1, int(len(keywords) * 0.7))
    norm = _normalize(doc_text)
    return sum(1 for kw in keywords if kw in norm) >= threshold


def calc_metrics(results: list) -> dict:
    import math
    n = len(results)
    if n == 0:
        return {}

    hit_1 = sum(1 for r in results if r["first_rank"] is not None and r["first_rank"] <= 1) / n
    hit_3 = sum(1 for r in results if r["first_rank"] is not None and r["first_rank"] <= 3) / n
    hit_5 = sum(1 for r in results if r["first_rank"] is not None and r["first_rank"] <= 5) / n

    mrr = 0.0
    for r in results:
        if r["first_rank"] is not None:
            mrr += 1.0 / r["first_rank"]
    mrr /= n

    ndcg_sum = 0.0
    for r in results:
        keywords = _extract_keywords(r["expected_answer"])
        rel_count = sum(1 for d in r["docs"][:TOP_K] if _doc_is_relevant(d["text"], keywords))
        dcg = 0.0
        for i, doc in enumerate(r["docs"][:TOP_K]):
            rel = 1 if _doc_is_relevant(doc["text"], keywords) else 0
            dcg += rel if i == 0 else rel / math.log2(i + 2)
        idcg = sum(1.0 / (math.log2(i + 2) if i > 0 else 1) for i in range(rel_count))
        ndcg_sum += dcg / idcg if idcg > 0 else 0.0
    ndcg = ndcg_sum / n

    precision = 0.0
    for r in results:
        top_docs = r["docs"][:TOP_K]
        if not top_docs:
            continue
        keywords = _extract_keywords(r["expected_answer"])
        rel = sum(1 for d in top_docs if _doc_is_relevant(d["text"], keywords))
        precision += rel / len(top_docs)
    precision /= n

    return {
        "hit@1": hit_1, "hit@3": hit_3, "hit@5": hit_5,
        "mrr": mrr, "ndcg@5": ndcg, "precision@5": precision,
    }


# ── 消融实验配置 ──

@dataclass
class AblationConfig:
    name: str
    hybrid_search: bool
    mmr: bool
    rerank: bool
    query_rewrite: bool


ABLATIONS = [
    AblationConfig("1.纯向量", False, False, False, False),
    AblationConfig("2.+BM25混合", True, False, False, False),
    AblationConfig("3.+MMR多样化", True, True, False, False),
    AblationConfig("4.+查询重写", True, True, False, True),
    AblationConfig("5.完整链路(+Rerank)", True, True, True, True),
]


async def run_ablation(config: AblationConfig, test_set: list) -> dict:
    """在指定配置下跑完整评测"""
    # 临时修改 settings
    settings.HYBRID_SEARCH_ENABLED = config.hybrid_search
    settings.MMR_ENABLED = config.mmr
    settings.RE_RANKING_ENABLED = config.rerank
    settings.QUERY_REWRITING_ENABLED = config.query_rewrite

    # 失效 BM25 缓存（配置变更后旧的混合检索索引可能不适用）
    retrieval_pipeline.invalidate_bm25(USER_ID)

    results = []
    start = time.monotonic()

    for item in test_set:
        question = item["question"]
        expected = item["answer"]

        docs = await retrieval_pipeline.search(USER_ID, question, TOP_K)

        keywords = _extract_keywords(expected)
        threshold = max(1, int(len(keywords) * 0.7))
        first_rank = None
        for rank, doc in enumerate(docs, 1):
            norm = _normalize(doc["text"])
            if sum(1 for kw in keywords if kw in norm) >= threshold:
                first_rank = rank
                break

        results.append({
            "question": question,
            "expected_answer": expected,
            "docs": docs,
            "first_rank": first_rank,
        })

    elapsed = time.monotonic() - start
    metrics = calc_metrics(results)
    metrics["elapsed_s"] = elapsed
    metrics["total_queries"] = len(test_set)

    return metrics


async def main():
    test_set_path = settings.PROJECT_ROOT / "data/uploads/测试集.json"
    with open(test_set_path, "r", encoding="utf-8") as f:
        test_set = json.load(f)

    print(f"消融实验 — {len(test_set)} 条测试集, Top-K={TOP_K}\n")

    all_results: list[dict] = []

    for config in ABLATIONS:
        print(f"  跑 {config.name}...")
        m = await run_ablation(config, test_set)
        m["config"] = config.name
        all_results.append(m)

    # 恢复默认
    settings.HYBRID_SEARCH_ENABLED = True
    settings.MMR_ENABLED = True
    settings.RE_RANKING_ENABLED = True
    settings.QUERY_REWRITING_ENABLED = True
    retrieval_pipeline.invalidate_bm25(USER_ID)

    # 打印对比表
    print(f"\n{'='*80}")
    print(f"  消融实验结果")
    print(f"{'='*80}")
    header = f"  {'配置':<22s} {'Hit@1':>7s} {'Hit@3':>7s} {'Hit@5':>7s} {'MRR':>7s} {'NDCG':>7s} {'耗时':>7s}"
    print(header)
    print(f"  {'─'*22} {'─'*7} {'─'*7} {'─'*7} {'─'*7} {'─'*7} {'─'*7}")

    baseline = all_results[0] if all_results else None
    final = all_results[-1] if all_results else None

    for r in all_results:
        line = (f"  {r['config']:<22s} {r['hit@1']:>6.1%} {r['hit@3']:>6.1%} "
                f"{r['hit@5']:>6.1%} {r['mrr']:>6.3f} {r['ndcg@5']:>6.3f} {r['elapsed_s']:>5.0f}s")
        print(line)

    # 组件贡献分析
    print(f"\n{'='*80}")
    print(f"  组件贡献分析")
    print(f"{'='*80}")

    for i in range(1, len(all_results)):
        prev = all_results[i - 1]
        curr = all_results[i]
        delta = curr["hit@5"] - prev["hit@5"]
        label = all_results[i]["config"].split(".", 1)[1] if "." in all_results[i]["config"] else all_results[i]["config"]
        direction = "+" if delta >= 0 else ""
        print(f"  {label:<20s}: Hit@5 {prev['hit@5']:.1%} → {curr['hit@5']:.1%} ({direction}{delta:+.1%})")

    if baseline and final:
        print(f"\n  总提升: Hit@5 {baseline['hit@5']:.1%} → {final['hit@5']:.1%} ({final['hit@5']-baseline['hit@5']:+.1%})")

    print()


if __name__ == "__main__":
    asyncio.run(main())
