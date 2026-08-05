FROM python:3.13-slim

WORKDIR /app

# 系统依赖（国内服务器换阿里云镜像加速）
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    curl \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖（分层缓存：requirements.txt 变才重建，国内服务器换清华镜像加速）
COPY requirements.txt ./
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt && pip install -i https://pypi.tuna.tsinghua.edu.cn/simple uvicorn

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
