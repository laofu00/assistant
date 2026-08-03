"""RAG 生成质量评估 — Faithfulness + Answer Relevancy + Context Relevancy

用法：
    cd backend && .venv/Scripts/python tests/rag_gen_eval.py

评测方法：
    - Faithfulness: 拆解生成答案为独立陈述，检查每条是否被检索文档支撑
    - Answer Relevancy: 生成答案与问题的语义相关性
    - Context Relevancy: 检索文档与问题的相关性（Hit Rate 的软版本）

注意：每道题都需要 LLM 调用来生成答案，81 题预计 ¥0.15-0.20
"""

import asyncio
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import settings
from src.core.llm_factory import get_llm
from src.knowledge.retrieval import retrieval_pipeline

USER_ID = "u05c42c5b"
TOP_K = 5

# 只测 20 条避免费用过高
SAMPLE_SIZE = 20


def _split_claims(text: str) -> list[str]:
    """将文本拆分为独立陈述句"""
    # 按句号、分号、换行拆分
    parts = re.split(r"[。；;.\n]", text)
    return [p.strip() for p in parts if len(p.strip()) > 5]


async def evaluate_faithfulness(answer: str, docs: list[dict]) -> dict:
    """
    Faithfulness: 拆解答案为陈述句，用 LLM 判断每条是否被文档支撑。
    不引入 ragas 依赖，直接用小模型做蕴含判断。
    """
    claims = _split_claims(answer)
    if not claims:
        return {"score": 0, "supported": 0, "total": 0}

    # 拼接上下文
    context = "\n\n".join(f"[{i+1}] {d['text'][:500]}" for i, d in enumerate(docs[:TOP_K]))

    llm = get_llm(temperature=0, streaming=False)
    supported = 0

    for claim in claims[:8]:  # 最多评估 8 个陈述
        prompt = (
            "你是一个事实核查助手。请判断以下陈述是否被提供的文档片段支撑。\n\n"
            f"文档片段：\n{context}\n\n"
            f"陈述：{claim}\n\n"
            "只回答 YES 或 NO。如果陈述的内容在文档中有明确对应，回答 YES；"
            "如果文档中没有相关支撑或陈述超出了文档范围，回答 NO。"
        )
        try:
            result = await llm.ainvoke(prompt)
            if result.content and "YES" in str(result.content).upper():
                supported += 1
        except Exception:
            pass

    score = supported / len(claims[:8]) if claims[:8] else 0
    return {"score": score, "supported": supported, "total": min(len(claims), 8)}


async def evaluate_answer_relevancy(answer: str, question: str) -> float:
    """Answer Relevancy: 生成答案与问题的相关性"""
    llm = get_llm(temperature=0, streaming=False)
    prompt = (
        "评估以下回答与问题的相关性。1-5 分，1=完全不相关，5=高度相关。只输出数字。\n\n"
        f"问题：{question}\n"
        f"回答：{answer[:500]}\n\n"
        "分数："
    )
    try:
        result = await llm.ainvoke(prompt)
        content = str(result.content).strip()
        match = re.search(r"([1-5])", content)
        if match:
            return int(match.group(1)) / 5.0
    except Exception:
        pass
    return 0.0


def evaluate_context_relevancy(docs: list[dict], question: str) -> float:
    """Context Relevancy: 检索文档与问题的关键词重合度（Hit Rate 的软版本）"""
    # 拼接所有检索文档
    all_text = " ".join(d["text"] for d in docs[:TOP_K])

    # 提取问题关键词
    import jieba
    q_words = set(jieba.cut(question))
    q_words = {w.strip() for w in q_words if len(w.strip()) >= 2}

    if not q_words:
        return 0.0

    matched = sum(1 for w in q_words if w in all_text)
    return matched / len(q_words)


async def main():
    test_set_path = settings.PROJECT_ROOT / "data/uploads/测试集.json"
    with open(test_set_path, "r", encoding="utf-8") as f:
        test_set = json.load(f)

    # 抽样
    import random
    random.seed(42)
    sample = random.sample(test_set, min(SAMPLE_SIZE, len(test_set)))

    print(f"生成质量评估 — {len(sample)} 题抽样\n")

    faith_scores = []
    relevancy_scores = []
    context_scores = []
    times = []

    for idx, item in enumerate(sample):
        question = item["question"]

        q_start = time.monotonic()
        try:
            docs = await retrieval_pipeline.search(USER_ID, question, TOP_K)
            answer = await retrieval_pipeline._generate_rag(question, docs)
        except Exception as e:
            print(f"  [{idx+1:2d}] ERROR: {e}")
            continue
        q_time = (time.monotonic() - q_start) * 1000
        times.append(q_time)

        faith = await evaluate_faithfulness(answer, docs)
        relevancy = await evaluate_answer_relevancy(answer, question)
        ctx_rel = evaluate_context_relevancy(docs, question)

        faith_scores.append(faith["score"])
        relevancy_scores.append(relevancy)
        context_scores.append(ctx_rel)

        print(f"  [{idx+1:2d}] Faith={faith['score']:.2f} "
              f"AnswerRel={relevancy:.2f} CtxRel={ctx_rel:.2f} "
              f"({q_time:.0f}ms) {question[:40]}...")

    # 汇总
    n = len(faith_scores)
    if n == 0:
        print("无有效结果")
        return

    avg_faith = sum(faith_scores) / n
    avg_rel = sum(relevancy_scores) / n
    avg_ctx = sum(context_scores) / n
    avg_time = sum(times) / n

    print(f"\n{'='*60}")
    print(f"  生成评估结果")
    print(f"{'='*60}")
    print(f"  样本数: {n}")
    print(f"  平均耗时: {avg_time:.0f}ms/题")
    print()
    print(f"  Faithfulness:       {avg_faith:.2f}  (生成答案忠实于文档)")
    print(f"  Answer Relevancy:   {avg_rel:.2f}  (答案与问题相关性)")
    print(f"  Context Relevancy:  {avg_ctx:.2f}  (检索文档与问题相关性)")
    print()

    print(f"{'='*60}")
    print(f"  简历话术建议")
    print(f"{'='*60}")
    print(f'  "基于自建的 81 条测试集，在 {n} 题抽样生成评估中：')
    print(f'   Faithfulness 达 {avg_faith:.2f}，Answer Relevancy {avg_rel:.2f}，')
    print(f'   Context Relevancy {avg_ctx:.2f}，')
    print(f'   平均端到端生成耗时 {avg_time:.0f}ms。"')


if __name__ == "__main__":
    asyncio.run(main())
