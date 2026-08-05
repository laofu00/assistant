"""知识库路由 — POST /upload, GET /files, DELETE /files, GET /retrieve, GET /files/{filename}/status"""

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from loguru import logger
from sqlalchemy import func, select, update

from src.core.auth_deps import is_admin_user
from src.core.config import settings
from src.core.database import async_session_factory
from src.core.llm_factory import set_trace_context
from src.core.schema import R
from src.knowledge.chunker import split_into_chunks
from src.knowledge.document_loader import load_document
from src.knowledge.retrieval import retrieval_pipeline
from src.knowledge.vector_store import vector_store
from src.models.knowledge_file import KnowledgeFile

router = APIRouter(prefix="/knowledge", tags=["知识库"])


def _get_user_id(request: Request) -> str:
    """从请求上下文获取已认证的用户ID（中间件已保证非 anonymous）"""
    return request.state.user_id


def _fmt_time(dt: datetime | None) -> str | None:
    """格式化时间字符串（PostgreSQL 已设为 Asia/Shanghai，naive datetime 直接格式化）"""
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%d %H:%M:%S")


@router.post("/upload")
async def upload_file(file: UploadFile = File(...), request: Request = None):  # type: ignore
    """上传文件到知识库"""
    user_id = _get_user_id(request) if request else "test"

    if not file.filename:
        raise HTTPException(400, "文件名为空")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in settings.allowed_extensions_list:
        raise HTTPException(400, f"不支持的文件格式: {ext}")

    upload_dir = settings.upload_dir
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    file_path = upload_dir / safe_name

    content = await file.read()

    # 设置 token 追踪上下文
    trace_id = uuid.uuid4().hex
    set_trace_context(trace_id=trace_id, user_id=user_id)

    # SHA256 去重 + 版本检测
    content_hash = hashlib.sha256(content).hexdigest()
    async with async_session_factory() as session:
        # 1. 内容完全相同 → 跳过
        result = await session.execute(
            select(KnowledgeFile).where(
                KnowledgeFile.user_id == user_id,
                KnowledgeFile.content_hash == content_hash,
                KnowledgeFile.active == 1,
                KnowledgeFile.status.in_(["COMPLETED", "PROCESSING"]),
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            msg = "文件已存在，无需重复上传" if existing.status == "COMPLETED" else "文件正在处理中"
            return R.ok({"id": existing.id, "filename": existing.file_name, "version": existing.version, "status": existing.status}, msg)

        # 2. 同名文件内容不同 → 版本升级
        result = await session.execute(
            select(KnowledgeFile).where(
                KnowledgeFile.user_id == user_id,
                KnowledgeFile.file_name == file.filename,
                KnowledgeFile.active == 1,
            ).order_by(KnowledgeFile.version.desc()).limit(1)
        )
        latest = result.scalar_one_or_none()
        new_version = (latest.version + 1) if latest else 1
        is_update = latest is not None

    file_path.write_bytes(content)

    try:
        async with async_session_factory() as session:
            kf = KnowledgeFile(
                user_id=user_id,
                file_name=file.filename,
                file_path=str(file_path),
                file_type=ext,
                content_hash=content_hash,
                version=new_version,
                active=1 if not is_update else 0,  # 新文件立即可见，版本更新等处理完成
                chunk_count=0,
                status="PENDING",
            )
            session.add(kf)
            await session.commit()
            await session.refresh(kf)
            file_id = kf.id

        import asyncio
        asyncio.create_task(_process_file_async(file_id, user_id, str(file_path), ext, file.filename, is_update))

        action = f"更新到 v{new_version}" if is_update else "上传成功"
        logger.info(f"文件{action}: {file.filename}, user={user_id}")
        return R.ok({"id": file_id, "filename": file.filename, "version": new_version, "is_update": is_update}, f"{action}，正在处理中")

    except Exception as e:
        logger.error(f"文件处理失败: {e}")
        raise HTTPException(500, f"文件处理失败: {e}")


async def _process_file_async(file_id: int, user_id: str, file_path: str, ext: str, filename: str, is_update: bool = False) -> None:
    """异步向量化处理：切片 → 向量化 → 写入 ChromaDB → 激活版本"""

    # 保险：异步任务中重新设置追踪上下文
    set_trace_context(trace_id=uuid.uuid4().hex, user_id=user_id)

    try:
        async with async_session_factory() as session:
            kf = await session.get(KnowledgeFile, file_id)
            if kf:
                kf.status = "PROCESSING"
                await session.commit()
            version = kf.version if kf else 1

        # 文档加载 + 切片 + 向量化
        text = await load_document(file_path, ext)
        chunk_results = split_into_chunks(text, settings.KNOWLEDGE_CHUNK_SIZE, settings.KNOWLEDGE_OVERLAP)
        now = datetime.now(UTC).replace(tzinfo=None)
        texts = [c["text"] for c in chunk_results]
        metadatas = [
            {
                "source": filename,
                "user_id": user_id,
                "file_id": str(file_id),
                "version": version,
                "active": 1,
                "upload_time": now.isoformat(),
                "chunk_index": i,
                "section": c.get("section", ""),
            }
            for i, c in enumerate(chunk_results)
        ]

        # 如果是版本更新：先软删除旧版本 chunks（不重新嵌入）
        if is_update:
            count = vector_store.deactivate_by_filename(user_id, filename)
            logger.info(f"旧版本 chunks 已软删除: {filename}, count={count}")

        await vector_store.add_documents(user_id, texts, metadatas)
        retrieval_pipeline.invalidate_bm25(user_id)

        # 更新状态，版本更新时激活新版本并标记旧版本 inactive
        async with async_session_factory() as session:
            kf = await session.get(KnowledgeFile, file_id)
            if kf:
                kf.status = "COMPLETED"
                if is_update:
                    kf.active = 1
                kf.chunk_count = len(chunk_results)
                kf.process_time = now
                await session.commit()

            # 标记旧版本 PG 记录为 inactive
            if is_update:
                await session.execute(
                    update(KnowledgeFile).where(
                        KnowledgeFile.user_id == user_id,
                        KnowledgeFile.file_name == filename,
                        KnowledgeFile.id != file_id,
                    ).values(active=0)
                )
                await session.commit()

        logger.info(f"异步向量化完成: {filename} v{version}, chunks={len(chunk_results)}")

    except Exception as e:
        logger.error(f"异步向量化失败: {filename}, error={e}")
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
    """列出知识库文件（支持分页）— 管理员查看全部用户"""
    user_id = _get_user_id(request)
    is_admin = await is_admin_user(user_id)
    async with async_session_factory() as session:
        conditions = [KnowledgeFile.active == 1]
        if not is_admin:
            conditions.append(KnowledgeFile.user_id == user_id)
        total_q = select(func.count(KnowledgeFile.id)).where(*conditions)
        total = (await session.execute(total_q)).scalar() or 0
        offset = (page - 1) * size
        q = select(KnowledgeFile).where(*conditions).order_by(KnowledgeFile.created_at.desc()).offset(offset).limit(size)
        result = await session.execute(q)
        files = result.scalars().all()
        records = [
            {
                "id": f.id,
                "fileName": f.file_name,
                "fileType": f.file_type,
                "version": f.version,
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
    is_admin = await is_admin_user(user_id)
    async with async_session_factory() as session:
        kf = await session.get(KnowledgeFile, file_id)
        if not kf:
            raise HTTPException(404, "文件不存在")
        if not is_admin and kf.user_id != user_id:
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
    """删除知识库文件所有版本（PG + ChromaDB + 物理文件）"""
    user_id = _get_user_id(request)
    is_admin = await is_admin_user(user_id)
    async with async_session_factory() as session:
        kf = await session.get(KnowledgeFile, file_id)
        if not kf:
            raise HTTPException(404, "文件不存在")
        if not is_admin and kf.user_id != user_id:
            raise HTTPException(404, "文件不存在")
        filename = kf.file_name

        # 删除该文件名下所有版本的 PG 记录
        result = await session.execute(
            select(KnowledgeFile).where(
                KnowledgeFile.user_id == user_id,
                KnowledgeFile.file_name == filename,
            )
        )
        all_records = result.scalars().all()
        for r in all_records:
            await session.delete(r)
        await session.commit()

    # 清理物理文件
    for r in all_records:
        if r.file_path:
            try:
                Path(r.file_path).unlink(missing_ok=True)
            except OSError:
                pass

    # 删除 ChromaDB 向量（所有版本）
    count = vector_store.delete_by_filename(user_id, filename)
    retrieval_pipeline.invalidate_bm25(user_id)

    logger.info(f"文件已删除（含 {len(all_records)} 个版本）: {filename}")
    return R.ok({"filename": filename, "deleted_chunks": count, "versions_removed": len(all_records)}, f"已删除 {count} 个片段")


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
