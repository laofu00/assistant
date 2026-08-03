# 部署文档

---

## 目录

1. [项目结构](#项目结构)
2. [本地开发环境](#本地开发环境)
3. [Docker Compose 部署](#docker-compose-部署)
4. [云服务器部署](#云服务器部署)
5. [HTTPS / SSL 配置](#https--ssl-配置)
6. [数据库迁移](#数据库迁移)
7. [健康检查 & 监控](#健康检查--监控)
8. [常见问题](#常见问题)

---

## 项目结构

```
assistant/
├── docker-compose.yml        # 服务编排
├── .env.docker               # Docker 环境变量模板
├── nginx/
│   └── default.conf          # Nginx 反向代理配置
├── backend/                  # Python 后端
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── .env                  # 后端环境变量
│   ├── src/
│   ├── alembic/              # 数据库迁移
│   └── data/                 # 运行时数据（volume 挂载）
├── frontend/                 # Vue 3 前端
│   ├── Dockerfile
│   ├── nginx.conf
│   └── src/
└── docs/
    └── DEPLOYMENT.md
```

### 服务架构

```
                    ┌──────────────┐
                    │   Nginx:80   │  反向代理（统一入口）
                    └──────┬───────┘
                           │
            ┌──────────────┼──────────────┐
            │              │              │
       ┌────▼────┐   ┌────▼────┐   ┌────▼────┐
       │ Frontend│   │   App   │   │  Docs   │
       │  :80    │   │  :8000  │   │  :8000  │
       └─────────┘   └────┬────┘   └─────────┘
                          │
          ┌───────────────┼───────────────┐
          │               │               │
     ┌────▼────┐    ┌────▼────┐    ┌─────▼─────┐
     │Postgres │    │  Redis  │    │ ChromaDB  │
     │  :5432  │    │  :6379  │    │   :8000   │
     └─────────┘    └─────────┘    └───────────┘
```

---

## 本地开发环境

### 前置依赖

本地需要 PostgreSQL 和 Redis。用 Docker 一键启动：

```bash
# 启动 PostgreSQL
docker run -d --name smart-pg \
  -e POSTGRES_DB=assistant -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 postgres:16-alpine

# 启动 Redis
docker run -d --name smart-redis \
  -p 6379:6379 redis:7-alpine
```

ChromaDB 使用本地文件模式（`data/chroma_db/`），无需单独启动服务。

### 后端

```bash
cd backend

# === 方式一：pyproject.toml（开发推荐） ===
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

pip install -e ".[dev]"

# === 方式二：requirements.txt（最小依赖） ===
pip install -r requirements.txt

# === 配置环境变量 ===
cp .env.example .env
# 编辑 .env，至少填入 OPENAI_API_KEY

# === 数据库迁移 ===
alembic upgrade head

# === 导入示例数据（可选） ===
python scripts/seed_data.py

# === 启动服务 ===
uvicorn src.api.main:app --reload --port 8000
```

### 前端

```bash
cd frontend

npm install
npm run dev
```

访问 http://localhost:5173，API 请求自动代理到后端。

> 开发环境下前端 `.env.test` 中 `VITE_API_BASE_URL` 指向 `http://localhost:8000/api/v1`。

---

## Docker Compose 部署

### 1. 准备环境变量

```bash
# 从模板创建
cp .env.docker.example .env

# 编辑 .env，修改以下必填项：
# - OPENAI_API_KEY：你的 API Key
# - POSTGRES_PASSWORD：数据库密码（不要用默认值）
```

### 2. 构建并启动

```bash
# 启动所有服务
docker compose up -d

# 查看启动状态
docker compose ps

# 查看日志
docker compose logs -f app
```

### 3. 首次初始化

```bash
# 数据库迁移
docker compose run --rm alembic

# 导入示例数据
docker compose run --rm seed
```

### 4. 验证

```bash
# 健康检查
curl http://localhost/health/live
# → {"status":"ok"}

curl http://localhost/health/ready
# → {"status":"ok","components":{"chromadb":"healthy",...}}

# 前端页面
curl http://localhost/
# → HTML 页面

# API 文档
open http://localhost/docs
```

### 常用命令

```bash
# 重启单个服务
docker compose restart app

# 更新镜像并重新部署
docker compose pull
docker compose up -d --remove-orphans

# 查看资源占用
docker stats smart-app smart-postgres smart-redis smart-chromadb

# 进入容器
docker compose exec app bash
docker compose exec postgres psql -U postgres -d assistant

# 停止并清理
docker compose down
docker compose down -v  # 同时删除数据卷（危险）
```

---

## 云服务器部署

以 Ubuntu 22.04 为例。

### 1. 服务器初始化

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER

# 安装 Docker Compose
sudo apt install docker-compose-plugin -y

# 安装 git
sudo apt install git -y
```

### 2. 克隆项目

```bash
git clone <your-repo-url> /opt/smart-assistant
cd /opt/smart-assistant
```

### 3. 配置环境变量

```bash
cp .env.docker.example .env
vi .env
```

必填项：
```
OPENAI_API_KEY=sk-your-api-key
POSTGRES_PASSWORD=<强密码>
ENVIRONMENT=production
LOG_LEVEL=WARNING
```

### 4. 启动服务

```bash
docker compose up -d
docker compose run --rm alembic
```

### 5. 配置防火墙

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 22/tcp
sudo ufw enable
```

### 6. 配置 systemd 自启

```bash
sudo tee /etc/systemd/system/smart-assistant.service << 'EOF'
[Unit]
Description=Smart Assistant
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/smart-assistant
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable smart-assistant
sudo systemctl start smart-assistant
```

---

## HTTPS / SSL 配置

### 方案 A：Let's Encrypt（推荐，免费）

```bash
# 安装 certbot
sudo apt install certbot python3-certbot-nginx -y

# 获取证书
sudo certbot --nginx -d your-domain.com

# 自动续期
sudo certbot renew --dry-run
```

获取证书后，编辑 `nginx/default.conf`，取消 HTTPS server 块注释，填入证书路径。

### 方案 B：Cloudflare SSL

1. DNS 接入 Cloudflare
2. SSL/TLS 模式设为 "Full (strict)"
3. Cloudflare → Nginx:80（HTTP），用户 → Cloudflare（HTTPS）

### 方案 C：自签名证书（内网测试）

```bash
mkdir -p nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/privkey.pem \
  -out nginx/ssl/fullchain.pem \
  -subj "/CN=localhost"
```

---

## 数据库迁移

### 开发环境

```bash
cd backend
alembic upgrade head       # 升级到最新
alembic downgrade -1       # 回滚一个版本
alembic revision --autogenerate -m "描述"  # 生成新迁移
```

### Docker 环境

```bash
# 执行迁移
docker compose run --rm alembic

# 生成新迁移（需进入容器）
docker compose run --rm app alembic revision --autogenerate -m "add_new_table"
```

### 备份 & 恢复

```bash
# 备份 PostgreSQL
docker compose exec postgres pg_dump -U postgres assistant > backup.sql

# 恢复
docker compose exec -T postgres psql -U postgres assistant < backup.sql

# 备份 ChromaDB
docker compose exec app python scripts/backup_chroma.py

# 备份文件在 backend/data/chroma_db/backups/
```

---

## 健康检查 & 监控

### 端点

| 端点 | 用途 | 间隔建议 |
|------|------|---------|
| `/health/live` | K8s livenessProbe | 30s |
| `/health/ready` | K8s readinessProbe | 10s |
| `/metrics` | Prometheus 采集 | 15s |

### Prometheus 配置

```yaml
scrape_configs:
  - job_name: smart-assistant
    metrics_path: /metrics
    static_configs:
      - targets: ['your-server:80']
```

### 日志

```bash
# 查看应用日志
docker compose logs -f app

# 查看 Nginx 访问日志
docker compose logs -f nginx

# 日志文件位置
ls backend/logs/app.log  # JSON 格式，每天轮转，保留 30 天
```

### 告警规则（Prometheus）

```yaml
groups:
  - name: smart-assistant
    rules:
      - alert: ServiceDown
        expr: up{job="smart-assistant"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Smart Assistant is down"

      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        labels:
          severity: warning

      - alert: TokenQuotaWarning
        expr: smart_token_usage_ratio > 0.8
        for: 1m
        labels:
          severity: warning
```

---

## 常见问题

### 1. "Connection refused" 连接数据库

```bash
# 确认 PostgreSQL 已启动
docker compose ps postgres
# 等待健康检查通过
docker compose logs postgres | grep "ready to accept connections"
```

### 2. ChromaDB 健康检查失败

ChromaDB 启动较慢（特别是首次初始化），等待 1-2 分钟后重试：
```bash
docker compose restart chromadb
```

### 3. 前端页面白屏

检查浏览器控制台，确认 API 请求路径正确：
```bash
# 确认 Nginx 配置正确
docker compose exec nginx nginx -t
docker compose exec nginx nginx -s reload
```

### 4. 端口冲突

修改 `.env` 中的端口映射：
```
NGINX_PORT=8080
```
或在 `docker-compose.yml` 中直接改 `ports`。

### 5. 内存不足

减少服务内存限制（`.env`）：
```
APP_MEMORY_LIMIT=512M
PG_MEMORY_LIMIT=256M
```

只启动核心服务：
```bash
docker compose up -d nginx app postgres redis
```

### 6. 数据清理

```bash
# Token 记录和审计日志定期清理
docker compose exec app python scripts/cleanup.py

# 添加 cron 定时任务
crontab -e
# 每天凌晨 3 点清理
0 3 * * * cd /opt/smart-assistant && docker compose exec -T app python scripts/cleanup.py
```

---

## 部署检查清单

- [ ] `.env` 中 `OPENAI_API_KEY` 已填写
- [ ] `.env` 中 `POSTGRES_PASSWORD` 已修改为非默认值
- [ ] `docker compose up -d` 所有服务 healthy
- [ ] `docker compose run --rm alembic` 迁移成功
- [ ] `curl http://localhost/health/ready` 返回 ok
- [ ] `curl http://localhost/api/v1/tools` 返回工具列表
- [ ] 前端页面可正常访问
- [ ] 防火墙 80/443 端口已开放
- [ ] SSL 证书已配置（生产环境）
- [ ] systemd 自启已配置
- [ ] 数据库备份策略已配置
- [ ] 日志轮转已验证
