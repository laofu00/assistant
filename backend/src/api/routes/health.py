"""健康检查路由 — /health/live + /health/ready（K8s 探针分离）"""

import time

from fastapi import APIRouter

from src.core.config import settings
from src.core.schema import R

router = APIRouter(tags=["健康检查"])

_start_time = time.monotonic()


@router.get("/health/live")
async def health_live():
    """存活探针（仅检查进程存活）"""
    return {"status": "ok"}


@router.get("/health/ready")
async def health_ready():
    """就绪探针（检查外部依赖）"""
    components = {
        "chromadb": "healthy",
        "postgresql": "healthy",
        "llm": "healthy",
    }

    # 检查 ChromaDB
    try:
        from src.knowledge.vector_store import vector_store
        vector_store._client.heartbeat()
    except Exception:
        components["chromadb"] = "unhealthy"

    # 检查 PostgreSQL
    try:
        from src.core.database import engine
        async with engine.connect() as conn:
            await conn.execute(await conn.compile("SELECT 1"))  # type: ignore[arg-type]
    except Exception:
        components["postgresql"] = "unhealthy"

    # 检查 LLM
    if not settings.OPENAI_API_KEY:
        components["llm"] = "unconfigured"

    all_healthy = all(v == "healthy" or v == "unconfigured" for v in components.values())
    status = "ok" if all_healthy else "degraded"

    return {
        "status": status,
        "components": components,
        "version": settings.APP_VERSION,
        "uptime": round(time.monotonic() - _start_time, 1),
    }
