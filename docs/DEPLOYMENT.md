# 部署文档

---

## 目录

1. [本地开发（非 Docker）](#本地开发非-docker)
2. [云端部署（Docker Compose）](#云端部署docker-compose)

---

## 本地开发（非 Docker）

### 前置依赖

- Python 3.13+
- Node.js 18+
- PostgreSQL（本地或 Docker）
- Redis（本地或 Docker）

ChromaDB 使用嵌入式文件模式（`data/chroma_db/`），无需单独服务。

### 1. 启动 PostgreSQL & Redis（Docker 临时）

如果本地没有安装，用 Docker 跑：

```bash
docker run -d --name smart-pg \
  -e POSTGRES_DB=assistant -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 postgres:16-alpine

docker run -d --name smart-redis \
  -p 6379:6379 redis:7-alpine redis-server --requirepass smart123
```

### 2. 后端

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

pip install -e ".[dev]"

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY 等

# 数据库迁移
alembic upgrade head

# 启动（开发模式，热重载）
uvicorn src.api.main:app --reload --port 8000
```

### 3. 前端

```bash
cd frontend
npm install
npm run dev
```

访问 `http://localhost:5173`，API 自动代理到后端 `localhost:8000`。

---

## 云端部署（Docker Compose）

### 整体架构

```
浏览器 → Nginx:80 → 前端:80（静态文件）
                  → App:8000（API / SSE）
                       ↓
                  PostgreSQL / Redis / ChromaDB
```

### 1. 服务器初始化

```bash
# Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER

# Docker Compose
sudo apt install docker-compose-plugin -y

# Git
sudo apt install git -y
```

### 2. 克隆项目

```bash
git clone <repo-url> /opt/assistant
cd /opt/assistant
```

### 3. 配置环境变量

```bash
cp backend/.env.example backend/.env
vi backend/.env
```

需要在 `.env` 中配置的变量（`docker-compose.yml` 会读取此文件）：

| 变量 | 必填 | 说明 |
|------|------|------|
| `OPENAI_API_KEY` | 是 | DashScope API Key |
| `POSTGRES_PASSWORD` | 建议改 | 数据库密码 |
| `JWT_SECRET` | 建议改 | JWT 签名密钥 |
| `NGINX_PORT` | 否 | 外部访问端口，默认 80 |
| `CHROMA_URL` | 否 | 留空即可，`docker-compose.yml` 已设置默认值 `http://chromadb:8000` |

### 4. 启动服务

```bash
# 构建并启动
docker compose up -d --build

# 数据库首次迁移（必须）
docker compose --profile init run --rm alembic

# 查看所有服务状态
docker compose ps
```

全部 7 个服务：

| 容器 | 说明 |
|------|------|
| `smart-nginx` | 反向代理，统一入口 |
| `smart-frontend` | Vue 3 前端静态文件 |
| `smart-app` | FastAPI 后端 |
| `smart-postgres` | PostgreSQL 16 |
| `smart-redis` | Redis 7 |
| `smart-chromadb` | ChromaDB 向量存储 |
| `smart-langfuse` | 链路追踪（可选） |

### 5. 验证

```bash
# 本地验证
curl http://localhost/health/live
# → {"status":"ok"}
```

### 6. 防火墙 & 安全组

**云服务器控制台**：添加入站规则，开放端口（.env 中 `NGINX_PORT` 对应的端口，默认 80）。

**系统防火墙**（如有）：

```bash
sudo ufw allow 80/tcp
sudo ufw allow 22/tcp
sudo ufw enable
```

### 7. 开机自启

```bash
sudo tee /etc/systemd/system/smart-assistant.service << 'EOF'
[Unit]
Description=Smart Assistant
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/assistant
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable smart-assistant
```

---

## 更新部署

```bash
cd /opt/assistant
git pull
docker compose up -d --build
```

如果只改了前端：

```bash
git pull
docker compose up -d --build frontend nginx
```

---

## 数据库迁移

```bash
# 执行迁移（首次初始化或更新后）
docker compose --profile init run --rm alembic

# 生成新迁移（在容器内）
docker compose run --rm app alembic revision --autogenerate -m "描述"
```

### 备份

```bash
# PostgreSQL
docker compose exec postgres pg_dump -U postgres assistant > backup.sql

# 恢复
docker compose exec -T postgres psql -U postgres assistant < backup.sql
```

---

## 健康检查端点

| 端点 | 用途 |
|------|------|
| `/health/live` | 存活探针 |
| `/health/ready` | 就绪探针（含各组件状态） |
| `/metrics` | Prometheus 指标 |

---

## 常见问题

### 1. 服务一直 restarting 不 healthy

```bash
# 看具体日志
docker logs smart-chromadb --tail 20
docker logs smart-langfuse --tail 20
docker logs smart-frontend --tail 20

# 排查依赖链：postgres/redis 必须 healthy → chromadb healthy → app 才能启动
docker compose ps
```

### 2. 端口冲突

修改 `.env` 中 `NGINX_PORT`：

```
NGINX_PORT=8080
```

### 3. 内存不足

`.env` 中调整限制：

```
APP_MEMORY_LIMIT=512M
PG_MEMORY_LIMIT=256M
CHROMA_MEMORY_LIMIT=256M
```

### 4. 前端访问不了

- 云服务器安全组是否开放了对应端口
- `docker logs smart-frontend` 看 nginx 是否正常运行
- 在服务器本地 `curl http://localhost/` 测试

### 5. 完全重置

```bash
docker compose down -v    # 删除所有数据卷
docker compose up -d --build
docker compose --profile init run --rm alembic
```
