"""长期记忆管理 — ChromaDB 语义存储 + PostgreSQL 用户画像

生命周期:
  会话结束 → 萃取跨会话事实 → 写入 ChromaDB + PG
  会话开始 → 检索相关长期记忆 → 注入 LLM context
"""

import json
import re
import time

from loguru import logger

from src.core.config import settings
from src.core.metrics import memory_summary_duration_seconds, memory_summary_total

# ChromaDB collection 前缀
_LTM_COLLECTION_PREFIX = "long_term_memory"

# 萃取 prompt
_EXTRACTION_PROMPT = """你是一个用户信息提取助手。从对话历史中提取可跨会话复用的长期信息。

输出 JSON 对象（不是数组），包含：
{
  "preferences": {"回复风格": "简洁", "输出格式": "Markdown", ...},
  "key_facts": [{"fact": "事实内容", "type": "identity|preference|decision|reminder", "importance": "high|medium"}, ...]
}

提取规则：
- identity: 姓名、邮箱、角色、公司、位置等身份信息
- preference: "以后都...""总是...""不喜欢..." 等偏好表达，合并已有偏好
- decision: 重要决策结果、确认的约定
- reminder: 需要提醒的事项

只输出 JSON，不要加任何前缀。如果没有可提取的信息，输出 {"preferences": {}, "key_facts": []}。

对话历史：
"""


class LongTermMemory:
    """长期记忆管理器"""

    # ==================== 萃取 ====================

    async def extract_and_save(
        self, user_id: str, session_id: str, messages: list[dict], summary_facts: list[dict]
    ) -> dict:
        """会话结束：LLM 萃取跨会话事实 → 写入 ChromaDB + PG

        Returns:
            {"preferences": {...}, "key_facts": [...]}
        """
        if not messages and not summary_facts:
            return {"preferences": {}, "key_facts": []}

        start = time.monotonic()

        try:
            extracted = await self._extract(user_id, messages, summary_facts)
            if not extracted or not extracted.get("key_facts"):
                return {"preferences": {}, "key_facts": []}

            # 写 ChromaDB（语义检索）
            facts = extracted.get("key_facts", [])
            await self._save_to_chromadb(user_id, session_id, facts)

            # 写 PG（结构化存储）
            preferences = extracted.get("preferences", {})
            await self._save_profile(user_id, preferences, facts)

            elapsed = time.monotonic() - start
            memory_summary_total.inc()
            memory_summary_duration_seconds.observe(elapsed)
            logger.info(
                f"[长期记忆] 萃取: user={user_id}, session={session_id}, "
                f"facts={len(facts)}, prefs={len(preferences)}, elapsed={elapsed:.2f}s"
            )

            return extracted
        except Exception as e:
            logger.warning(f"[长期记忆] 萃取失败: {e}")
            return {"preferences": {}, "key_facts": []}

    async def _extract(self, user_id: str, messages: list[dict], summary_facts: list[dict]) -> dict | None:
        """LLM 萃取长期信息"""
        try:
            from src.core.llm_factory import get_llm

            # 拼接对话内容
            history = ""
            if summary_facts:
                history += "历史操作摘要:\n"
                for f in summary_facts[:10]:
                    history += f"  [{f.get('action', '?')}] {f.get('entity', '?')}: {f.get('detail', '')}\n"
            for m in messages[-6:]:
                history += f"{m.get('role', '?')}: {str(m.get('content', ''))[:200]}\n"

            llm = get_llm(temperature=0, streaming=False, model=settings.MODEL_NAME_LIGHT)
            response = await llm.ainvoke(_EXTRACTION_PROMPT + history)
            text = str(response.content) if response.content else ""

            json_match = re.search(r"\{[\s\S]*\}", text)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.warning(f"[长期记忆] LLM 萃取失败: {e}")

        return None

    # ==================== ChromaDB 存储 ====================

    async def _save_to_chromadb(self, user_id: str, session_id: str, facts: list[dict]) -> None:
        """写入 ChromaDB（按 user_id 分 collection）"""
        from src.knowledge.vector_store import vector_store

        collection_name = f"{_LTM_COLLECTION_PREFIX}_{user_id}"
        now = time.strftime("%Y-%m-%d %H:%M:%S")

        texts = []
        metadatas = []
        ids = []

        for i, fact in enumerate(facts):
            texts.append(fact.get("fact", ""))
            metadatas.append({
                "user_id": user_id,
                "session_id": session_id,
                "type": fact.get("type", "unknown"),
                "importance": fact.get("importance", "medium"),
                "created_at": now,
            })
            ids.append(f"{user_id}_{session_id}_{i}_{int(time.time())}")

        collection = vector_store._client.get_or_create_collection(
            name=collection_name,
            embedding_function=vector_store._ef,
        )
        collection.add(documents=texts, metadatas=metadatas, ids=ids)

    # ==================== 检索 ====================

    async def retrieve(self, user_id: str, current_message: str, top_k: int = 5) -> list[dict]:
        """会话开始：从 ChromaDB 检索相关长期记忆"""
        try:
            from src.knowledge.vector_store import vector_store

            collection_name = f"{_LTM_COLLECTION_PREFIX}_{user_id}"
            try:
                collection = vector_store._client.get_collection(collection_name)
            except Exception:
                return []

            results = collection.query(query_texts=[current_message], n_results=top_k)
            if not results["documents"] or not results["documents"][0]:
                return []

            docs = results["documents"][0]
            metas = results["metadatas"][0] if results["metadatas"] else [{}] * len(docs)

            facts = []
            for doc, meta in zip(docs, metas, strict=False):
                facts.append({
                    "fact": doc,
                    "type": meta.get("type", "unknown"),
                    "importance": meta.get("importance", "medium"),
                })

            logger.debug(f"[长期记忆] 检索: user={user_id}, query={current_message[:50]}, results={len(facts)}")
            return facts
        except Exception as e:
            logger.warning(f"[长期记忆] 检索失败: {e}")
            return []

    async def list_all(self, user_id: str) -> dict:
        """列出用户的所有长期记忆（管理页面用）"""
        from src.knowledge.vector_store import vector_store

        if user_id is None:
            # 管理员视角：列出所有用户的长期记忆
            return await self._list_all_users(vector_store)

        collection_name = f"{_LTM_COLLECTION_PREFIX}_{user_id}"
        try:
            collection = vector_store._client.get_collection(collection_name)
        except Exception:
            return {"profile": {}, "facts": [], "fact_count": 0}

        results = collection.get(include=["documents", "metadatas"])
        facts = []
        for doc, meta in zip(results.get("documents", []), results.get("metadatas", []), strict=False):
            facts.append({
                "fact": doc,
                "type": meta.get("type", "unknown"),
                "importance": meta.get("importance", "medium"),
                "session_id": meta.get("session_id", ""),
                "created_at": meta.get("created_at", ""),
            })

        profile = await self._get_profile(user_id)
        return {
            "profile": profile,
            "facts": sorted(facts, key=lambda f: (
                -{"high": 3, "medium": 2, "low": 1}.get(f.get("importance", "medium"), 1)
            )),
            "fact_count": len(facts),
        }

    async def _list_all_users(self, vector_store) -> dict:
        """管理员视角：汇总所有用户的长期记忆"""
        all_facts = []
        try:
            collections = vector_store._client.list_collections()
        except Exception:
            return {"profile": {}, "facts": [], "fact_count": 0}

        for col in collections:
            col_name = col if isinstance(col, str) else col.name
            if not col_name.startswith(f"{_LTM_COLLECTION_PREFIX}_"):
                continue
            user_id = col_name[len(f"{_LTM_COLLECTION_PREFIX}_"):]
            try:
                collection = vector_store._client.get_collection(col_name)
                results = collection.get(include=["documents", "metadatas"])
                for doc, meta in zip(results.get("documents", []), results.get("metadatas", []), strict=False):
                    all_facts.append({
                        "user_id": user_id,
                        "fact": doc,
                        "type": meta.get("type", "unknown"),
                        "importance": meta.get("importance", "medium"),
                        "session_id": meta.get("session_id", ""),
                        "created_at": meta.get("created_at", ""),
                    })
            except Exception as e:
                logger.warning(f"[长期记忆] 读取集合 {col_name} 失败: {e}")

        return {
            "profile": {},
            "facts": sorted(all_facts, key=lambda f: (
                -{"high": 3, "medium": 2, "low": 1}.get(f.get("importance", "medium"), 1)
            )),
            "fact_count": len(all_facts),
            "all_users": True,
        }

    async def delete_fact(self, user_id: str, fact_text: str) -> bool:
        """删除单条长期记忆"""
        from src.knowledge.vector_store import vector_store

        collection_name = f"{_LTM_COLLECTION_PREFIX}_{user_id}"
        try:
            collection = vector_store._client.get_collection(collection_name)
            results = collection.get(where={"user_id": user_id}, include=["documents"])
            ids_to_delete = []
            for doc_id, doc in zip(results.get("ids", []), results.get("documents", []), strict=False):
                if doc == fact_text:
                    ids_to_delete.append(doc_id)
            if ids_to_delete:
                collection.delete(ids=ids_to_delete)
            return True
        except Exception as e:
            logger.warning(f"[长期记忆] 删除失败: {e}")
            return False

    # ==================== PostgreSQL 画像 ====================

    async def _save_profile(self, user_id: str, preferences: dict, facts: list[dict]) -> None:
        """写入/更新用户画像"""
        from sqlalchemy import select

        from src.core.database import async_session_factory
        from src.models.user_profile import UserProfile

        async with async_session_factory() as session:
            result = await session.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
            profile = result.scalar_one_or_none()

            if profile:
                # 合并偏好
                existing_prefs = dict(profile.preferences or {})
                existing_prefs.update(preferences)
                profile.preferences = existing_prefs

                # 合并关键事实（去重）
                existing_facts = dict(profile.key_facts or {})
                for f in facts:
                    if f.get("importance") == "high":
                        existing_facts[f.get("type", "unknown")] = f.get("fact", "")
                profile.key_facts = existing_facts
            else:
                key_facts = {}
                for f in facts:
                    if f.get("importance") == "high":
                        key_facts[f.get("type", "unknown")] = f.get("fact", "")
                profile = UserProfile(
                    user_id=user_id,
                    preferences=preferences,
                    key_facts=key_facts,
                )
                session.add(profile)

            await session.commit()

    async def _get_profile(self, user_id: str) -> dict:
        """读取用户画像"""
        from sqlalchemy import select

        from src.core.database import async_session_factory
        from src.models.user_profile import UserProfile

        async with async_session_factory() as session:
            result = await session.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
            profile = result.scalar_one_or_none()
            if profile:
                return {
                    "preferences": profile.preferences or {},
                    "key_facts": profile.key_facts or {},
                }
            return {}

    async def update_preferences(self, user_id: str, preferences: dict) -> None:
        """手动更新用户偏好（管理 API 用）"""
        from sqlalchemy import select

        from src.core.database import async_session_factory
        from src.models.user_profile import UserProfile

        async with async_session_factory() as session:
            result = await session.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
            profile = result.scalar_one_or_none()
            if profile:
                profile.preferences = preferences
            else:
                profile = UserProfile(user_id=user_id, preferences=preferences)
                session.add(profile)
            await session.commit()


# 全局实例
long_term_memory = LongTermMemory()
