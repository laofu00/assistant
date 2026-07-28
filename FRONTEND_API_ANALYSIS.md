# 前端 API 对接分析

**前端来源**：`D:\LocalWork\java\smart-assistant\frontend`（Vue 3 + Element Plus）
**后端目标**：`D:\LocalWork\Python\assistant\backend`（FastAPI）
**分析日期**：2026-07-27

---

## 一、环境变量

前端 `.env.test`：
```
VITE_API_BASE_URL=http://localhost:90/api
```
需改为：
```
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

---

## 二、响应格式差异（🔴 核心阻塞）

| 字段 | Java 后端 | Python 后端 | 影响 |
|------|----------|------------|------|
| 成功码 | `code: 200` | `code: 0` | **前端拦截器只认 `code === 200`，否则全部 reject** |
| 消息字段 | `message` | `msg` | 前端 `response.data.message` 读不到 |

**结论**：必须修改 Python `src/api/routes/` 统一返回 `code: 200, msg: "success"`，或者改 `src/core/schema.py` 默认值 + 字段名。

---

## 三、逐接口对比

### 3.1 对话 `/chat`

| 方面 | 前端调用 | Python 后端 | 状态 |
|------|---------|------------|------|
| 流式接口 | `GET /chat/stream?message=xxx` (SSE) | `POST /api/v1/chat` (JSON body + SSE) | ❌ 方法+参数不匹配 |
| 同步接口 | `POST /chat?message=xxx` (query params) | 无 | ❌ 缺失 |

**问题**：
1. 前端用 GET + query param，后端用 POST + JSON body — 完全不兼容
2. 需要新增 `GET /chat/stream` 或修改前端 `sendMessageStream()`

### 3.2 知识库 `/knowledge`

| 前端接口 | Python 后端 | 状态 |
|---------|------------|------|
| `POST /knowledge/upload` (multipart, file + form fields) | `POST /api/v1/knowledge/upload` (file + user_id form) | ✅ 匹配 |
| `GET /knowledge/files?page=1&size=10` | `GET /api/v1/knowledge/files` (无分页) | ❌ 缺少分页参数 |
| `DELETE /knowledge/files/{id}` | `DELETE /api/v1/knowledge/files/{filename}` | ❌ ID vs 文件名 |
| `GET /knowledge/retrieve?query=&topK=5` | **缺失** | ❌ 无此端点 |
| `GET /knowledge/files/{id}/status` | **缺失** | ❌ 无此端点 |
| `GET /knowledge/files/statuses` | **缺失** | ❌ 无此端点 |

### 3.3 备忘录 `/memo`

| 前端接口 | Python 后端 | 状态 |
|---------|------------|------|
| `POST /memo` (JSON body) | **缺失** | ❌ 无 REST 端点 |
| `PUT /memo/{id}` | **缺失** | ❌ 无 REST 端点 |
| `DELETE /memo/{id}` | **缺失** | ❌ 无 REST 端点 |
| `GET /memo/list?category=&page=&size=` | **缺失** | ❌ 无 REST 端点 |

> Java 版备忘录通过 smart-memo 微服务提供 REST API。Python 版仅通过 @tool 让 LLM 操作，缺少面向前端的 CRUD 接口。

### 3.4 认证 `/auth`

| 前端接口 | Python 后端 | 状态 |
|---------|------------|------|
| `POST /auth/login` | **缺失** | ❌ |
| `POST /auth/register` | **缺失** | ❌ |
| `GET /auth/current` | **缺失** | ❌ |
| `PUT /auth/profile` | **缺失** | ❌ |
| `POST /auth/change-password` | **缺失** | ❌ |

> 前端拦截器强制要求 JWT token（`Authorization: Bearer xxx`），所有请求带 `X-User-Id`。

### 3.5 Token 统计 `/token`

| 前端接口 | Python 后端 | 状态 |
|---------|------------|------|
| `GET /token/records?userId=&startTime=&endTime=&pageNum=&pageSize=` | `GET /api/v1/token/records?user_id=&page=&size=` | ❌ 参数名不一致 |
| `GET /token/statistics` | `GET /api/v1/token/statistics` | ❌ 参数名不一致（userId vs user_id） |
| `GET /token/by-model` | `GET /api/v1/token/by-model` | ❌ 同上 |
| `GET /token/by-date` | `GET /api/v1/token/by-date` | ❌ 同上 |
| `POST /token/recalculate-cost` | **缺失** | ❌ |
| `GET /token/quota` | `GET /api/v1/token/quota` | ❌ 同上 |

### 3.6 工具管理 `/tools`

| 前端接口 | Python 后端 | 状态 |
|---------|------------|------|
| `GET /tools` | `GET /api/v1/tools` | ✅ |
| `GET /tools/{toolName}` | **缺失** | ❌ |
| `POST /tools/{toolName}/enable` | `PUT /api/v1/tools/{name}/enable` | ❌ POST vs PUT |
| `POST /tools/{toolName}/disable` | `PUT /api/v1/tools/{name}/disable` | ❌ POST vs PUT |
| `GET /chat/audit-logs` | **缺失** | ❌ |

---

## 四、修复方案

### 方案 A：改前端（推荐，改动最小）

修改 3 个前端核心文件即可对接：

#### 1. `src/api/index.js` — 响应拦截器
```diff
- if (response.data.code === 200) {
+ if (response.data.code === 0) {
```
同时 `baseURL` 添加 `/v1` 前缀。

#### 2. `src/api/index.js` — 流式对话
```diff
- GET /chat/stream?message=xxx
+ POST /chat (JSON body: {message, user_id})
```

#### 3. 新增缺失的后端端点（P0 必需）
- `GET /api/v1/knowledge/files` — 增加分页参数（page, size）
- 备忘录 CRUD REST 接口（`/api/v1/memo`）
- 认证简化（跳过 JWT，或 mock）

#### 4. 可选（降低页面报错）
- `GET /api/v1/knowledge/files/{id}/status` — 返回文件状态
- `GET /api/v1/tools/{name}` — 返回单个工具详情

### 方案 B：改后端对齐 Java API

修改所有 Python 端点，完全兼容 Java API 格式。工作量更大，需要改 6 个 route 文件 + schema。

---

## 五、推荐执行

| 优先级 | 操作 | 方式 |
|-------|------|------|
| 🔴 P0 | 响应格式对齐 | 改前端 `code: 200 → 0`，1 行 |
| 🔴 P0 | 流式对话接口 | 改前端 `GET → POST /chat` |
| 🔴 P0 | 备忘录 REST API | 后端新增 `src/api/routes/memo.py` |
| 🟡 P1 | Token 参数名对齐 | 后端统一用 `user_id` 或前端改为 `userId` |
| 🟡 P1 | 知识库分页+状态 | 后端扩展 knowledge router |
| 🟡 P1 | 认证简化 | 前端绕过 JWT（直接传 user_id） |
| 🟢 P2 | 工具管理细节 | POST→PUT、详情端点 |
| 🟢 P2 | 审计日志 | 新增端点或前端隐藏 |
| ⚪ 可选 | 费用重算 | 新增端点或前端隐藏 |
