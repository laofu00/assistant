"""知识检索流水线 — 完整的 6 步 RAG 管道

对齐 Java 版 KnowledgeServiceImpl 的检索流程：
查询重写 → 混合检索(向量+FTS) → RRF融合 → MMR多样化 → LLM重排序 → RAG生成
"""

import re
from typing import Any

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from src.core.config import settings
from src.knowledge.vector_store import VectorStore, vector_store


# ==================== 停用词表 ====================

_STOP_WORDS: set[str] = {
    "的", "了", "是", "在", "有", "和", "就", "不", "人", "都",
    "一", "个", "上", "也", "很", "到", "说", "要", "去", "你",
    "会", "着", "没有", "看看", "知道", "可以", "这个", "那个",
    "自己", "因为", "所以", "但是", "如果", "虽然", "而且", "或者",
    "然后", "已经", "还是", "只是", "不是", "没",
    "可能", "应该", "能够", "什么", "怎么", "如何", "怎样", "哪个",
}


class RetrievalPipeline:
    """完整检索流水线"""

    def __init__(self, vs: VectorStore | None = None) -> None:
        self.vs = vs or vector_store
        self._llm: ChatOpenAI | None = None
        self._embeddings: OpenAIEmbeddings | None = None

    @property
    def llm(self) -> ChatOpenAI:
        if self._llm is None:
            self._llm = ChatOpenAI(
                model=settings.MODEL_NAME,
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL,
                temperature=0,
            )
        return self._llm

    @property
    def embeddings(self) -> OpenAIEmbeddings:
        if self._embeddings is None:
            self._embeddings = OpenAIEmbeddings(
                model=settings.EMBEDDING_MODEL,
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL,
            )
        return self._embeddings

    # ==================== 步骤 1: 查询重写 ====================

    async def _rewrite_query(self, query: str) -> str:
        """LLM 优化查询：去除口语化，提取核心关键词"""
        if not settings.QUERY_REWRITING_ENABLED:
            return query
        try:
            prompt = (
                "你是一个搜索查询优化助手。请分析用户的原始查询，将其重写为更适合向量检索的搜索查询。\n"
                "要求：\n"
                "1. 去除口语化表达（如'帮我找一下''我想知道''有没有关于'等）\n"
                "2. 提取核心关键词和概念\n"
                "3. 保持语义完整，不要改变原意\n"
                "4. 只返回重写后的查询，不要解释，不要加引号\n\n"
                f"原始查询：{query}"
            )
            result = await self.llm.ainvoke(prompt)
            rewritten = result.content
            if rewritten and isinstance(rewritten, str) and rewritten.strip():
                return rewritten.strip()
        except Exception:
            pass
        return query

    # ==================== 步骤 2: 混合检索 ====================

    def _calculate_threshold(self, query: str) -> float:
        """动态相似度阈值"""
        if not settings.DYNAMIC_THRESHOLD_ENABLED:
            return settings.SIMILARITY_THRESHOLD_BASE
        q_len = len(query)
        if q_len > 100:
            return min(0.6, settings.SIMILARITY_THRESHOLD_BASE + 0.4)
        elif q_len > 50:
            return min(0.55, settings.SIMILARITY_THRESHOLD_BASE + 0.3)
        elif q_len > 20:
            return min(0.5, settings.SIMILARITY_THRESHOLD_BASE + 0.2)
        else:
            return max(0.15, settings.SIMILARITY_THRESHOLD_BASE - 0.02)

    def _keyword_search(self, query: str, user_id: str, top_k: int) -> list[dict]:
        """关键词检索（模拟 FTS，基于 metadata 过滤 + 文本关键词匹配）"""
        keywords = self._extract_keywords(query)
        if not keywords:
            return []

        # 用每个关键词分别检索，合并结果
        results: list[dict] = []
        seen: set[str] = set()
        for kw in keywords.split():
            for doc in self.vs.search(user_id, kw, top_k):
                text = doc["text"]
                key = str(hash(text))
                if key not in seen:
                    seen.add(key)
                    results.append(doc)
        return results[:top_k]

    @staticmethod
    def _extract_keywords(query: str) -> str:
        """提取 FTS 关键词（过滤停用词）"""
        cleaned = re.sub(r"(?i)(帮我|我想|我要|请问|有没有|给我|找一下|查一下|看一下)", " ", query)
        cleaned = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9\s]", " ", cleaned)
        words = cleaned.split()
        meaningful = [w for w in words if len(w) >= 2 and w not in _STOP_WORDS]
        result = " ".join(meaningful).strip()
        return result if len(result) >= 2 else ""

    def _hybrid_search(self, query: str, user_id: str, top_k: int) -> list[dict]:
        """混合检索：向量 + 关键词"""
        vector_k = top_k * settings.VECTOR_CANDIDATE_MULTIPLIER
        fts_k = top_k * settings.FTS_CANDIDATE_MULTIPLIER

        vector_docs = self.vs.search(user_id, query, vector_k)
        keyword_docs = self._keyword_search(query, user_id, fts_k)

        return self._rrf_merge(vector_docs, keyword_docs, top_k)

    # ==================== 步骤 3: RRF 融合 ====================

    @staticmethod
    def _rrf_merge(vector_docs: list[dict], fts_docs: list[dict], top_k: int) -> list[dict]:
        """Reciprocal Rank Fusion"""
        k = settings.RRF_CONSTANT_K
        scores: dict[int, float] = {}
        doc_map: dict[int, dict] = {}

        for docs, is_vector in [(vector_docs, True), (fts_docs, False)]:
            for rank, doc in enumerate(docs):
                key = hash(doc["text"])
                score = 1.0 / (k + rank + 1)
                scores[key] = scores.get(key, 0) + score
                if key not in doc_map:
                    doc_map[key] = doc

        sorted_keys = sorted(scores, key=scores.get, reverse=True)[:top_k]
        return [doc_map[k] for k in sorted_keys if k in doc_map]

    # ==================== 步骤 4: MMR 多样化 ====================

    def _mmr_diversify(self, docs: list[dict], top_k: int) -> list[dict]:
        """最大边界相关性算法"""
        if not settings.MMR_ENABLED or len(docs) <= top_k:
            return docs[:top_k]

        selected: list[dict] = [docs[0]]
        remaining: list[dict] = list(docs[1:])

        while len(selected) < top_k and remaining:
            best_idx = -1
            best_score = float("-inf")

            for i, candidate in enumerate(remaining):
                relevance = 1.0 / (1 + i)
                max_sim = max(
                    (self._jaccard_similarity(candidate["text"], s["text"]) for s in selected),
                    default=0,
                )
                mmr_score = settings.MMR_LAMBDA * relevance - (1 - settings.MMR_LAMBDA) * max_sim

                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = i

            if best_idx >= 0:
                selected.append(remaining.pop(best_idx))
            else:
                break

        if len(selected) < top_k:
            selected.extend(remaining[: top_k - len(selected)])

        return selected

    @staticmethod
    def _jaccard_similarity(text1: str, text2: str) -> float:
        """n-gram Jaccard 相似度"""
        n = 3
        s1 = text1[:200]
        s2 = text2[:200]
        grams1 = {s1[i : i + n] for i in range(len(s1) - n + 1)}
        grams2 = {s2[i : i + n] for i in range(len(s2) - n + 1)}
        if not grams1 or not grams2:
            return 0.0
        intersection = grams1 & grams2
        union = grams1 | grams2
        return len(intersection) / len(union)

    # ==================== 步骤 5: LLM 重排序 ====================

    async def _rerank(self, docs: list[dict], query: str, top_k: int) -> list[dict]:
        """LLM 重排序（>5 个结果时触发）"""
        if not settings.RE_RANKING_ENABLED or len(docs) <= settings.RE_RANK_THRESHOLD:
            return docs[:top_k]

        try:
            sb = "请根据与用户查询的相关性，对以下知识片段进行排序。\n"
            sb += "只输出片段编号的排列顺序（从最相关到最不相关），以英文逗号分隔，不要解释。\n\n"
            sb += f"用户查询：{query}\n\n"
            for i, doc in enumerate(docs):
                text = doc["text"][:200]
                sb += f"片段{i + 1}：{text}\n\n"
            sb += "请输出排序后的片段编号（逗号分隔，如：3,1,5,2,4）："

            result = await self.llm.ainvoke(sb)
            content = result.content
            if not content or not isinstance(content, str):
                return docs[:top_k]

            indices: list[int] = []
            for part in re.split(r"[,\s]+", content.strip()):
                try:
                    idx = int(part) - 1
                    if 0 <= idx < len(docs) and idx not in indices:
                        indices.append(idx)
                except ValueError:
                    pass

            if len(indices) < min(3, len(docs)):
                return docs[:top_k]

            reranked = [docs[i] for i in indices]
            remaining = [d for i, d in enumerate(docs) if i not in set(indices)]
            reranked.extend(remaining)
            return reranked[:top_k]
        except Exception:
            return docs[:top_k]

    # ==================== 步骤 6: RAG 生成 ====================

    async def _generate_rag(self, query: str, docs: list[dict]) -> str:
        """基于检索结果生成 RAG 回答"""
        if not docs:
            return "抱歉，知识库中未找到相关信息。"

        context = "基于以下知识片段回答问题：\n\n"
        for i, doc in enumerate(docs):
            context += f"片段 {i + 1}: {doc['text']}\n\n"

        prompt = f"""请根据以下知识片段回答问题。请遵循以下要求：
1. 如果知识片段中没有相关信息，请明确说明"根据已有知识无法回答"
2. 如果知识片段中有相关信息，请引用具体的片段编号（例如：根据片段1、片段3）
3. 请以自然、流畅的语言组织回答，不要直接复制片段内容
4. 如果信息不完全匹配或存在不确定性，请说明

问题：{query}

{context}

请给出准确、简洁的回答（可引用片段编号）："""

        try:
            result = await self.llm.ainvoke(prompt)
            return str(result.content) if result.content else "生成答案时发生错误。"
        except Exception:
            return "生成答案时发生错误，请稍后重试。"

    # ==================== 公开接口 ====================

    async def search(self, user_id: str, query: str, top_k: int = 5) -> list[dict]:
        """执行完整检索（步骤 1-5）"""
        rewritten = await self._rewrite_query(query)

        if settings.HYBRID_SEARCH_ENABLED:
            docs = self._hybrid_search(rewritten, user_id, top_k)
        else:
            docs = self.vs.search(user_id, rewritten, top_k)

        docs = self._mmr_diversify(docs, top_k)
        docs = await self._rerank(docs, query, top_k)
        return docs

    async def search_with_rag(self, user_id: str, query: str, top_k: int = 5) -> str:
        """执行完整检索 + RAG 生成（步骤 1-6）"""
        docs = await self.search(user_id, query, top_k)
        return await self._generate_rag(query, docs)

    async def search_in_file(self, user_id: str, query: str, filename: str, top_k: int = 5) -> list[dict]:
        """在指定文件中检索"""
        rewritten = await self._rewrite_query(query)
        docs = self.vs.search(user_id, rewritten, top_k * settings.VECTOR_CANDIDATE_MULTIPLIER, where={"source": filename})
        docs = self._mmr_diversify(docs, top_k)
        return docs

    async def search_in_file_with_rag(self, user_id: str, query: str, filename: str, top_k: int = 5) -> str:
        """在指定文件中检索 + RAG 生成"""
        docs = await self.search_in_file(user_id, query, filename, top_k)
        if not docs:
            return f"抱歉，未在文件 [{filename}] 中找到相关的知识信息。"
        return await self._generate_rag(query, docs)


# 全局实例
retrieval_pipeline = RetrievalPipeline()
