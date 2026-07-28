# Smart Assistant Python 重构 — 企业级开发计划 v4

**源项目**：`D:\LocalWork\java\smart-assistant`（Spring Cloud 微服务）
**目标项目**：`D:\LocalWork\Python\assistant`（LangGraph + FastAPI 单体）
**重构标准**：功能完整对齐 Java 版 + 企业级工程标准
**计划日期**：2026-07-27

> **关于前端**：复用 Java 版 Vue 3 前端项目（`frontend/` 目录），直接复制到本项目根目录下，修改 `VITE_API_BASE_URL` 指向 Python 后端即可，不做重复开发。Docker Compose 中通过 Nginx 统一代理前端 + 后端。

---

## 项目目录总览

```
D:\LocalWork\Python\assistant/
├── docker-compose.yml              # 编排：backend + chromadb + postgres + redis + nginx
├── .gitignore                      # 项目级忽略规则
├── README.md
├── DEVELOPMENT_PLAN.md
├── PROGRESS.md
├── backend/                        # Python 后端（FastAPI + LangGraph）
│   ├── pyproject.toml              # 项目元数据 + 依赖
│   ├── .env / .env.example
│   ├── Dockerfile
│   ├── alembic/                    # 数据库迁移
│   │   ├── alembic.ini
│   │   ├── env.py
│   │   └── versions/
│   ├── src/
│   │   ├── __init__.py
│   │   ├── core/                   # 基础设施（12 文件）
│   │   │   ├── config.py           # 60+ 配置项
│   │   │   ├── database.py         # SQLAlchemy async engine
│   │   │   ├── middleware.py        # 请求上下文 + JWT/Redis 认证
│   │   │   ├── password_utils.py   # bcrypt
│   │   │   ├── jwt_utils.py        # JWT 生成/解析
│   │   │   ├── auth_deps.py        # 认证依赖
│   │   │   ├── redis_client.py     # Redis 连接
│   │   │   └── ...
│   │   ├── models/                 # ORM 模型（10 表）
│   │   │   ├── user.py             # user_info
│   │   │   ├── user_preference.py  # user_preference
│   │   │   ├── user_token.py       # user_token
│   │   │   ├── memo.py             # memo
│   │   │   ├── knowledge_file.py   # knowledge_file
│   │   │   ├── token_usage.py      # ai_token_usage
│   │   │   ├── tool_audit.py       # tool_audit_log
│   │   │   ├── operation_log.py    # operation_log
│   │   │   ├── user_notification.py # user_notification
│   │   │   └── state.py            # AgentState
│   │   ├── tools/                  # 工具函数（7 文件）
│   │   ├── knowledge/              # 知识库（4 文件）
│   │   ├── agents/                 # 智能体（3 文件，ChatTongyi）
│   │   ├── workflows/              # LangGraph 图（3 文件）
│   │   ├── token/                  # Token 计费（6 文件）
│   │   └── api/                    # FastAPI 接口（10 文件）
│   │       └── routes/
│   │           ├── auth.py         # 认证（注册/登录/改密/刷新）
│   │           ├── user.py         # 用户偏好
│   │           ├── chat.py         # SSE 对话
│   │           ├── knowledge.py    # 文件上传+异步向量化
│   │           ├── memo.py         # CRUD
│   │           ├── token.py        # 统计
│   │           ├── tools.py        # 工具管理
│   │           ├── admin.py        # 管理端点
│   │           └── health.py       # 健康检查
│   ├── data/
│   ├── tests/
│   ├── scripts/
│   └── logs/
├── frontend/                       # Vue 3 前端
├── .env.docker                     # Docker 部署配置
└── docs/                           # 项目文档
```

**文件总计**：`src/` 44 + `tests/` 10 + `scripts/` 4 + `config/工程` 8 + `alembic/` 4 + `CI` 1 + `docs/` 4 = **75**

---

## 第一阶段：项目骨架与基础配置（13 文件）

### 目标
搭建完整 Python 项目骨架 + 工程化配置。

### 涉及文件

| # | 文件 | 说明 |
|---|------|------|
| 1 | `pyproject.toml` | 项目元数据 + 依赖 + mypy/ruff/pytest 配置 |
| 2 | `.python-version` | `3.12` |
| 3 | `.env` | 环境变量 |
| 4 | `.env.example` | 环境变量模板 |
| 5 | `.gitignore` | 忽略规则 |
| 6 | `.pre-commit-config.yaml` | pre-commit hooks（ruff format + ruff check + mypy） |
| 7 | `src/__init__.py` | 包初始化 |
| 8 | `src/core/config.py` | Settings 类（~55 配置项） |
| 9 | `src/core/logging_config.py` | loguru 初始化 |
| 10 | `src/core/exceptions.py` | 异常体系（10 类 + LLM 细分） |
| 11 | `src/core/errors.py` | LLM 错误分类器 |
| 12 | `src/core/database.py` | SQLAlchemy async engine |
| 13 | `src/core/middleware.py` | 请求上下文中间件 |

### 详细设计

#### 1.1 pyproject.toml（核心配置）
```toml
[project]
name = "smart-assistant"
version = "3.0.0"
requires-python = ">=3.12"
dependencies = [
    # AI 框架
    "langchain>=0.3.0", "langchain-openai>=0.3.0", "langgraph>=0.4.0",
    # 数据存储
    "chromadb>=0.6.0", "sqlalchemy[asyncio]>=2.0.0", "asyncpg>=0.30.0",
    "aiosqlite>=0.20.0",
    # Web 框架
    "fastapi>=0.115.0", "uvicorn[standard]>=0.34.0",
    "sse-starlette>=2.0.0", "python-multipart>=0.0.12",
    # 工具
    "pydantic>=2.0.0", "pydantic-settings>=2.0.0",
    "loguru>=0.7.0", "tenacity>=9.0.0", "python-dotenv>=1.0.0",
    # 邮件
    "aiosmtplib>=3.0.0",
    # 文档处理
    "pypdf>=5.0.0", "python-docx>=1.0.0", "openpyxl>=3.0.0",
    # 运维
    "alembic>=1.14.0", "slowapi>=0.1.9",
    "prometheus-fastapi-instrumentator>=7.0.0",
    "aiofiles>=24.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0", "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0.0", "httpx>=0.28.0",
    "ruff>=0.8.0", "mypy>=1.13.0",
    "pre-commit>=4.0.0",
]

[tool.ruff]
line-length = 120
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "C4", "SIM"]

[tool.mypy]
strict = true
python_version = "3.12"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "--cov=src --cov-report=term --cov-fail-under=80"

[tool.uv]
dev-dependencies = [...]
```

#### 1.2 配置项（完整 55 项）
```ini
# ---- AI 模型 ----
OPENAI_API_KEY=xxx
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
MODEL_NAME=qwen-plus
EMBEDDING_MODEL=text-embedding-v3

# ---- 应用 ----
APP_NAME=Smart Assistant
APP_VERSION=3.0.0
DEBUG=false
ENVIRONMENT=development          # development/staging/production

# ---- 日志 ----
LOG_LEVEL=INFO

# ---- 知识库 ----
KNOWLEDGE_CHUNK_SIZE=800
KNOWLEDGE_OVERLAP=150

# ---- 工具 ----
TOOL_TIMEOUT=15                  # 查询类超时（秒）
TOOL_WRITE_TIMEOUT=20            # 写入类超时（秒）
MAX_RETRIES=3

# ---- 数据库 ----
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/assistant
DEAD_LETTER_DB_URL=sqlite+aiosqlite:///data/dead_letter/dead_letter.db

# ---- ChromaDB ----
CHROMA_PERSIST_DIR=data/chroma_db

# ---- Redis（限流用） ----
REDIS_URL=redis://localhost:6379/0

# ---- 邮件 ----
SMTP_HOST=smtp.163.com
SMTP_PORT=465
SMTP_USERNAME=xxx@163.com
SMTP_PASSWORD=xxx
SMTP_SSL=true
SMTP_STARTTLS=false

# ---- Token 配额 ----
TOKEN_DAILY_LIMIT=500000
TOKEN_DAILY_COST_LIMIT=10.0
TOKEN_CACHE_READ_DISCOUNT=0.1
TOKEN_CACHE_WRITE_PREMIUM=1.25
TOKEN_DEFAULT_INPUT_PRICE=0.0008
TOKEN_DEFAULT_OUTPUT_PRICE=0.002
TOKEN_ALERT_THRESHOLD=0.8         # 80% 告警
TOKEN_ALERT_WEBHOOK=              # 告警 Webhook（可选）

# ---- Agent ----
AGENT_RECURSION_LIMIT=10
AGENT_MEMORY_MAX_MESSAGES=20
AGENT_SUMMARY_THRESHOLD=12
AGENT_MAX_DUPLICATE_CALLS=3
AGENT_CIRCUIT_BREAKER_THRESHOLD=5 # 连续失败 N 次熔断
AGENT_CIRCUIT_BREAKER_TIMEOUT=60  # 熔断恢复时间（秒）

# ---- 文件上传 ----
MAX_FILE_SIZE=20971520            # 20MB
ALLOWED_EXTENSIONS=txt,pdf,doc,docx,xls,xlsx

# ---- 检索 ----
HYBRID_SEARCH_ENABLED=true
VECTOR_CANDIDATE_MULTIPLIER=3
FTS_CANDIDATE_MULTIPLIER=2
RRF_CONSTANT_K=30
RE_RANKING_ENABLED=true
RE_RANK_THRESHOLD=5
MMR_ENABLED=true
MMR_LAMBDA=0.7
QUERY_REWRITING_ENABLED=true
DYNAMIC_THRESHOLD_ENABLED=true
SIMILARITY_THRESHOLD_BASE=0.15

# ---- 记忆 ----
MEMORY_TTL_HOURS=24
MEMORY_SUMMARY_TTL_HOURS=1

# ---- 限流 ----
RATE_LIMIT_PER_MINUTE=30          # 每用户每分钟请求数
RATE_LIMIT_PER_DAY=500            # 每用户每日请求数

# ---- 数据清理 ----
AUDIT_LOG_RETENTION_DAYS=90
TOKEN_USAGE_RETENTION_DAYS=365
```

#### 1.3 异常体系
```
AppException (Exception)
├── ConfigError
├── ValidationError
├── ToolTimeoutError
├── RetryExhaustedError
├── KnowledgeNotFoundError
├── TokenQuotaExceededError
├── RateLimitExceededError          # 新增
├── CircuitBreakerOpenError         # 新增
├── DeadLetterError                 # 新增
├── LLMServiceError
│   ├── LLMTimeoutError            # 9005
│   ├── LLMRateLimitError          # 9006
│   ├── LLMUnavailableError        # 9007
│   └── LLMContentFilterError      # 9008
└── DatabaseError
```

#### 1.4 依赖锁定
- `uv.lock`：精确锁定所有依赖版本
- `.python-version`：`3.12`
- CI 中 `uv sync --frozen` 确保可重现构建

### 验收标准
```bash
uv sync
uv run python -c "from src.core.config import settings; print(settings.MODEL_NAME)"  # → qwen-plus
uv run ruff check src/     # 0 errors
uv run mypy src/            # 0 errors
```

---

## 第二阶段：数据层与工具函数（26 文件）

### 目标
全部数据层（4 ORM + Alembic 迁移）+ 18 工具方法 + 检索流水线 + Token 计费 + 容错机制。

### 涉及文件

| # | 分类 | 文件 | 说明 |
|---|------|------|------|
| **ORM** | | | |
| 1 | models | `src/models/memo.py` | 备忘录表 |
| 2 | models | `src/models/token_usage.py` | Token 记录表 |
| 3 | models | `src/models/tool_audit.py` | 工具审计表 |
| 4 | models | `src/models/knowledge_file.py` | 知识库文件表 |
| **数据库迁移** | | | |
| 5 | alembic | `alembic/alembic.ini` | 迁移配置 |
| 6 | alembic | `alembic/env.py` | 迁移环境 |
| 7 | alembic | `alembic/script.py.mako` | 迁移模板 |
| 8 | alembic | `alembic/versions/001_initial.py` | 初始迁移 |
| **基础设施** | | | |
| 9 | core | `src/core/cache.py` | 工具降级缓存 |
| 10 | core | `src/core/schema.py` | 统一响应格式 |
| **知识库** | | | |
| 11 | knowledge | `src/knowledge/document_loader.py` | 多格式加载 |
| 12 | knowledge | `src/knowledge/chunker.py` | 段落→句子分块 |
| 13 | knowledge | `src/knowledge/vector_store.py` | ChromaDB CRUD |
| 14 | knowledge | `src/knowledge/retrieval.py` | 6 步检索流水线 |
| **工具** | | | |
| 15 | tools | `src/tools/knowledge_tool.py` | 5 方法 |
| 16 | tools | `src/tools/memo_tool.py` | 6 方法 |
| 17 | tools | `src/tools/email_tool.py` | 2 方法 |
| 18 | tools | `src/tools/date_tool.py` | 4 方法 |
| 19 | tools | `src/tools/user_tool.py` | 1 方法 |
| 20 | tools | `src/tools/tool_registry.py` | 注册中心+熔断 |
| 21 | tools | `src/tools/tool_wrapper.py` | 调用包装器 |
| **Token** | | | |
| 22 | token | `src/token/capture.py` | Token 捕获 |
| 23 | token | `src/token/cost.py` | 成本计算 |
| 24 | token | `src/token/quota.py` | 配额检查+告警 |
| 25 | token | `src/token/statistics.py` | 统计查询 |
| 26 | token | `src/token/dead_letter.py` | 写入容错（新增） |
| **初始化** | | | |
| 27 | scripts | `scripts/init_db.py` | 改为调用 alembic |
| 28 | scripts | `scripts/seed_data.py` | 示例数据 |
| **数据** | | | |
| 29 | data | `data/knowledge/ai_intro.txt` | 示例文档 |
| 30 | data | `data/knowledge/java_guide.txt` | 示例文档 |
| 31 | data | `data/knowledge/microservices.txt` | 示例文档 |

### 详细设计（仅列 v4 新增/变更部分）

#### 2.1 统一响应格式（`src/core/schema.py`）
```python
from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")

class R(BaseModel, Generic[T]):
    """统一响应"""
    code: int = 0
    data: T | None = None
    msg: str = "success"
    trace_id: str | None = None

class PageResponse(BaseModel, Generic[T]):
    """统一分页响应"""
    records: list[T]
    total: int
    page: int
    size: int

    @classmethod
    def of(cls, records, total, page, size):
        return cls(records=records, total=total, page=page, size=size)
```

#### 2.2 Token 写入容错（`src/token/dead_letter.py`）
```python
class TokenDeadLetter:
    """Token 写入主库失败时的兜底机制"""

    def __init__(self, sqlite_url: str):
        # 独立的 SQLite 引擎，不依赖主 PostgreSQL
        self.engine = create_async_engine(sqlite_url)

    async def save(self, record: dict):
        """保存到 SQLite 兜底库（主库写入失败时调用）"""

    async def retry_pending(self):
        """定期将 SQLite 中的记录重试写入主库（cron 调用）"""

    async def get_pending_count(self) -> int:
        """获取待重试记录数（/health 可暴露）"""
```

#### 2.3 工具包装器（`src/tools/tool_wrapper.py`）
```python
class ToolExecutor:
    """工具调用包装器 — 两层缓存 + 超时 + 审计 + 重复检测 + 熔断"""

    def __init__(self, registry: ToolRegistry, cache: ToolCache):
        ...

    async def execute(self, tool_name: str, tool_func, *args, user_id: str, trace_id: str) -> str:
        """执行工具调用，经过以下链条：
        1. 检查熔断状态（连续失败 ≥5 次 → CircuitBreakerOpenError）
        2. 检查缓存命中 → 直接返回
        3. asyncio.wait_for(tool_func, timeout)  → ToolTimeoutError
        4. 成功 → 写入缓存 + 更新熔断计数器(成功)
        5. 失败 → 降级缓存 get_fallback → 更新熔断计数器(失败)
        6. 审计日志异步写入（成功/失败均记录）
        7. 重复调用检测（同一 tool 连续 ≥3 次 → 终止）
        """
```

#### 2.4 工具注册中心集成熔断（`src/tools/tool_registry.py` 增量）
```python
class ToolRegistry:
    ...

    # 新增：熔断器
    class CircuitBreaker:
        def __init__(self, threshold=5, timeout=60):
            self.failure_count = 0
            self.last_failure_time = None
            self.is_open = False

        def record_success(self):
            self.failure_count = 0

        def record_failure(self):
            self.failure_count += 1
            if self.failure_count >= threshold:
                self.is_open = True

        def check(self):
            """熔断打开且未到恢复时间 → 抛异常"""
            if self.is_open and (time.time() - self.last_failure_time) < timeout:
                raise CircuitBreakerOpenError(...)
            if self.is_open and (time.time() - self.last_failure_time) >= timeout:
                self.is_open = False  # 半开，尝试恢复
                self.failure_count = 0
```

#### 2.5 配额检查集成告警（`src/token/quota.py` 增量）
```python
async def check_quota(user_id: str):
    today = await get_today_usage(user_id)
    if today.total_tokens > TOKEN_DAILY_LIMIT:
        raise TokenQuotaExceededError(...)
    if today.total_tokens > TOKEN_DAILY_LIMIT * TOKEN_ALERT_THRESHOLD:
        # 异步告警
        asyncio.create_task(send_alert(user_id, today))
```

### 验收标准
```bash
uv run alembic upgrade head                        # 4 张表创建成功
uv run python scripts/seed_data.py                  # 3 文档 + 5 备忘录导入
uv run python -c "
from src.tools.knowledge_tool import search_knowledge
print(search_knowledge.invoke({'query':'AI','user_id':'test'}))
# → 经过完整 6 步检索流水线返回结果
"
uv run python -c "
from src.token.cost import CostCalculator
calc = CostCalculator()
print(calc.calculate('dashscope', 'qwen-plus', 10000, 5000))
# → 0.018
"
uv run pytest tests/ -v --cov=src --cov-fail-under=80
```

---

## 第三阶段：单 Agent 工作流（5 文件）

### 目标
ReAct 工作流 + 记忆管理 + VectorMemory + 工具包装器集成。

### 涉及文件

| # | 文件 | 说明 |
|---|------|------|
| 1 | `src/models/state.py` | AgentState |
| 2 | `src/core/memory.py` | 增强记忆管理 |
| 3 | `src/agents/react_agent.py` | System Prompt + Agent 节点 |
| 4 | `src/workflows/react_workflow.py` | LangGraph StateGraph |
| - | `src/token/dead_letter.py` | （第二阶段已建，本阶段集成） |

### 详细设计（仅列 v4 新增/变更）

#### 3.1 完整工作流节点
```
__start__
  → rate_limit        # 新增：限流检查（slowapi / Redis 令牌桶）
  → quota_check       # 配额检查
  → load_memory       # 加载历史记忆 + VectorMemory 偏好检索
  → agent             # LLM 决策（18 工具，ToolExecutor 包装）
  → 条件边            # tool_calls? → tools : capture_token
  → tools             # ToolExecutor.execute() 内部包含：
  │                     cache查→超时控制→熔断检查→执行→缓存写/降级→审计→重复检测
  → capture_token     # Token 捕获（含 dead_letter 兜底）
  → save_memory       # 更新记忆 + extractAndStore 偏好
  → __end__
```

#### 3.2 记忆持久化
SmartMemory 使用 PostgreSQL（而非内存存储），流程重启不丢失：
```python
class SmartMemory:
    # 使用 memos 风格的独立表 chat_memory:
    # id, session_id, role(user/assistant), content, is_summary, created_at
    # 支持 TTL 清理（24h 过期自动删除）
    # 摘要单独存储（TTL 1h）
```

### 验收标准
```python
app = create_react_workflow()
result = app.invoke({
    "messages": [HumanMessage(content="帮我查一下AI内容")],
    "user_id": "test", "session_id": "s1"
})
# → 检索结果 + ai_token_usage 写入 + tool_audit_log 写入
```

---

## 第四阶段：多智能体简历匹配（2 文件）

与 v3 一致，不重复。

---

## 第五阶段：Supervisor 统一路由（2 文件）

与 v3 一致，不重复。

---

## 第六阶段：企业级加固与 API 封装（18 文件）

### 目标
FastAPI 接口 + 企业级加固（限流/指标/CORS/压缩/优雅关闭/Admin 端点/运维脚本）+ Docker Compose + CI/CD。

### 涉及文件

| # | 分类 | 文件 | 说明 |
|---|------|------|------|
| **API 核心** | | | |
| 1 | api | `src/api/main.py` | 应用工厂 + 生命周期（优雅关闭/CORS/GZip/限流/指标） |
| 2 | api | `src/api/schemas.py` | Pydantic 模型（第二阶段已建，本阶段扩展） |
| **路由** | | | |
| 3 | api | `src/api/routes/__init__.py` | 路由注册 |
| 4 | api | `src/api/routes/chat.py` | POST /api/v1/chat |
| 5 | api | `src/api/routes/knowledge.py` | POST /api/v1/upload 等 |
| 6 | api | `src/api/routes/token.py` | GET /api/v1/token/* |
| 7 | api | `src/api/routes/health.py` | /health/live + /health/ready（K8s 探针分离） |
| 8 | api | `src/api/routes/tools.py` | GET/POST /api/v1/tools（工具管理） |
| 9 | api | `src/api/routes/admin.py` | PUT /api/v1/admin/log-level、POST /api/v1/admin/cache/clear、POST /api/v1/admin/backup |
| **运维** | | | |
| 10 | scripts | `scripts/backup_chroma.py` | ChromaDB 导出到 JSON |
| 11 | scripts | `scripts/cleanup.py` | 审计日志/Token 记录定期清理 |
| **容器化** | | | |
| 12 | - | `Dockerfile` | Python 3.12-slim |
| 13 | - | `docker-compose.yml` | app + chromadb + postgres + redis |
| **CI/CD** | | | |
| 14 | - | `.github/workflows/ci.yml` | lint → test → build → push |
| **前端（可选）** | | | |
| 15-18 | - | 暂不做 | |

### 详细设计

#### 6.1 FastAPI 应用工厂（`src/api/main.py`）
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from prometheus_fastapi_instrumentator import Instrumentator

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：校验配置 → 初始化 DB → 注册工具 → 启动清理定时器
    settings.validate_required()
    await init_db()
    logger.info("应用启动完成")
    yield
    # 关闭：等待请求完成 → 关闭 DB 连接 → 关闭 ChromaDB
    await shutdown_db()
    logger.info("应用优雅关闭完成")

def create_app() -> FastAPI:
    app = FastAPI(title="Smart Assistant", version="3.0.0", lifespan=lifespan)

    # CORS
    app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)

    # GZip 压缩
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # 限流
    limiter = Limiter(key_func=lambda: ...)  # 按 user_id
    app.state.limiter = limiter
    app.add_exception_handler(429, _rate_limit_exceeded_handler)

    # Prometheus 指标
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    # 全局异常处理
    app.add_exception_handler(AppException, app_exception_handler)

    # 路由注册
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(knowledge.router, prefix="/api/v1")
    app.include_router(token.router, prefix="/api/v1")
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(tools.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")

    return app
```

#### 6.2 完整 API 端点（25 个）

| 方法 | 路径 | 说明 |
|------|------|------|
| **认证** | | |
| POST | `/api/v1/auth/register` | 用户注册（bcrypt） |
| POST | `/api/v1/auth/login` | 登录（返回 JWT） |
| POST | `/api/v1/auth/refresh` | Token 刷新 |
| GET | `/api/v1/auth/current` | 获取当前用户 |
| PUT | `/api/v1/auth/profile` | 更新资料 |
| POST | `/api/v1/auth/change-password` | 修改密码 |
| **用户** | | |
| GET | `/api/v1/user/preferences` | 获取偏好 |
| POST | `/api/v1/user/preferences` | 保存偏好 |
| PUT | `/api/v1/user/preferences` | 更新偏好 |
| **对话** | | |
| POST | `/api/v1/chat` | 统一对话入口（SSE 流式） |
| GET | `/api/v1/chat/audit-logs` | 工具审计日志 |
| **知识库** | | |
| POST | `/api/v1/knowledge/upload` | 上传文件（异步向量化） |
| GET | `/api/v1/knowledge/files` | 文件列表（从 DB 查询） |
| GET | `/api/v1/knowledge/files/{id}/status` | 文件处理状态（轮询） |
| DELETE | `/api/v1/knowledge/files/{id}` | 删除文件及向量 |
| GET | `/api/v1/knowledge/retrieve` | RAG 检索 |
| **备忘录** | | |
| POST | `/api/v1/memo` | 创建 |
| PUT | `/api/v1/memo/{id}` | 更新 |
| DELETE | `/api/v1/memo/{id}` | 删除 |
| GET | `/api/v1/memo/list` | 列表 |
| GET | `/api/v1/memo/search` | 搜索 |
| **Token** | | |
| GET | `/api/v1/token/records` | 记录（分页） |
| GET | `/api/v1/token/statistics` | 汇总统计 |
| GET | `/api/v1/token/by-model` | 按模型统计 |
| GET | `/api/v1/token/by-date` | 按日期统计 |
| GET | `/api/v1/token/quota` | 今日用量 |
| **工具管理** | | |
| GET | `/api/v1/tools` | 工具列表 |
| PUT | `/api/v1/tools/{name}/enable` | 启用 |
| PUT | `/api/v1/tools/{name}/disable` | 禁用 |
| **健康检查** | | |
| GET | `/health` | 健康检查 |
| GET | `/metrics` | Prometheus 指标 |

#### 6.3 健康检查 K8s 探针分离
```
/health/live  → HTTP 200 "ok"（仅检查进程存活）
/health/ready → {"status":"ok","components":{"chromadb":"healthy","postgresql":"healthy","llm":"healthy","dead_letter_pending":0}}
```
- `livenessProbe`：简单存活检查，不依赖外部服务
- `readinessProbe`：依赖外部服务检查，失败→摘除流量

#### 6.4 Docker Compose
```yaml
services:
  app:
    build: .
    ports: ["8000:8000"]
    environment: [...]
    depends_on:
      postgres: { condition: service_healthy }
      chromadb: { condition: service_healthy }
      redis: { condition: service_healthy }
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health/live"]
    deploy:
      resources:
        limits: { memory: 1G }

  chromadb:
    image: chromadb/chroma:latest
    ports: ["8001:8000"]
    volumes: ["./data/chroma_db:/chroma/chroma"]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/heartbeat"]

  postgres:
    image: postgres:16-alpine
    ports: ["5432:5432"]
    environment:
      POSTGRES_DB: assistant
      POSTGRES_PASSWORD: postgres
    volumes: ["./data/postgres:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
```

#### 6.5 CI/CD（`.github/workflows/ci.yml`）
```yaml
name: CI
on: [push, pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --frozen
      - run: uv run ruff check src/ tests/
      - run: uv run mypy src/

  test:
    needs: lint
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env: { POSTGRES_DB: assistant_test, POSTGRES_PASSWORD: postgres }
      chromadb:
        image: chromadb/chroma:latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --frozen
      - run: uv run alembic upgrade head
      - run: uv run pytest tests/ -v --cov=src --cov-fail-under=80

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t smart-assistant:${{ github.sha }} .
```

#### 6.6 优雅关闭
```python
# main.py lifespan yield 之后：
# 1. 停止接收新请求（设置 health/ready 为 not ready）
# 2. 等待现有请求完成（最多 30s）
# 3. 关闭 DB 连接池
# 4. 关闭 ChromaDB 客户端
# 5. 刷新日志缓冲区
```

#### 6.7 运维脚本

**ChromaDB 备份**（`scripts/backup_chroma.py`）：
```python
# 导出指定 collection 的全部 documents + embeddings 为 JSON
# 支持增量备份（按 upload_time 过滤）
# 输出到 data/chroma_db/backups/
```

**数据清理**（`scripts/cleanup.py`）：
```python
# 清理 tool_audit_log（>90 天）
# 清理 ai_token_usage（>365 天）
# 清理 chat_memory（>24h 过期会话）
# 通过 /api/v1/admin/cleanup 触发 或 cron
```

### 验收标准
```bash
docker-compose up -d
curl http://localhost:8000/health/live      # → "ok"
curl http://localhost:8000/health/ready     # → {"status":"ok","components":{...}}
curl http://localhost:8000/metrics           # → Prometheus 格式指标
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"帮我查一下AI内容","user_id":"test"}'  # → SSE 流式返回
```

---

## 第七阶段：文档与面试材料（4 文件）

| # | 文件 | 说明 |
|---|------|------|
| 1 | `docs/README.md` | 项目简介、Mermaid 架构图、功能列表、快速启动、API 文档、技术栈、亮点 |
| 2 | `docs/ARCHITECTURE.md` | 架构决策、状态流转、扩展规划 |
| 3 | `docs/INTERVIEW_QA.md` | 6 个面试追问 + 回答要点（含企业级加固追问） |
| 4 | `docs/DEMO.md` | 4 个完整演示用例 |

---

## 阶段验收总览

| 阶段 | 文件数 | 核心验收 |
|------|-------|---------|
| 1 | 13 | `ruff check` + `mypy` 0 errors，`settings.MODEL_NAME` → `qwen-plus` |
| 2 | 31 | 10 表迁移成功，18 工具可调用，检索流水线完整 |
| 3 | 6 | ReAct 多轮对话正常，ChatTongyi 流式输出 |
| 4 | 2 | 简历+JD → 完整评估报告 |
| 5 | 2 | 同一界面正确路由 |
| 6 | 20 | 25+ API 端点，JWT+Redis 认证，异步知识库上传，Docker 4 容器 |
| 7 | 4 | docs/ 下 4 文档齐全 |
| 8 | 20 | 认证模块 + 用户偏好 + 5 新表 + Token 回调 + 前端对齐 |
| **合计** | **98+** | |

---

## 企业级能力覆盖总览

| 维度 | 能力 | 实现 |
|------|------|------|
| **可观测性** | 结构化日志 | loguru JSON + request_id |
| | 链路追踪 | middleware trace_id 贯穿 |
| | Prometheus 指标 | /metrics + Instrumentator |
| | 告警 | Token 80% 阈值 + Webhook |
| | 审计 | tool_audit_log + API 查询 |
| **可靠性** | 超时控制 | 查询 15s / 写入 20s |
| | 重试 | tenacity 3 次 |
| | 熔断 | 连续 5 次失败→熔断 60s |
| | 降级 | ToolCache TTL + fallback |
| | 配额保护 | check_quota 入口拦截 |
| | 重复检测 | 连续 ≥3 次→终止 |
| | 死信队列 | SQLite 兜底 + 重试 |
| | 优雅关闭 | lifespan 处理 SIGTERM |
| | 限流 | slowapi 按 user_id |
| **安全性** | Prompt Injection | 12 组正则 + 防御提示 |
| | PII 脱敏 | 5 种正则替换 |
| | CORS | CORSMiddleware |
| | 请求大小限制 | 20MB |
| | SQL 注入防护 | SQLAlchemy 参数化 |
| **性能** | 连接池 | SQLAlchemy pool_size=10 |
| | GZip 压缩 | GZipMiddleware |
| | 工具缓存 | ToolCache（TTL 2min/5min） |
| | 异步处理 | asyncio 全链路 |
| **数据管理** | 数据库迁移 | Alembic |
| | 备份 | ChromaDB 导出脚本 |
| | 数据清理 | cleanup.py（cron） |
| | 事务 | SQLAlchemy async session |
| **代码质量** | 类型检查 | mypy strict |
| | 代码规范 | ruff + pre-commit |
| | 测试覆盖率 | pytest-cov ≥80% |
| | 依赖锁定 | uv.lock |
| **CI/CD** | 自动化流水线 | GitHub Actions |
| **运维** | 健康检查 | liveness/readiness 分离 |
| | Docker 资源限制 | mem_limit |
| | 配置校验 | 启动时 validate_required |
| | 日志级别热更新 | PUT /admin/log-level |

