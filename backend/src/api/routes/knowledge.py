"""知识库路由 — POST /upload, GET /files, DELETE /files, GET /retrieve, GET /files/{filename}/status"""

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from loguru import logger
from sqlalchemy import func, select

from src.core.config import settings
from src.core.database import async_session_factory
from src.core.schema import R
from src.models.knowledge_file import KnowledgeFile
from src.knowledge.chunker import split_into_chunks
from src.knowledge.document_loader import load_document
from src.knowledge.retrieval import retrieval_pipeline
from src.knowledge.vector_store import vector_store

router = APIRouter(prefix="/knowledge", tags=["知识库"])

_CST = timezone(timedelta(hours=8))


def _get_user_id(request: Request) -> str:
    """从请求上下文获取已认证的用户ID（中间件已保证非 anonymous）"""
    return request.state.user_id


def _fmt_time(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_CST).strftime("%Y-%m-%d %H:%M:%S")


@router.post("/upload")
async def upload_file(file: UploadFile = File(...), request: Request = None):  # type: ignore
    """上传文件到知识库"""
    user_id = _get_user_id(request) if request else "test"

    if not file.filename:
        raise HTTPException(400, "文件名为空")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in settings.allowed_extensions_list:
        raise HTTPException(400, f"不支持的文件格式: {ext}")

    upload_dir = Path("data/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    file_path = upload_dir / safe_name

    content = await file.read()
    file_path.write_bytes(content)

    try:
        # 创建文件记录，状态为 PENDING（对齐 Java：异步向量化）
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        async with async_session_factory() as session:
            kf = KnowledgeFile(
                user_id=user_id,
                file_name=file.filename,
                file_path=str(file_path),
                file_type=ext,
                chunk_count=0,
                status="PENDING",
            )
            session.add(kf)
            await session.commit()
            await session.refresh(kf)
            file_id = kf.id

        # 异步向量化处理（不阻塞上传响应）
        import asyncio
        asyncio.create_task(_process_file_async(file_id, user_id, str(file_path), ext, file.filename))

        logger.info(f"文件上传成功: {file.filename}, user={user_id}, 已触发异步向量化")
        return R.ok({"id": file_id, "filename": file.filename}, "上传成功，正在处理中")

    except Exception as e:
        logger.error(f"文件处理失败: {e}")
        raise HTTPException(500, f"文件处理失败: {e}")


async def _process_file_async(file_id: int, user_id: str, file_path: str, ext: str, filename: str) -> None:
    """异步向量化处理：切片 → 向量化 → 写入 ChromaDB → 更新状态"""
    from src.knowledge.chunker import split_into_chunks
    from src.knowledge.document_loader import load_document

    try:
        # 更新状态为 PROCESSING
        async with async_session_factory() as session:
            kf = await session.get(KnowledgeFile, file_id)
            if kf:
                kf.status = "PROCESSING"
                await session.commit()

        # 文档加载 + 切片 + 向量化
        text = await load_document(file_path, ext)
        chunks = split_into_chunks(text, settings.KNOWLEDGE_CHUNK_SIZE, settings.KNOWLEDGE_OVERLAP)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        metadatas = [{"source": filename, "user_id": user_id, "file_id": str(file_id), "upload_time": now.isoformat(), "chunk_index": i} for i in range(len(chunks))]
        vector_store.add_documents(user_id, chunks, metadatas)

        # 更新状态为 COMPLETED + 记录分块数
        async with async_session_factory() as session:
            kf = await session.get(KnowledgeFile, file_id)
            if kf:
                kf.status = "COMPLETED"
                kf.chunk_count = len(chunks)
                kf.process_time = now
                await session.commit()

        logger.info(f"异步向量化完成: {filename}, chunks={len(chunks)}")

    except Exception as e:
        logger.error(f"异步向量化失败: {filename}, error={e}")
        # 更新状态为 FAILED
        try:
            async with async_session_factory() as session:
                kf = await session.get(KnowledgeFile, file_id)
                if kf:
                    kf.status = "FAILED"
                    kf.error_message = str(e)[:500]
                    await session.commit()
        except Exception:
            pass


@router.get("/files")
async def list_files(
    request: Request,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=100, ge=1, le=1000),
):
    """列出知识库文件（支持分页）"""
    user_id = _get_user_id(request)
    async with async_session_factory() as session:
        total_q = select(func.count(KnowledgeFile.id)).where(KnowledgeFile.user_id == user_id)
        total = (await session.execute(total_q)).scalar() or 0
        offset = (page - 1) * size
        q = select(KnowledgeFile).where(KnowledgeFile.user_id == user_id).order_by(KnowledgeFile.created_at.desc()).offset(offset).limit(size)
        result = await session.execute(q)
        files = result.scalars().all()
        records = [
            {
                "id": f.id,
                "fileName": f.file_name,
                "fileType": f.file_type,
                "chunkCount": f.chunk_count,
                "status": f.status,
                "createTime": _fmt_time(f.created_at),
            }
            for f in files
        ]
    return R.ok({"records": records, "total": total, "page": page, "size": size})


@router.get("/files/{file_id:int}/status")
async def get_file_status(file_id: int, request: Request):
    """获取单个文件处理状态（前端轮询用）"""
    user_id = _get_user_id(request)
    async with async_session_factory() as session:
        kf = await session.get(KnowledgeFile, file_id)
        if not kf or kf.user_id != user_id:
            raise HTTPException(404, "文件不存在")
        return R.ok({
            "id": kf.id,
            "filename": kf.file_name,
            "fileType": kf.file_type,
            "chunkCount": kf.chunk_count,
            "status": kf.status,
            "errorMessage": kf.error_message,
        })


@router.delete("/files/{file_id:int}")
async def delete_file(file_id: int, request: Request):
    """删除知识库文件"""
    user_id = _get_user_id(request)
    async with async_session_factory() as session:
        result = await session.execute(
            select(KnowledgeFile).where(KnowledgeFile.id == file_id, KnowledgeFile.user_id == user_id)
        )
        kf = result.scalar_one_or_none()
        if not kf:
            raise HTTPException(404, "文件不存在")
        filename = kf.file_name
        await session.delete(kf)
        await session.commit()
    # 删除 ChromaDB 向量（按 file_id，避免同名文件误删）
    count = vector_store.delete_by_file_id(user_id, file_id)
    return R.ok({"filename": filename, "deleted_chunks": count}, f"已删除 {count} 个片段")


@router.get("/retrieve")
async def retrieve_knowledge(
    query: str = Query(default=""),
    request: Request = None,  # type: ignore
    top_k: int = Query(default=5, ge=1, le=20),
):
    """检索知识库并 RAG 生成答案"""
    if not query.strip():
        return R.ok([], "查询为空")
    user_id = _get_user_id(request) if request else "test"
    try:
        result = await retrieval_pipeline.search_with_rag(user_id, query, top_k)
        return R.ok({"answer": result, "query": query, "top_k": top_k})
    except Exception as e:
        logger.error(f"检索失败: {e}")
        raise HTTPException(500, f"检索失败: {e}")
