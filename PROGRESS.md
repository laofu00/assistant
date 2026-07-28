# Smart Assistant Python 重构 — 开发进度

**项目路径**：`D:\LocalWork\Python\assistant`
**后端代码**：`backend/`（Python + FastAPI + LangGraph）
**前端代码**：`frontend/`（Vue 3）
**计划版本**：v4（企业级标准）
**开始日期**：2026-07-27

---

## 进度总览

| 阶段 | 状态 | 完成日期 |
|------|------|---------|
| 第一阶段：项目骨架与基础配置 | 🟢 已完成 | 2026-07-27 |
| 第二阶段：数据层与工具函数 | 🟢 已完成 | 2026-07-27 |
| 第三阶段：单Agent工作流（ReAct模式） | 🟢 已完成 | 2026-07-27 |
| 第四阶段：多智能体简历匹配模块 | 🟢 已完成 | 2026-07-27 |
| 第五阶段：Supervisor统一路由 | 🟢 已完成 | 2026-07-27 |
| 第六阶段：企业级加固与API封装 | 🟢 已完成 | 2026-07-27 |
| 第七阶段：文档与面试材料 | 🟢 已完成 | 2026-07-27 |
| 第八阶段：对齐Java项目 + 认证模块 | 🟢 已完成 | 2026-07-28 |
| **合计** | **8 / 8 ✅** | |

---

## 第八阶段：对齐Java项目 — 🟢 已完成 (2026-07-28)

### 数据库表结构对齐
- [x] 新建 `user_info` 表（含 bcrypt 密码加密）
- [x] 新建 `user_preference` 表
- [x] 新建 `user_token` 表（JWT 管理）
- [x] 新建 `operation_log` 表（操作日志）
- [x] 新建 `user_notification` 表（用户通知）
- [x] `memos` → `memo` 重命名 + `status` 字段 String→Integer
- [x] `tool_audit_log`：`success`→`result`，`error_message`→`error_msg`，补充 `conversation_id`、`updated_at`
- [x] `ai_token_usage`：补充 `input_unit_price`、`output_unit_price`、`deleted`、`updated_at`
- [x] Alembic 迁移脚本含数据迁移（VARCHAR→INTEGER、Boolean→String）

### 认证模块（新增）
- [x] `POST /api/v1/auth/register` — 用户注册（bcrypt）
- [x] `POST /api/v1/auth/login` — 登录（返回 JWT）
- [x] `GET /api/v1/auth/current` — 获取当前用户
- [x] `PUT /api/v1/auth/profile` — 更新资料（手机/邮箱空值跳过校验）
- [x] `POST /api/v1/auth/change-password` — 修改密码（清除 Redis token）
- [x] `POST /api/v1/auth/refresh` — Token 刷新
- [x] JWT 中间件（RequestContextMiddleware）：解码 JWT + Redis 校验
- [x] Redis 存储 token（`token:{user_id}`，TTL=24h）
- [x] 改密强制登出（删除 Redis key）

### 用户模块（新增）
- [x] `GET/POST/PUT /api/v1/user/preferences` — 用户偏好 CRUD
- [x] 用户 ID 从 `request.state.user_id`（中间件注入）读取

### 认证流程
```
登录 → 校验密码 → 生成 JWT → 写入 Redis(token:{userId}, TTL=24h)
请求 → Bearer token → 中间件解码 JWT → 校验 Redis → request.state.user_id
改密 → 删除 Redis key → 旧 token 立即失效
```

### LLM 层切换
- [x] `ChatOpenAI`（OpenAI 兼容接口）→ `ChatTongyi`（DashScope 原生 SDK）
- [x] 原生 SDK 返回真实 token usage（`response_metadata.token_usage`）
- [x] `streaming=True` 启用流式输出
- [x] SSE 按 `name == "ChatTongyi"` 过滤，只输出主 Agent 回复

### Token 捕获
- [x] `TokenCaptureCallback` — LangChain 回调拦截 `on_llm_end`
- [x] 队列 + 后台 asyncio 任务写入 DB（避免 event loop 冲突）
- [x] `main.py` lifespan 启动 `start_token_worker()`
- [x] 统计 API 字段 camelCase 对齐前端

### 知识库
- [x] 上传异步处理：PENDING → PROCESSING → COMPLETED/FAILED
- [x] 文件元数据写入 `knowledge_file` 表
- [x] 列表/状态查询/删除均从 DB 读取
- [x] 删除按 `file_id`（非文件名）防同名误删
- [x] ChromaDB embedding：本地模型 → DashScope API（`text-embedding-v3`）
- [x] 双模式支持：`CHROMA_URL` 为空=嵌入式，设为 URL=HttpClient

### 分块策略对齐
- [x] overlap 逻辑修复（保留尾部句子到下一块开头）
- [x] 文档加载器：txt/pdf/docx/doc/xlsx/xls

### 前端修复
- [x] 列表页数据读取路径（`response.data.records` vs `response.data`）
- [x] 菜单跳转双重导航（移除冗余 `handleMenuSelect`）
- [x] Token 统计页 `code===200`→`code===0`，字段名对齐
- [x] 知识库上传 URL `/api/` → `/api/v1/`
- [x] 上传响应校验 `code===200`→`code===0`
- [x] 删除文件 `file.id` → `file.id`（后端改接收 ID）
- [x] 用户名不可修改 → disabled
- [x] 登录成功后显示昵称（`displayName`）
- [x] 登录页面 Enter 键触发
- [x] 修改密码（前端对接后端）
- [x] 手机/邮箱空值校验跳过
- [x] 知识库表头宽度调整

### Docker 部署配置
- [x] PostgreSQL 时区 `TZ: Asia/Shanghai` + `PGTZ: Asia/Shanghai`
- [x] Redis 密码认证 `--requirepass`
- [x] ChromaDB 端口映射 `8001:8000`
- [x] `.env.docker` 补全：DATABASE_URL、REDIS_URL、JWT_SECRET、SMTP_* 等

---

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-07-27 | v1~v4 计划演进 |
| 2026-07-27 | 🟢 P1 完成：项目骨架 |
| 2026-07-27 | 🟢 P2 完成：数据层 + 工具函数 |
| 2026-07-27 | 🟢 P3 完成：ReAct 工作流 |
| 2026-07-27 | 🟢 P4 完成：简历匹配 |
| 2026-07-27 | 🟢 P5 完成：Supervisor 路由 |
| 2026-07-27 | 🟢 P6 完成：API + 部署 |
| 2026-07-27 | 前端迁移 + API 对齐 |
| 2026-07-27 | 🟢 P7 完成：文档 |
| 2026-07-28 | 🟢 P8 完成：对齐Java项目 + 认证模块 + LLM切换 + Token捕获 |
| **2026-07-28** | **🎉 全部 8 阶段完成** |
| 2026-07-29 | 🔧 Token 过期不跳转登录页修复（中间件 401 + CORS 头 + 路由层去冗余校验） |
| 2026-07-29 | ✨ 简历匹配优化：`asyncio.gather` → LangGraph Send fan-out 并行 |
| 2026-07-29 | ✨ 简历匹配新增候选人视角模式（"帮我分析这个岗位" → 面试准备报告） |
| 2026-07-29 | 🔧 匹配报告流式输出：逐行 SSE + JSON 编码保护换行格式 |
| 2026-07-29 | 📝 新增 `docs/resume-match.md` 完善简历匹配流程文档 |
