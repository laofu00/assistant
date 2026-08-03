"""知识检索流水线 — 完整的 6 步 RAG 管道

对齐 Java 版 KnowledgeServiceImpl 的检索流程：
查询重写 → 混合检索(向量+BM25) → RRF融合 → MMR多样化 → gte-rerank重排序 → RAG生成
"""

import re

from loguru import logger

from src.core.config import settings
from src.core.llm_factory import get_llm
from src.knowledge.vector_store import VectorStore, vector_store


def _track_rerank_usage(total_tokens: int, doc_count: int) -> None:
    """记录重排序 token 用量到统一统计队列"""
    try:
        from src.core.llm_factory import _trace_ctx
        from src.token.token_callback import _token_queue

        ctx = _trace_ctx.get()
        if ctx is None or not ctx.get("trace_id"):
            return
        _token_queue.append({
            "trace_id": ctx["trace_id"],
            "session_id": ctx.get("session_id", ""),
            "user_id": ctx.get("user_id", ""),
            "model_name": "gte-rerank",
            "input_tokens": total_tokens,
            "output_tokens": 0,
            "total_tokens": total_tokens,
            "intent_type": "RERANK",
            "call_purpose": f"rerank_{doc_count}_docs",
            "tool_called": False,
            "tool_names": "",
        })
    except Exception:
        pass


# ==================== 查询简化判断 ====================

# 口语化/自然语言问句模式
_QUESTION_PATTERNS = re.compile(
    r"[?？]|什么|怎么|如何|为什么|哪个|哪些|"
    r"帮我|我想|我要|能不能|可不可以|有没有|"
    r"请问|麻烦|找一下|查一下|看一下|告诉我"
)


def _is_simple_query(query: str) -> bool:
    """短查询（≤20字）且无问句/口语模式，跳过 LLM 重写"""
    return len(query) <= 20 and not _QUESTION_PATTERNS.search(query)


# ==================== 中英文混合分词（模块级复用） ====================


def _tokenize(text: str) -> list[str]:
    """中英混合分词：英文单词 + 中文单字 bigram"""
    tokens: list[str] = []
    buf = ""
    for ch in text:
        if ch.isascii() and ch.isalpha():
            buf += ch
        else:
            if buf:
                tokens.append(buf.lower())
                buf = ""
            if not ch.isspace() and ch.isalnum():
                tokens.append(ch)
    if buf:
        tokens.append(buf.lower())
    # 中文 bigram
    zh = [t for t in tokens if not t.isascii()]
    bigrams = [zh[i] + zh[i + 1] for i in range(len(zh) - 1)]
    return tokens + bigrams


class RetrievalPipeline:
    """完整检索流水线"""

    def __init__(self, vs: VectorStore | None = None) -> None:
        self.vs = vs or vector_store
        self._llm = None
        # BM25 索引缓存：{user_id: (doc_count, bm25, docs_list)}
        self._bm25_cache: dict[str, tuple[int, object, list[dict]]] = {}

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm(temperature=0, streaming=False)
        return self._llm

    # ==================== 步骤 1: 查询重写 ====================

    async def _rewrite_query(self, query: str) -> str:
        """LLM 优化查询：去除口语化，提取核心关键词（短查询/纯关键词跳过）"""
        if not settings.QUERY_REWRITING_ENABLED:
            return query
        if _is_simple_query(query):
            return query
        from src.core.llm_factory import update_trace_context
        update_trace_context(intent_type="QUERY_REWRITE")
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

    def _get_or_build_bm25(self, user_id: str) -> tuple[object, list[dict]]:
        """获取 BM25 索引（惰性缓存：文档数变化时自动重建）"""
        from rank_bm25 import BM25Okapi

        current_count = self.vs.count(user_id)
        cached = self._bm25_cache.get(user_id)
        if cached and cached[0] == current_count:
            return cached[1], cached[2]

        # 缓存失效或首次：重建索引
        docs = self.vs.get_all_docs(user_id)
        if not docs:
            self._bm25_cache[user_id] = (0, None, [])
            return None, []

        corpus = [_tokenize(d["text"]) for d in docs]
        bm25 = BM25Okapi(corpus)
        self._bm25_cache[user_id] = (current_count, bm25, docs)
        return bm25, docs

    def invalidate_bm25(self, user_id: str) -> None:
        """文档变更后主动失效 BM25 缓存"""
        self._bm25_cache.pop(user_id, None)

    def _keyword_search(self, query: str, user_id: str, top_k: int) -> list[dict]:
        """BM25 稀疏检索（惰性缓存索引，零嵌入调用）"""
        bm25, docs = self._get_or_build_bm25(user_id)
        if not bm25 or not docs:
            return []

        scores = bm25.get_scores(_tokenize(query))

        ranked = sorted(zip(scores, docs), key=lambda x: x[0], reverse=True)
        return [
            {"text": d["text"], "metadata": d["metadata"], "distance": float(s)}
            for s, d in ranked[:top_k] if s > 0
        ]

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
        """分词级 Jaccard 相似度（jieba 中文分词 + 空格英文分词）"""
        import jieba

        def _word_tokenize(text: str) -> set[str]:
            # 中文用 jieba 分词，英文/数字保持原样
            tokens: set[str] = set()
            buf = ""
            for ch in text[:200]:
                if ch.isascii() and (ch.isalpha() or ch.isdigit()):
                    buf += ch
                else:
                    if buf:
                        tokens.add(buf.lower())
                        buf = ""
                    if not ch.isspace():
                        # jieba 切单个中文词
                        for word in jieba.cut(ch):
                            word = word.strip()
                            if word:
                                tokens.add(word)
            if buf:
                tokens.add(buf.lower())
            return tokens

        tokens1 = _word_tokenize(text1)
        tokens2 = _word_tokenize(text2)
        if not tokens1 or not tokens2:
            return 0.0
        intersection = tokens1 & tokens2
        union = tokens1 | tokens2
        return len(intersection) / len(union)

    # ==================== 步骤 5: 重排序（gte-rerank） ====================

    async def _rerank(self, docs: list[dict], query: str, top_k: int) -> list[dict]:
        """gte-rerank 专用重排序模型（比 LLM 更快更便宜）"""
        if not settings.RE_RANKING_ENABLED or len(docs) <= settings.RE_RANK_THRESHOLD:
            return docs[:top_k]

        try:
            from dashscope import TextReRank

            texts = [doc["text"][:500] for doc in docs]  # gte-rerank 最大 8192 tokens
            response = TextReRank.call(
                model="gte-rerank",
                query=query,
                documents=texts,
                top_n=top_k,
                api_key=settings.OPENAI_API_KEY,
            )

            if response.status_code != 200:
                logger.warning(f"重排序失败: {response.code} {response.message}")
                return docs[:top_k]

            # 记录 token 用量
            usage = getattr(response, "usage", None)
            if usage and usage.total_tokens:
                _track_rerank_usage(usage.total_tokens, len(docs))

            results = response.output.results if response.output else []
            if not results:
                return docs[:top_k]

            reranked = [docs[r.index] for r in results if r.index < len(docs)]
            return reranked[:top_k]
        except Exception as e:
            logger.warning(f"重排序异常: {e}")
            return docs[:top_k]

    # ==================== 步骤 6: RAG 生成 ====================

    async def _generate_rag(self, query: str, docs: list[dict]) -> str:
        """基于检索结果生成 RAG 回答"""
        if not docs:
            return "抱歉，知识库中未找到相关信息。"
        from src.core.llm_factory import update_trace_context
        update_trace_context(intent_type="RAG_GENERATE")

        context = "基于以下知识片段回答问题：\n\n"
        for i, doc in enumerate(docs):
            section = doc.get("metadata", {}).get("section", "")
            label = f"片段 {i + 1}" + (f"（章节：{section}）" if section else "")
            context += f"{label}: {doc['text']}\n\n"

        try:
            from langchain_core.messages import SystemMessage, HumanMessage

            result = await self.llm.ainvoke([
                SystemMessage(content=(
                    "你是严格的文档问答助手。你的所有回答必须100%基于用户提供的知识片段。\n\n"
                    "核心规则：\n"
                    "1. 只能使用知识片段中明确写出的信息，禁止使用训练数据或常识补充\n"
                    "2. 如果片段中没有相关信息，直接回复\"根据已有知识无法回答\"，不要猜测或延伸\n"
                    "3. 引用时标注片段编号（如：根据片段1、片段3）\n"
                    "4. 回答保持简洁，不要展开片段中没有的内容"
                )),
                HumanMessage(content=(
                    f"问题：{query}\n\n"
                    f"{context}\n\n"
                    "请严格基于以上片段回答，不要添加任何额外信息。"
                )),
            ])
            return str(result.content) if result.content else "生成答案时发生错误。"
        except Exception:
            return "生成答案时发生错误，请稍后重试。"

    # ==================== 公开接口 ====================

    async def search(self, user_id: str, query: str, top_k: int = 5) -> list[dict]:
        """执行完整检索（步骤 1-5），自适应跳过不适用的组件"""
        # 自适应查询重写：小知识库跳过（LLM 重写反引入噪声）
        if settings.QUERY_REWRITING_ENABLED and self.vs.count(user_id) >= settings.QUERY_REWRITE_MIN_DOCS:
            rewritten = await self._rewrite_query(query)
        else:
            rewritten = query

        if settings.HYBRID_SEARCH_ENABLED:
            docs = self._hybrid_search(rewritten, user_id, top_k)
        else:
            docs = self.vs.search(user_id, rewritten, top_k)

        # 自适应 MMR：候选不足 top_k×2 时无多样性优化空间
        if settings.MMR_ENABLED and len(docs) > top_k * 2:
            docs = self._mmr_diversify(docs, top_k)

        # 自适应 Rerank：候选不足阈值时跳过
        if settings.RE_RANKING_ENABLED and len(docs) > settings.RE_RANK_THRESHOLD:
            docs = await self._rerank(docs, query, top_k)

        return docs

    async def search_with_rag(self, user_id: str, query: str, top_k: int = 5) -> str:
        """执行完整检索 + RAG 生成（步骤 1-6）"""
        docs = await self.search(user_id, query, top_k)
        return await self._generate_rag(query, docs)

    async def search_in_file(self, user_id: str, query: str, filename: str, top_k: int = 5) -> list[dict]:
        """在指定文件中检索"""
        if settings.QUERY_REWRITING_ENABLED and self.vs.count(user_id) >= settings.QUERY_REWRITE_MIN_DOCS:
            rewritten = await self._rewrite_query(query)
        else:
            rewritten = query
        docs = self.vs.search(user_id, rewritten, top_k * settings.VECTOR_CANDIDATE_MULTIPLIER, where={"source": filename})
        if settings.MMR_ENABLED and len(docs) > top_k * 2:
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
