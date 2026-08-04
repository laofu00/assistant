FROM python:3.13-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖（分层缓存：requirements.txt 变才重建）
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && pip install uvicorn

# 复制源码
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini ./
COPY scripts/ scripts/
COPY data/ data/

# 运行时目录
RUN mkdir -p logs data/uploads data/dead_letter

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
