# 简历匹配工作流

## 概述

基于 LangGraph 多 Agent 架构的简历与 JD 智能匹配系统，支持**招聘方视角**和**候选人视角**两种模式，通过 Supervisor 自然语言自动识别切换。

Supervisor 根据用户消息关键词判断模式：
- 招聘方（"评估候选人"、"匹配度怎么样"）→ 岗位匹配度评估报告
- 候选人（"帮我分析"、"怎么准备"、"我适合吗"）→ 面试准备报告

## 架构

```
用户消息
  │
  ▼
Supervisor（意图分类 + 模式识别）
  │
  ├── general ──▶ ReAct 工作流（通用对话）
  │
  └── match ──▶ 简历匹配子图
                  │
                  ▼
              fetch_docs（从向量库读取简历+JD全文）
                  │
                  ▼
              ┌─ tech_agent  ─┐
              ├─ exp_agent   ─┤  三个 Agent 并行执行
              └─ risk_agent  ─┘
                  │
                  ▼
              summarize（加权汇总 + 生成报告）
```

## 核心组件

### Supervisor (`src/agents/supervisor.py`)

| 职责 | 说明 |
|------|------|
| 快速关键词匹配 | 先做本地关键词过滤，命中才调 LLM 精确分类 |
| LLM 意图分类 | 判断 intent（match/general）和 match_mode（recruiter/candidate） |
| 信息提取 | 从用户消息中提取 resume_file、jd_text 等参数 |

**关键词列表**：`匹配`、`简历`、`岗位`、`评估`、`候选人`、`面试`、`帮我分析`、`怎么准备` 等

### 三个评估 Agent (`src/agents/match_agents.py`)

每个 Agent 输入完整简历文本 + JD 文本，输出结构化 JSON。

#### 招聘方视角

| Agent | 角色 | 输出字段 |
|-------|------|---------|
| tech_agent | 资深技术面试官 | `score`, `reason`, `matched_skills`, `missing_skills` |
| exp_agent | 业务负责人 | `score`, `reason`, `highlights`, `gaps` |
| risk_agent | HR | `score`, `reason`, `risks`, `notes` |

**汇总**：`summarize_results()` — 加权平均（技术 40%、经验 35%、风险 25%），生成 Markdown 评估报告。

#### 候选人视角

| Agent | 角色 | 输出字段 |
|-------|------|---------|
| tech_agent | 技术导师 | `score`, `reason`, `strengths`, `weaknesses`, `preparation_tips` |
| exp_agent | 职业规划师 | `score`, `reason`, `highlight_projects`, `gap_strategies`, `star_examples` |
| risk_agent | HR 面试教练 | `score`, `reason`, `risks`, `response_strategies`, `overall_advice` |

**汇总**：`summarize_candidate_results()` — 加权平均，生成 `面试准备报告`。

### 工作流 (`src/workflows/match_workflow.py`)

| 节点 | 说明 |
|------|------|
| `fetch_docs` | 从 ChromaDB 向量库读取简历和 JD 完整文本 |
| `tech_agent` / `exp_agent` / `risk_agent` | LangGraph `Send` fan-out 并行评估 |
| `summarize` | 收集三个 Agent 结果，根据 `match_mode` 调用不同汇总函数 |

### 流式输出 (`src/api/routes/chat.py`)

| 机制 | 说明 |
|------|------|
| 报告流式 | `summarize` 完成后，按行逐行 SSE 发送，~25 行/秒 |
| JSON 编码 | `json.dumps()` 保护换行格式，前端 `JSON.parse` 还原 |
| 重复过滤 | `match_depth` 嵌套计数器，只取最外层 `on_chain_end` |

## 数据流

```
用户输入
  ├── resume_filename（知识库中的简历文件名）
  └── jd_text（JD 文本或文件名）

fetch_docs
  ├── ChromaDB.get_by_filename(user_id, resume_filename)
  └── ChromaDB.get_by_filename(user_id, jd_filename)  或直接使用粘贴文本

各 Agent
  ├── System Prompt（根据 match_mode 选择）
  ├── resume_text（完整简历文本，几千字）
  ├── jd_text（完整 JD 文本）
  └── 输出：结构化 JSON

summarize
  ├── 三组 JSON → 加权平均计算总分
  ├── 调用 summarize_results() 或 summarize_candidate_results()
  └── 输出：Markdown 报告字符串
```

## 耗时分析（参考值，基于 qwen-plus）

| 步骤 | 耗时 | 备注 |
|------|------|------|
| Supervisor 分类 | ~2s | 一次 LLM 调用 |
| fetch_docs | ~1s | ChromaDB 查询 |
| 三 Agent 并行 | ~20s | 每个 Agent 处理完整文本（数千字输入 + JSON 输出），取最慢者 |
| summarize | <1s | 纯字符串操作 |
| **总计** | **~25s** | |

### 优化方向

1. **缩短输入** — 对简历/JD 做摘要后评估，可省 40-50% token 和时间
2. **换更快模型** — 评分场景可换 `qwen-turbo`
3. **增量反馈** — 已完成但已回退（体验不佳）

## 文件清单

```
backend/src/
├── agents/
│   ├── supervisor.py          # 意图分类 + 模式识别
│   └── match_agents.py        # 6 组 Prompt + 2 个汇总函数
├── workflows/
│   ├── supervisor_workflow.py # 顶层路由图
│   └── match_workflow.py      # 匹配子图（fan-out 并行）
├── models/
│   └── state.py               # AgentState（含 match_mode 字段）
└── api/routes/
    └── chat.py                # SSE 流式输出
```

## 兼容性说明

- 向后兼容：`match_mode` 默认为 `"recruiter"`，旧版 Superisor 返回的结果不受影响
- 前端无需改动：两种模式均通过同一 SSE `/api/v1/chat` 端点流式输出
- 无配置文件变更：`AgentState` 新增字段有默认值
