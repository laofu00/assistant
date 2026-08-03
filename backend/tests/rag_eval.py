"""RAG 检索质量评测脚本

基于自建标注测试集，评估检索流水线的准确性。
计算指标：Hit Rate@K、MRR、Precision@K、Recall@K、NDCG@K。

用法：
    cd backend && .venv/Scripts/python tests/rag_eval.py

前置条件：
    1. 服务不需要运行（直接读 ChromaDB + 调 API）
    2. 确保 .env 中 DASHSCOPE_API_KEY 已配置
    3. 知识库已通过 Web 端上传文档
"""

import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import settings
from src.knowledge.retrieval import retrieval_pipeline

# ==================== 配置 ====================

USER_ID = "u05c42c5b"
TEST_SET_PATH = Path("data/uploads/测试集.json")
TOP_K = 5  # 检索返回条数

# ==================== 指标计算 ====================


def _normalize(text: str) -> str:
    """去空格、换行，统一中英文标点，用于模糊匹配"""
    # 去除空白
    text = re.sub(r"\s+", "", text)
    # 统一全半角标点
    text = text.replace("）", ")").replace("（", "(")
    text = text.replace("：", ":").replace("，", ",").replace("。", ".")
    text = text.replace(""", "\"").replace(""", "\"")
    text = text.replace("'", "'").replace("'", "'")
    # 统一顿号为逗号
    text = text.replace("、", ",")
    text = text.replace("；", ";")
    return text.lower()


def _extract_keywords(text: str) -> set[str]:
    """提取答案关键词：中英文边界分离 + jieba 中文分词"""
    import jieba

    # 标点统一
    t = text
    t = t.replace("）", ")").replace("（", "(")
    t = t.replace("：", ":").replace("，", ",").replace("。", ".")
    t = t.replace(""", "\"").replace(""", "\"")
    t = t.replace("、", ",").replace("；", ";")
    t = t.lower()

    # 在中英文边界插入空格，避免 "user_id和session_id" 粘在一起
    t = re.sub(r"([a-z0-9])([\u4e00-\u9fff])", r"\1 \2", t)
    t = re.sub(r"([\u4e00-\u9fff])([a-z0-9])", r"\1 \2", t)

    # 提取英文/数字关键词
    eng_nums = set(re.findall(r"[a-z][a-z0-9_]+", t))
    # 纯数字
    nums = set(re.findall(r"\d+", text))

    # 中文用 jieba 分词
    zh_text = re.sub(r"[a-z0-9_]+", " ", t)
    zh_words = {w.strip() for w in jieba.cut(zh_text) if len(w.strip()) >= 1}
    # 过滤单字中文词（除非是数字）
    zh_words = {w for w in zh_words if len(w) >= 2 or w.isdigit()}

    return eng_nums | nums | zh_words


def _is_answer_found(retrieved_docs: list[dict], expected_answer: str) -> bool:
    """检查答案关键词是否在任一回召文档中出现（70% 关键词命中即成功）"""
    keywords = _extract_keywords(expected_answer)
    if not keywords:
        return False
    threshold = max(1, int(len(keywords) * 0.7))  # 至少 70% 命中
    for doc in retrieved_docs:
        norm_doc = _normalize(doc["text"])
        matched = sum(1 for kw in keywords if kw in norm_doc)
        if matched >= threshold:
            return True
    return False


def _get_first_relevant_rank(retrieved_docs: list[dict], expected_answer: str) -> int | None:
    """返回第一个达到 70% 关键词命中率的文档排名（1-based）"""
    keywords = _extract_keywords(expected_answer)
    if not keywords:
        return None
    threshold = max(1, int(len(keywords) * 0.7))
    for rank, doc in enumerate(retrieved_docs, 1):
        norm_doc = _normalize(doc["text"])
        matched = sum(1 for kw in keywords if kw in norm_doc)
        if matched >= threshold:
            return rank
    return None


def calc_hit_rate_at_k(results: list[dict], k: int) -> float:
    """Hit Rate@K：前 K 条中至少有一条包含答案的题目比例"""
    if not results:
        return 0.0
    hits = sum(1 for r in results if r["first_rank"] is not None and r["first_rank"] <= k)
    return hits / len(results)


def calc_mrr(results: list[dict]) -> float:
    """MRR：第一个正确答案倒数排名的均值"""
    if not results:
        return 0.0
    reciprocal_sum = 0.0
    for r in results:
        rank = r["first_rank"]
        if rank is not None:
            reciprocal_sum += 1.0 / rank
    return reciprocal_sum / len(results)


def _doc_is_relevant(doc_text: str, keywords: set[str]) -> bool:
    """70% 关键词命中即为相关"""
    if not keywords:
        return False
    threshold = max(1, int(len(keywords) * 0.7))
    norm = _normalize(doc_text)
    return sum(1 for kw in keywords if kw in norm) >= threshold


def calc_precision_at_k(results: list[dict], k: int) -> float:
    """Precision@K：前 K 条中相关文档占比（每题取平均）"""
    if not results:
        return 0.0
    precisions = []
    for r in results:
        top_k_docs = r["docs"][:k]
        if not top_k_docs:
            precisions.append(0.0)
            continue
        keywords = _extract_keywords(r["expected_answer"])
        relevant = sum(1 for d in top_k_docs if _doc_is_relevant(d["text"], keywords))
        precisions.append(relevant / len(top_k_docs))
    return sum(precisions) / len(precisions)


def calc_recall_at_k(results: list[dict], total_relevant: int = 1) -> float:
    """Recall@K：前 K 条中找到的相关文档 / 总相关文档（简化：默认每题 1 个正确答案）"""
    if not results:
        return 0.0
    recalls = []
    for r in results:
        top_k_docs = r["docs"][:TOP_K]
        keywords = _extract_keywords(r["expected_answer"])
        found = sum(1 for d in top_k_docs if _doc_is_relevant(d["text"], keywords))
        recalls.append(min(found / total_relevant, 1.0))
    return sum(recalls) / len(recalls)


def calc_ndcg_at_k(results: list[dict], k: int) -> float:
    """NDCG@K：归一化折损累计增益（简化：相关=1，不相关=0）"""
    import math
    if not results:
        return 0.0
    ndcg_scores = []
    for r in results:
        keywords = _extract_keywords(r["expected_answer"])
        dcg = 0.0
        rel_count = 0
        for i, doc in enumerate(r["docs"][:k]):
            rel = 1 if _doc_is_relevant(doc["text"], keywords) else 0
            if rel:
                rel_count += 1
            if i == 0:
                dcg += rel
            else:
                dcg += rel / math.log2(i + 2)
        # IDCG：理想情况是所有相关文档排在前面
        idcg = 0.0
        for i in range(min(rel_count, k)):
            idcg += 1.0 if i == 0 else 1.0 / math.log2(i + 2)
        ndcg_scores.append(dcg / idcg if idcg > 0 else 0.0)
    return sum(ndcg_scores) / len(ndcg_scores)


# ==================== 主评测流程 ====================


async def run_evaluation():
    # 1. 加载测试集
    test_set_path = settings.PROJECT_ROOT / TEST_SET_PATH
    if not test_set_path.exists():
        print(f"❌ 测试集不存在: {test_set_path}")
        return

    with open(test_set_path, "r", encoding="utf-8") as f:
        test_set: list[dict[str, str]] = json.load(f)
    print(f"  加载测试集: {len(test_set)} 条问答对")

    # 2. 确认知识库有数据
    from src.knowledge.vector_store import vector_store
    doc_count = vector_store.count(USER_ID)
    if doc_count == 0:
        print("❌ 知识库为空，请先通过 Web 端上传文档！")
        return
    filenames = vector_store.list_filenames(USER_ID)
    print(f"  知识库: {doc_count} chunks, {len(filenames)} 个文件")
    for fn in filenames:
        print(f"     - {fn}")

    # 3. 逐题评测
    print(f"\n  开始评测 (top_k={TOP_K})...")
    results: list[dict[str, Any]] = []
    total_start = time.monotonic()

    for idx, item in enumerate(test_set):
        question = item["question"]
        expected = item["answer"]

        q_start = time.monotonic()
        try:
            docs = await retrieval_pipeline.search(USER_ID, question, TOP_K)
        except Exception as e:
            print(f"  [{idx + 1:3d}] ❌ 检索异常: {e}")
            docs = []
        q_time = (time.monotonic() - q_start) * 1000

        first_rank = _get_first_relevant_rank(docs, expected)
        found = first_rank is not None

        results.append({
            "index": idx + 1,
            "question": question,
            "expected_answer": expected,
            "docs": docs,
            "first_rank": first_rank,
            "found": found,
            "time_ms": q_time,
        })

        status = "OK" if found else "FAIL"
        rank_str = f"rank={first_rank}" if found else "miss"
        print(f"  [{idx + 1:3d}] {status} {rank_str}  {question[:50]}...")

    total_time = time.monotonic() - total_start

    # 4. 计算指标
    print("\n" + "=" * 60)
    print("  RAG 检索质量报告")
    print("=" * 60)
    print(f"  测试集规模: {len(test_set)} 条")
    print(f"  Top-K:       {TOP_K}")
    print(f"  评测耗时:    {total_time:.1f}s")
    print()

    hit_1 = calc_hit_rate_at_k(results, 1)
    hit_3 = calc_hit_rate_at_k(results, 3)
    hit_5 = calc_hit_rate_at_k(results, 5)
    mrr = calc_mrr(results)
    precision = calc_precision_at_k(results, TOP_K)
    recall = calc_recall_at_k(results)
    ndcg = calc_ndcg_at_k(results, TOP_K)

    print("  核心指标:")
    print(f"    Hit Rate@1:     {hit_1:.2%}")
    print(f"    Hit Rate@3:     {hit_3:.2%}")
    print(f"    Hit Rate@5:     {hit_5:.2%}")
    print(f"    MRR:            {mrr:.4f}")
    print(f"    Precision@{TOP_K}:   {precision:.2%}")
    print(f"    Recall@{TOP_K}:      {recall:.2%}")
    print(f"    NDCG@{TOP_K}:        {ndcg:.4f}")

    # 5. 失败案例分析
    failed = [r for r in results if not r["found"]]
    if failed:
        print(f"\n  === 失败案例 ({len(failed)} 条) ===")
        for r in failed:
            print(f"    [{r['index']:3d}] {r['question'][:80]}")
            print(f"           预期答案: {r['expected_answer'][:80]}")
            if r["docs"]:
                top1 = r["docs"][0]["text"][:100]
                print(f"           Top-1 片段: {top1}...")
            print()

    # 6. 时延统计
    times = [r["time_ms"] for r in results]
    times_sorted = sorted(times)
    p50 = times_sorted[len(times_sorted) // 2]
    p95 = times_sorted[int(len(times_sorted) * 0.95)]
    print(f"  检索时延 (ms):")
    print(f"    P50: {p50:.0f}ms")
    print(f"    P95: {p95:.0f}ms")
    print(f"    平均: {sum(times)/len(times):.0f}ms")
    print()

    # 7. 分文档统计（通过 top-1 文档的 source 归因）
    print("  分文档命中分布 (按 Top-1 source):")
    doc_hits: dict[str, list[int]] = {}
    for r in results:
        if r["docs"]:
            src = r["docs"][0]["metadata"].get("source", "unknown")
            doc_hits.setdefault(src, []).append(1 if r["found"] else 0)
    for src, stats in sorted(doc_hits.items()):
        acc = sum(stats) / len(stats) if stats else 0
        print(f"    {src[:60]}: {sum(stats)}/{len(stats)} ({acc:.1%})")

    # 8. 简历话术建议
    print("\n" + "=" * 60)
    print("  简历话术建议")
    print("=" * 60)
    print(f'  "基于自建的 {len(test_set)} 条领域问答测试集，采用自研评测框架评估，')
    print(f'   RAG 检索命中率（Hit Rate@5）达 {hit_5:.0%}，MRR 为 {mrr:.3f}，')
    print(f'   上下文相关度（NDCG@5）为 {ndcg:.3f}。"')

    return results


if __name__ == "__main__":
    asyncio.run(run_evaluation())
