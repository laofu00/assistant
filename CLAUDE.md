# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Smart Assistant — 基于 AI 大模型的个人智能助手，Python 重构版（原 Java Spring Cloud 微服务）。

- **后端**: FastAPI + LangGraph + LangChain，单体架构
- **前端**: Vue 3 + Element Plus + Pinia + Vue Router
- **模型**: 通义千问 qwen-plus（DashScope），嵌入 text-embedding-v3
- **存储**: PostgreSQL + ChromaDB + Redis

## 常用命令

### 后端

```bash
cd backend
.venv/Scripts/activate          # Windows 激活虚拟环境
uvicorn src.api.main:app --reload --port 8000
alembic upgrade head            # 数据库迁移
alembic revision --autogenerate -m "描述"  # 生成新迁移
ruff check src/                 # lint
ruff format src/                # 格式化
mypy src/                       # 类型检查
pytest                          # 运行测试
```

### 前端

```bash
cd frontend
npm install
npm run dev                     # Vite dev server，端口 3000，代理 /api → localhost:8000
```

### Docker

```bash
docker compose up -d            # 全部服务
docker compose --profile init up alembic  # 初始化数据库
```

## 架构

### 请求路由

```
POST /api/v1/chat (SSE)
  → RequestContextMiddleware (JWT + Redis 认证)
  → Supervisor 意图分类 (关键词快匹配 → LLM 精确分类)
      ├── general → ReAct 工作流 (LLM + 18 工具，自主决策)
      └── match   → 简历匹配子图 (3 Agent 并行评估 + 加权汇总)
```

### 简历匹配子图（关键）

文件: `backend/src/workflows/match_workflow.py`

```
fetch_docs (从 ChromaDB 取简历+JD)
  → LangGraph Send fan-out 并行:
      ├── tech_agent (技术评估 40%)
      ├── exp_agent (经验评估 35%)
      └── risk_agent (风险评估 25%)
  → summarize (加权汇总，生成 Markdown 报告)
```

- **双模式** (`match_mode` 字段): `recruiter`（招聘方打分）vs `candidate`（候选人面试准备），Supervisor 自然语言自动切换
- Prompt 和汇总函数各自独立，都在 `backend/src/agents/match_agents.py`
- 报告通过 SSE 逐行流式输出，`json.dumps` 编码保护换行格式

### SSE 流式

- `backend/src/api/routes/chat.py` 中的 `_stream_chat` 异步生成器
- `supervisor_app.astream_events(version="v2")` 捕获 LangGraph 事件
- `match_depth` 嵌套计数器防止子图事件重复输出
- 前端 `fetch` + `ReadableStream.getReader()` 逐行解析（`backend/src/api/index.js`）
- JSON 编码的 chunk 由前端 `JSON.parse` 还原换行
- **Mock 端点**: `POST /api/v1/chat/mock` — 压测专用，完整中间件链路 + 模拟 SSE 输出，不调用真实 LLM

### 自适应检索管线（RAG）

文件: `backend/src/knowledge/retrieval.py`

6 步检索流水线，各组件根据知识库规模自适应开关，避免小数据集下过度调用 LLM：

```
查询重写(chunk≥30) → 混合检索(向量+BM25) → RRF 融合 → MMR 多样化(候选>top_k×2) → Rerank 重排(候选>20) → RAG 生成
```

| 组件 | 触发条件 | 配置项 | 说明 |
|------|---------|--------|------|
| 查询重写 | 全量 chunk ≥ 30 | `QUERY_REWRITE_MIN_DOCS` | 小数据集跳过，LLM 重写反引入噪声 |
| 混合检索 | 始终启用 | `HYBRID_SEARCH_ENABLED` | 向量 + BM25，消融实验证明唯一正向贡献 |
| MMR 多样化 | 候选 > top_k × 2 | `MMR_ENABLED` | 候选不足时无多样性优化空间 |
| Rerank 重排序 | 候选 > 20 | `RE_RANKING_ENABLED` | 小候选集跳过 gte-rerank API 调用 |

关键结论（来自消融实验）：
- BM25 混合检索是唯一正向贡献组件（Hit@1 +6.2%）
- 查询重写和 Rerank 在小文档集下是负优化（Hit@1 分别降 1.2% 和 1.3%）
- 自适应后检索延迟从 2.3s 降至 205ms（-91%），精度无损

评测脚本位于 `tests/rag_*.py`，结果记录在 `tests/bench_results.md`。

### 认证 & 角色

- JWT (HS256, 24h) + Redis 双校验
- 中间件 `RequestContextMiddleware` (纯 ASGI) 在入口统一拦截
- OPTIONS 预检请求直接放行到 CORS 中间件
- 非公开路径：解析 JWT → Redis 校验 token 匹配 → `request.state.user_id`
- 路由层不再做二次认证判断，直接信任 `request.state.user_id`
- 公开路径: `/api/v1/auth/login`, `/api/v1/auth/register`, `/health`, `/metrics`, `/docs`

**角色系统**（`backend/src/core/auth_deps.py`）：
- `User.roles` 逗号分隔字符串（如 `"admin,READ_WRITE"`）
- `is_admin_user(user_id)` — 查 DB 确认是否有 admin 角色（兼容 `ROLE_ADMIN`）
- `require_admin` — FastAPI 依赖，非管理员返回 403
- 前端 `useUserStore.isAdmin` — 登录时从后端返回 `roles`，App 启动时通过 `/auth/current` 同步
- 管理员专属页面：用户管理、工具管理、审计日志、记忆管理（路由 `requiresAdmin` + 侧边栏 `v-if`）

### AgentState

文件: `backend/src/models/state.py`，LangGraph TypedDict，贯穿所有节点：
- `messages`: `Annotated[list[BaseMessage], add_messages]`（对话消息，自动追加）
- `intent`: `general` | `match`
- `match_mode`: `recruiter` | `candidate`
- `resume_filename`, `jd_text`, `match_report`, `final_score`: 匹配专用
- `_tech_result`, `_exp_result`, `_risk_result`: 中间结果（下划线前缀约定）

### 工具调用与管理

ReAct 工作流中工具经过 `ToolExecutor` (`backend/src/tools/tool_wrapper.py`) 统一包装，完整执行链（12 步）：

1. 输入参数校验 → 2. 运行时权限验证（ADMIN 级工具拦截）→ 3. 依赖健康检查
→ 4. 三层限流 → 5. 熔断检查 → 6. 全局禁用 + 用户黑名单双重检查
→ 7. 重复调用检测 → 8. 只读工具缓存 → 9. 超时控制 → 10. 返回值截断
→ 11. 缓存/熔断状态更新 → 12. 审计日志 + Prometheus 指标

**工具禁用系统**：
- 全局禁用：`POST /tools/{name}/disable` — 内存 `ToolMeta.enabled=False` + 持久化 `tool_config` 表
- 用户级禁用：`POST /tools/users/{user_id}/disable` — `user_tool_blacklist` 表（用户+工具唯一）
- 硬拦截：每次 Agent 决策前 `bind_tools` 时滤掉 `enabled=False` 的工具，LLM 完全不可见
- 启动时从 `tool_config` 表加载禁用配置（`main.py` lifespan）
- 工具权限级别支持在线修改：`PUT /tools/{name}/permission`

**备忘录工具**（`backend/src/tools/memo_tool.py`）：
- `list_memos` — 统一查询入口，支持 keyword / category / status / due_before / due_after / 分页
- `delete_memos_batch` — 批量删除，`confirmed=False` 仅预览，`confirmed=True` 真删（强制确认）
- 递归限制 `AGENT_RECURSION_LIMIT` 控制最大 agent↔tools 循环步数

### 前端 Store 约定

- `useUserStore()`: `token`, `userId`, `username`, `nickname`, `roles`, `isAdmin`（同步 localStorage）
  - `syncRoles()` — 启动时从 `/auth/current` 同步角色
  - 登录时检测用户切换 → 自动清空旧用户的 `chat_*` localStorage
- `useChatStore()`: 消息列表 + 会话列表 + 流式拼接
  - `clearMessages()` — 清空当前会话 + 所有 `chat_*` localStorage + 调用后端清除 Redis 记忆
  - 会话按 `chat_msgs_{sessionId}` 隔离存储
- `chatApi.sendMessageStream()`: SSE 流式 fetch，不走 axios

### 管理员数据可见性

管理员访问普通功能页面时自动查看全部用户数据：
- 知识库 `list_files` / 备忘录 `list_memos` — 跳过 `user_id` 过滤
- Token 统计 — `user_id=None` → 查全部用户汇总
- 审计日志 `chat/audit-logs` — 管理员看全部用户，显示 `user_name`（nickname > username）
- 记忆管理 `memory/sessions` — `list_all_user_sessions()` Redis 扫描全量，详情带 `owner_user_id`

## 开发注意事项

- **后端虚拟环境**: 使用 `backend/.venv/`，Python 3.13+
- **API 响应格式**: 统一 `{code: 0, data: ..., msg: "success"}`（`backend/src/core/schema.py` 中 `R` 类）
- **前端 baseURL**: `VITE_API_BASE_URL` 默认 `http://localhost:8000/api/v1`，开发时不走 Vite 代理直接连后端
- **ChromaDB**: 支持嵌入式（PersistentClient，`CHROMA_URL=""`）或 HTTP 客户端（`CHROMA_URL=http://localhost:8001`）
- **Token 捕获**: 使用 LangChain `TokenCaptureCallback` + 内存队列 + 后台任务写入 DB（避免 event loop 冲突）
- **子图编译**: match_app 和 react_app 在模块级别 `.compile()`，导入即编译
- **前端路由**: hash 模式 (`createWebHashHistory`)，`requiresAuth` / `requiresAdmin` meta 受路由守卫保护
- **ReAct Agent 流式**: `get_llm(streaming=True)` — langchain-community 0.4.2 已修复 ChatTongyi 流式 + tool_calls 的 `subtract_client_response` 索引越界 bug
- **递归限制**: `AGENT_RECURSION_LIMIT` 同时控制 supervisor 和 react_subgraph，防止死循环。`.env` 中配置项会被 Pydantic Settings 自动加载，优先级高于 `config.py` 默认值
- **链路追踪**: 支持 LangFuse（云部署）和 LangSmith（本地开发）双模式，`llm_factory.py` 中 `setup_tracing()` 在应用启动时自动选择（LangFuse > LangSmith 优先级），详见 `.env` 配置项
- **Redis 连接池**: `max_connections=100`（`redis_client.py`），支持 20+ 并发 JWT 校验
- **限流**: `/api/v1/chat/mock` 单独配置 200/min，避免压测时被 chat 的 20/min 限制误伤

## 测试

| 脚本 | 用途 |
|------|------|
| `tests/rag_eval.py` | RAG 检索质量评测（Hit Rate@K / MRR / NDCG） |
| `tests/rag_ablation.py` | 消融实验（组件开关对比） |
| `tests/rag_debug_failures.py` | 失败案例分析（Top-N 关键词命中） |
| `tests/rag_gen_eval.py` | 生成质量评估（Faithfulness / Answer Relevancy） |
| `tests/cache_bench.py` | 缓存命中率模拟 + 成本分析 |
| `tests/perf_test.py` | asyncio 并发压测（替代 Locust，避免 Windows gevent 问题） |
| `tests/locustfile.py` | Locust 压测（需 Linux/Mac） |
| `tests/bench_results.md` | 评测结果记录 |

运行方式见各脚本头部注释。

## 文档

| 文件 | 内容 |
|------|------|
| `docs/ARCHITECTURE.md` | 架构决策记录（并行、认证、Token 捕获、扩展规划等） |
| `docs/resume-match.md` | 简历匹配流程文档（数据流、耗时分析、文件清单） |
| `docs/README.md` | 项目简介、Mermaid 架构图、API 文档、快速启动 |
| `tests/bench_results.md` | 性能评测记录（5 轮优化历程） |
| `tests/rag_debug_plan.md` | RAG 排查方案（嵌入/检索/生成三方向） |
| `DEVELOPMENT_PLAN.md` | 开发计划（历史） |
| `PROGRESS.md` | 开发进度记录 |
