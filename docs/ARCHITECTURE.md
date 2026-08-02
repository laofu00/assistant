# Smart Assistant — AI Agent 系统工程架构文档

---

## 目录

1. [系统概览](#1-系统概览)
2. [请求全链路](#2-请求全链路)
3. [Agent 决策引擎](#3-agent-决策引擎)
4. [简历匹配多 Agent](#4-简历匹配多-agent)
5. [工具治理体系](#5-工具治理体系)
6. [记忆体系](#6-记忆体系)
7. [安全防护](#7-安全防护)
8. [可观测性](#8-可观测性)
9. [韧性设计](#9-韧性设计)
10. [成本控制](#10-成本控制)
11. [前端架构](#11-前端架构)
12. [数据模型](#12-数据模型)
13. [部署架构](#13-部署架构)

---

## 1. 系统概览

### 1.1 一句话定位

**基于 LangGraph 的企业级 AI Agent 系统**：ReAct 决策引擎 + 多 Agent 并行评估 + 18 工具自主调用 + 三层记忆体系 + 完整工程韧性。

### 1.2 技术栈

| 层 | 技术 | 用途 |
|---|------|------|
| Agent 框架 | LangGraph + LangChain | ReAct 决策、多 Agent 编排、状态管理 |
| LLM | 通义千问 qwen-plus / qwen-turbo | 对话推理、意图分类、事实提取 |
| Embedding | text-embedding-v3 (DashScope API) | 知识库向量化、语义检索 |
| 后端 | FastAPI + Python 3.13 | REST + SSE 流式 |
| 前端 | Vue 3 + Element Plus + Vite | SPA 管理界面 + 流式对话 |
| 数据库 | PostgreSQL 16 | 业务数据、Token 统计、审计日志 |
| 向量库 | ChromaDB | 知识库检索、长期记忆语义匹配 |
| 缓存 | Redis 7 | JWT、短期记忆、限流计数 |
| 可观测性 | LangFuse + Prometheus + loguru | 链路追踪、指标、结构化日志 |

### 1.3 核心数字

| 指标 | 数值 |
|------|------|
| 工具数量 | 18 个（知识库5 + 备忘录6 + 邮件3 + 日期4） |
| Agent 数量 | 1 ReAct + 3 Match 评估 + 1 Supervisor |
| 记忆层数 | 3（短期 Redis + 长期 PG + 语义 ChromaDB） |
| 限流层数 | 6（工具3层 + API 3层） |
| 测试用例 | 438 个 |
| 代码覆盖率 | 67%（34 个模块超 80%） |
| 容器数 | 4（app + pg + chroma + redis） |

---

## 2. 请求全链路

### 2.1 入口：POST /api/v1/chat (SSE)

```
Client (Vue3 + fetch ReadableStream)
  │
  ├─ ApiRateLimitMiddleware    ← 第1关：三层 API 限流（Redis原子计数）
  ├─ RequestContextMiddleware  ← 第2关：JWT解析 + Redis token校验
  ├─ Supervisor 意图分类       ← 第3关：关键词快匹配 → LLM精确分类
  │     ├── general → ReAct 工作流
  │     └── match   → 简历匹配子图
  └─ SSE 逐行流式返回          ← json.dumps 保护格式
```

### 2.2 认证链路

```
POST /auth/login
  → 查DB校验密码（bcrypt）
  → 生成 JWT（HS256, 24h）
  → Redis SET token:{userId} = jwt（EX 24h）

后续请求：
  → Authorization: Bearer <jwt>
  → 中间件解码 sub → userId
  → Redis GET token:{userId} == jwt?（双重校验）
  → request.state.user_id → 下游路由直接信任
```

关键设计：
- **双校验**：JWT 签名 + Redis 存在性，改密/退出时直接 `DELETE token:{userId}` 即可令旧 token 失效
- **中间件统一鉴权**：路由层不做二次认证，`request.state.user_id` 即已认证的用户ID

### 2.3 意图分类（Supervisor）

```
用户消息
  │
  ├─ 关键词快匹配（免 LLM 调用）
  │     match_keywords = ["匹配","简历匹配","岗位匹配","帮我分析",...]
  │     candidate_keywords = ["帮我分析","我适合","怎么准备","我的优势",...]
  │     ↓ 无匹配 → 直接返回 intent=general
  │
  └─ LLM 精确分类（qwen-turbo, temperature=0）
        输入: System Prompt + 用户消息
        输出: {"intent":"match|general","resume_file":"...","match_mode":"recruiter|candidate"}
        ↓ LLM失败 → 降级为 general
```

---

## 3. Agent 决策引擎

### 3.1 ReAct 工作流

```
┌─────────────┐
│ quota_check │ → 每日Token配额检查
└──────┬──────┘
       ▼
┌──────────────┐
│ load_memory  │ → 加载短期记忆(Redis) + 长期记忆(PG+ChromaDB)
└──────┬───────┘      合并后替换最后一条用户消息
       ▼
┌─────────┐    有tool_calls    ┌───────┐
│  agent  │ ─────────────────→ │ tools │
│(LLM决策)│ ←───────────────── │(执行器)│
└────┬────┘    无tool_calls    └───────┘
     │
     ▼
┌──────────────┐
│ save_memory  │ → 保存对话到 Redis + 触发长期记忆萃取
└──────┬───────┘
       ▼
     __end__
```

### 3.2 Agent 决策节点

```
System Prompt (~50行规则)
  + 工具schema (已启用的 @tool)
  + 注入记忆（短期摘要 + 长期事实 + 用户画像）
  + 注入 userId
  + 注入安全规则

→ LLM (qwen-plus, temperature=0.3, streaming=False)
  → bind_tools(仅 enabled=True 的工具)  ← 动态过滤，禁用工具LLM不可见
  → invoke(messages)
  → AIMessage { content, tool_calls? }
```

关键设计：
- **每次重新调工具**：不信任历史数据，LLM 每次决策都是从零开始
- **工具报错不跳过**：报错是临时的，下次仍需尝试
- **禁止跳过步骤**：如邮件必须先 preview 再 send
- **禁用工具硬拦截**：每次 bind_tools 时滤掉 enabled=False 的工具，LLM 完全不可见

### 3.3 工具执行器（12步执行链）

```
输入参数
  → 1. Pydantic Schema 校验 + 字符串长度校验
  → 2. 运行时权限验证（ADMIN级工具需管理员）
  → 3. 依赖健康检查（ChromaDB/PG/SMTP探针） → 不健康则降级缓存
  → 4. 三层限流（用户工具 / 全局工具 / 用户总QPS）
  → 5. 熔断器状态检查 → 打开则拒绝
  → 6. 工具启用/禁用检查
  → 7. 重复调用检测（连续N次同一工具 → 终止）
  → 8. 只读工具缓存命中 → 直接返回
  → 9. asyncio.wait_for 超时控制（读15s/写20s）
  → 10. 返回值截断（保护Agent上下文窗口）
  → 11. 成功 → 写缓存 + 熔断归零；失败 → 降级缓存 + 熔断递增
  → 12. 审计日志（文件+DB）+ Prometheus指标
```

---

## 4. 简历匹配多 Agent

### 4.1 子图结构

```
┌─────────────┐
│ fetch_docs  │ → 从 ChromaDB 获取简历+JD 完整内容
└──────┬──────┘
       │
       ▼ fan-out 并行（LangGraph Send）
┌──────────┐  ┌──────────┐  ┌──────────┐
│tech_agent│  │exp_agent │  │risk_agent│
│ 技术40%  │  │ 经验35%  │  │ 风险25%  │
└────┬─────┘  └────┬─────┘  └────┬─────┘
     └──────────────┼──────────────┘
                    ▼
            ┌──────────────┐
            │  summarize   │ → 加权汇总 + 生成Markdown报告
            └──────────────┘
```

### 4.2 双模式切换

| 模式 | 触发方式 | Prompt | 汇总函数 | 报告内容 |
|------|---------|--------|---------|---------|
| recruiter | "评估候选人"、"匹配度" | TECH_MATCH_PROMPT | summarize_results() | 技术/经验/风险评分 + 匹配度 |
| candidate | "帮我分析"、"怎么准备" | CANDIDATE_TECH_PROMPT | summarize_candidate_results() | 优势/差距/面试准备建议 |

自动识别逻辑：Supervisor 分析自然语言中的候选视角关键词，设置 `match_mode` 状态字段。

### 4.3 加权策略

```
最终得分 = tech_score × 0.40 + exp_score × 0.35 + risk_score × 0.25
```

- 技术匹配 40%：直接影响工作胜任度
- 经验匹配 35%：项目经验反映实际能力
- 风险评估 25%：软性因素补充参考

---

## 5. 工具治理体系

### 5.1 工具注册中心

```python
ToolRegistry:
  register(func, name, permission, category, ...)  # 注册
  list_by_permission(permission)                    # 按权限筛选
  enable(name) / disable(name)                     # 动态启停（持久化 tool_config 表）
  set_permission(name, permission)                  # 在线修改权限级别
  set_version(name, version)                       # 灰度切流
  get_stats()                                      # 统计信息
```

每个工具携带元数据：名称、描述、权限级别（READ_ONLY/READ_WRITE/ADMIN）、分类、参数数量、输入长度限制、输出截断长度、依赖类型。

**工具禁用体系**：
- 全局禁用 → 内存 `ToolMeta.enabled=False` + 持久化 `tool_config` 表（重启不丢失）
- 用户级禁用 → `user_tool_blacklist` 表（用户+工具唯一），管理员页面管理
- 硬拦截 → 每次 Agent 决策前 `bind_tools` 过滤，禁用工具 LLM 完全不可见
- 启动加载 → `main.py` lifespan 从 `tool_config` 表恢复配置

### 5.2 工具清单

| 分类 | 工具 | 权限 | 依赖 |
|------|------|------|------|
| 知识库 (4) | search_knowledge | READ_ONLY | chromadb |
| | upload_knowledge | READ_WRITE | chromadb |
| | get_document_content | READ_ONLY | chromadb |
| | list_knowledge | READ_ONLY | chromadb |
| 备忘录 (6) | add_memo | READ_WRITE | postgresql |
| | list_memos | READ_ONLY | postgresql |
| | complete_memo | READ_WRITE | postgresql |
| | delete_memo | READ_WRITE | postgresql |
| | delete_memos_batch | READ_WRITE | postgresql |
| | update_memo | READ_WRITE | postgresql |
| 邮件 (3) | preview_email | READ_WRITE | smtp |
| | do_send_email | READ_WRITE | smtp |
| | do_send_formatted_email | READ_WRITE | smtp |
| 日期 (4) | get_current_date | READ_ONLY | 无 |
| | get_date_after_days | READ_ONLY | 无 |
| | get_current_datetime | READ_ONLY | 无 |
| | parse_date_range | READ_ONLY | 无 |

> `list_memos` 统一了原来的 `list_memos` + `list_memos_by_date`，支持 keyword / category / status / due_before / due_after / 分页。
> `delete_memos_batch` 默认 `confirmed=False` 仅预览，须 `confirmed=True` 才真删（强制确认）。

### 5.3 熔断器（CircuitBreaker）

```
状态机: CLOSED → (连续失败N次) → OPEN → (超时) → HALF-OPEN → (成功) → CLOSED

配置: AGENT_CIRCUIT_BREAKER_THRESHOLD=5, AGENT_CIRCUIT_BREAKER_TIMEOUT=60s
```

- 每个工具独立熔断器，互不影响
- 超时后自动半开，允许一次试探性调用
- 成功后熔断归零，失败后重新计时

### 5.4 三层限流

| 层次 | 维度 | 示例 | 实现 |
|------|------|------|------|
| 第1层 | 单用户单工具 | send_email 3次/分 | Redis EVALSHA |
| 第2层 | 工具全局 | chroma_ops 200次/分 | Redis EVALSHA |
| 第3层 | 单用户总量 | 60次/分 | Redis EVALSHA |

全部通过才放行，使用 Redis Lua 脚本保证原子性。

---

## 6. 记忆体系

### 6.1 三层架构

```
┌──────────────────────────────────────────────┐
│              短期记忆（Redis）                  │
│  TTL 24h | 按 user_id:session_id 隔离          │
│  原文窗口(最近20条) + 结构化事实摘要(LLM提取)     │
│  压缩策略: 超12条 → LLM提取事实 → 增量合并        │
└──────────────────────────────────────────────┘
                      │
                      ▼ 每8轮对话触发萃取
┌──────────────────────────────────────────────┐
│             长期记忆（PG + ChromaDB）           │
│  PostgreSQL: user_profile 表（JSONB 偏好+事实） │
│  ChromaDB: 语义事实（向量化 → 相似度检索）        │
│  跨会话持久化，用户画像随对话不断丰富             │
└──────────────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────┐
│             会话管理（Redis）                    │
│  列出所有会话 | 标题管理 | 删除会话 | 元数据      │
│  TTL 过期自动清理                               │
└──────────────────────────────────────────────┘
```

### 6.2 结构化压缩

```
旧消息（超窗口）
  → LLM 提取（qwen-turbo, temperature=0）
  → 格式: [{"action":"操作类型","entity":"对象","detail":"细节","importance":"critical|important|normal"}]
  → 增量合并: 按 action+entity 去重，保留更高 importance
  → 排序: critical > important > normal
  → 上限 30 条
```

### 6.3 历史注入格式

```
[以下是历史操作事实摘要]
  ★ [创建备忘录] task1 — 明天开会 (critical)
  ● [查询知识] Python — 查异步编程 (important)
  · [获取日期] 2026-08-01 — 查询 (normal)
[摘要结束]

[以下是最近几轮对话记录]
用户: xxx
助手: xxx
[最近对话记录结束]

[系统信息] 当前用户ID: u12345678
```

---

## 7. 安全防护

### 7.1 PII 脱敏

在输出流中实时替换，覆盖5种敏感信息：

| 类型 | 正则 | 替换为 |
|------|------|--------|
| 邮箱 | `[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}` | `[邮箱地址已隐藏]` |
| 手机号 | `1[3-9]\d{9}` | `[手机号已隐藏]` |
| 身份证 | `\d{17}[\dXx]` | `[身份证号已隐藏]` |
| IP | `\b(?:\d{1,3}\.){3}\d{1,3}\b` | `[IP已隐藏]` |
| API Key | `sk-[a-zA-Z0-9]{20,}` | `[API_KEY已隐藏]` |

### 7.2 Prompt 注入防御

双向防护：
- **输入侧**：`sanitize_user_input()` — 11 条中英文注入模式匹配，命中则追加防御性后缀
- **输出侧**：`sanitize_output()` — 3 条系统提示词泄漏模式匹配，命中则替换为 `[系统信息已隐藏]`

### 7.3 系统提示词泄漏检测

Agent 回复中检测：
- `"你是智能助理.*Smart Assistant"`
- `"##\s*(可用工具|核心规则|安全规则)"`
- `"system.?prompt"`

命中则自动替换，防止通过对话诱导泄漏系统 Prompt。

### 7.4 角色权限系统

| 级别 | 可访问工具 | 典型角色 |
|------|-----------|---------|
| READ_ONLY | 查询类工具 | 管理员可单独限制 |
| READ_WRITE | 查询+写入 | 登录用户（默认） |
| ADMIN | 全部+管理 | 管理员 |

**角色管理**：
- `User.roles` 字段（逗号分隔，如 `"admin,READ_WRITE"`），兼容 `ROLE_ADMIN` 标识
- 前端 `isAdmin` 控制侧边栏菜单可见性（用户管理/工具管理/审计日志/记忆管理仅管理员可见）
- 路由守卫 `requiresAdmin` 拦截非管理员直接 URL 访问
- 后端 `require_admin` FastAPI 依赖拦截非管理员 API 调用

**管理员数据可见性**：
- 知识库/备忘录/Token 统计 — 管理员自动查看全部用户数据
- 审计日志 — 管理员查看全部用户 + 显示 user_name（昵称优先）
- 记忆管理 — 管理员扫描全部用户 Redis 会话 + 长期记忆，详情带 owner_user_id

---

## 8. 可观测性

### 8.1 三层体系

```
LangFuse 链路追踪
  ├─ 每个 LLM 调用：输入/输出/token/耗时
  ├─ 每个 Agent 节点：tech_agent/exp_agent/risk_agent
  └─ 工具调用链：tool_name → input → output → duration

Prometheus 指标（GET /metrics）
  ├─ assistant_tool_calls_total          # 工具调用计数（按名称/结果）
  ├─ assistant_tool_call_duration_seconds # 工具耗时分布
  ├─ assistant_tool_active_calls          # 当前活跃调用
  ├─ assistant_tool_rate_limit_hits_total # 限流命中次数
  ├─ assistant_tool_health_status         # 依赖健康状态
  ├─ assistant_memory_*                  # 记忆操作指标
  └─ assistant_match_*                   # 匹配评估指标

结构化日志（4文件分级）
  ├─ console  → 开发可读格式（彩色）
  ├─ app.log  → 全量JSON，按天轮转+gzip，30天
  ├─ error.log→ 仅ERROR+，独立告警文件，90天
  └─ access.log→ API请求日志，14天
```

### 8.2 指标含义速查

| 指标 | 说明 |
|------|------|
| tool_calls_total | 按 tool_name×category×permission×result 四维标签统计调用成功率 |
| tool_call_duration_seconds | P50/P95/P99 耗时分布，识别慢工具 |
| rate_limit_hits_total | 按 tool_name×layer 标签统计限流触发频率 |
| match_agent_duration_seconds | 按 tech/exp/risk 标签统计各维度评估耗时 |

---

## 9. 韧性设计

### 9.1 多层防护总览

```
请求入口
  │
  ├─ API全局限流（3层）
  │     ├─ 路径级: /chat 20次/分
  │     ├─ IP级: 60次/分
  │     └─ 用户级: 120次/分
  │
  ├─ 工具限流（3层）
  │     ├─ 单用户单工具
  │     ├─ 工具全局
  │     └─ 用户总量
  │
  ├─ 熔断器
  │     └─ 连续失败5次 → 打开60s → 半开试探
  │
  ├─ 超时控制
  │     ├─ 读工具 15s
  │     └─ 写工具 20s
  │
  └─ 降级策略
        ├─ 缓存命中 → 直接返回
        ├─ 依赖不健康 → 过期缓存兜底
        └─ DB写入失败 → SQLite死信队列 → 定期重试
```

### 9.2 工具降级缓存

```python
class ToolCache:
    def get(self, key):        # 正常获取（过期返回None）
    def get_fallback(self, key): # 降级获取（过期也返回，兜底用）
    def put(self, key, value):  # 写入（TTL 2分钟）
```

两种命中场景：
- **正常命中**：缓存有效 → 直接返回，不调工具
- **降级命中**：工具超时/异常/依赖不健康 → 返回过期缓存 + 提示

### 9.3 死信队列

Token 写入主 PostgreSQL 失败时：
1. 记录到 SQLite 死信队列（`dead_letter` 表）
2. 后台任务每 60 秒重试写入主库
3. 重试超过 3 次放弃
4. `/health/ready` 暴露待处理数量

---

## 10. 成本控制

### 10.1 模型分层

| 场景 | 模型 | 温度 | 原因 |
|------|------|------|------|
| 通用对话 | qwen-plus | 0.3 | 需要创造性 |
| 意图分类 | qwen-turbo | 0 | 确定性输出，轻量模型降成本 |
| 事实提取 | qwen-turbo | 0 | 结构化输出，低频调用 |
| 简历评估 | qwen-plus | 0 | 评分可复现 |
| Embedding | text-embedding-v3 | — | DashScope API，按量计费 |

### 10.2 9 模型定价

| 模型 | 输入/千token | 输出/千token |
|------|-------------|-------------|
| qwen-plus | ¥0.0008 | ¥0.002 |
| qwen-max | ¥0.012 | ¥0.012 |
| qwen-turbo | ¥0.0008 | ¥0.002 |
| text-embedding-v3 | ¥0.0007 | ¥0 |
| gpt-4o | ¥0.018 | ¥0.072 |
| claude-3.5-sonnet | ¥0.0216 | ¥0.108 |
| ollama 本地 | ¥0.00001 | ¥0.00001 |

### 10.3 缓存折扣

```
成本 = 输入token/1000 × 输入单价 × 折扣系数 + 输出token/1000 × 输出单价

折扣:
  - 缓存命中：输入单价 × 0.1（TOKEN_CACHE_READ_DISCOUNT）
  - 缓存写入：输入单价 × 1.25（TOKEN_CACHE_WRITE_PREMIUM）

配额:
  - 每日 Token 上限：500,000
  - 每日费用上限：¥10
  - 阈值告警：80%（可配 Webhook）
```

---

## 11. 前端架构

### 11.1 技术选型

```
Vue 3 + Element Plus + Pinia + Vue Router (Hash模式)
  ├─ Chat.vue       → SSE 流式对话 + 思考过程可视化
  ├─ Knowledge.vue  → 文件上传/列表/删除
  ├─ Memo.vue       → 备忘录 CRUD + AI 分类
  ├─ Memory.vue     → 会话记忆 + 长期记忆管理（管理员全部用户视角）
  ├─ TokenStatistics.vue → Token 用量图表（管理员全部用户汇总）
  ├─ ToolManagement.vue  → 工具启用/禁用 + 权限级别修改 + 持久化
  ├─ UserManagement.vue  → 用户列表 + 按用户工具权限配置（管理员专属）
  ├─ AuditLogs.vue  → 审计日志查询（管理员全部用户 + 显示用户名）
  └─ Profile.vue    → 个人资料 + 密码修改
```

### 11.2 SSE 流式通信

```javascript
// 前端 fetch + ReadableStream.getReader() 逐行解析
const response = await fetch('/api/v1/chat', { method: 'POST', body })
const reader = response.body.getReader()
while (true) {
  const { done, value } = await reader.read()
  // 逐行解析 JSON 编码的 chunk
}
```

后端 `json.dumps(chunk)` 编码保护换行格式，前端 `JSON.parse` 还原。

### 11.3 黑暗模式

```
:root 定义亮色 CSS 变量 → html.dark 覆盖为暗色
  + Element Plus CSS变量覆盖（--el-bg-color、--el-fill-color-blank等）
  + 所有组件（表格/输入框/下拉/对话框/日期）完整适配
  + 跟随系统偏好 + 手动切换 + localStorage 持久化
```

---

## 12. 数据模型

### 12.1 PostgreSQL 核心表

| 表名 | 用途 | 关键字段 |
|------|------|---------|
| user_info | 用户 | user_id, username, password(bcrypt), roles, status |
| memo | 备忘录 | user_id, title, content, category, due_date, status |
| ai_token_usage | Token记录 | trace_id, user_id, model_name, input/output_tokens, cost |
| tool_audit_log | 审计日志 | trace_id, user_id, tool_name, tool_input/output, duration_ms, result |
| user_tool_blacklist | 用户工具黑名单 | user_id, tool_name, created_at |
| tool_config | 工具配置持久化 | tool_name, enabled, updated_at |
| user_profile | 用户画像 | user_id, preferences(JSONB), key_facts(JSONB) |
| knowledge_file | 知识库 | user_id, file_name, chunk_count, status |

### 12.2 Redis Key 设计

| Key Pattern | 用途 | TTL |
|-------------|------|-----|
| `token:{userId}` | JWT 白名单 | 24h |
| `mem:msg:{userId}:{sessionId}` | 短期记忆消息 | 24h |
| `mem:sum:{userId}:{sessionId}` | 结构化摘要 | 24h |
| `mem:meta:{userId}` | 会话元数据 | 24h |
| `ratelimit:user_tool:{userId}:{tool}:minute` | 工具用户限流 | 60s |
| `apirate:path:{path}:{ip}:minute` | API 路径限流 | 60s |

### 12.3 ChromaDB Collection

```
Collection: knowledge_{user_id}
  ├─ embedding: text-embedding-v3 (DashScope API)
  ├─ metadata: { source, user_id, version, active, upload_time, chunk_index, section }
  └─ 按 filename 分组管理
```

---

## 13. 部署

详细步骤见 [README.md](../README.md#快速启动) 和 `docker-compose.yml`。

```
nginx (:80) → frontend + app (:8000) → postgres + redis + chromadb
```

- **生产**：`docker compose up -d`，4 容器 + 健康检查依赖链
- **开发**：`uvicorn --reload` + `npm run dev`，无需 Docker