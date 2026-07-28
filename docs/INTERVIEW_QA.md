# 面试追问预测 & 回答要点

## 1. "为什么从 Java 迁移到 Python 做这个项目？"

**回答要点：**

- **生态优势**：Python 是 AI/LLM 开发的事实标准语言。LangChain、LangGraph 等框架在 Python 生态中最为成熟，而 Java 的 Spring AI Alibaba 框架版本还不够稳定（依赖 Spring Boot 3.5），社区文档和示例远不如 Python 丰富
- **开发效率**：同样的 Agent 工作流逻辑，Python（LangGraph）代码量约为 Java（Spring AI Alibaba）的 40%。例如 System Prompt 定义、工具注册、流式处理等场景，Python 的代码更简洁直观
- **技术验证**：LangGraph 的 StateGraph 模型天然支持子图封装、条件路由、人工中断等高级 Agent 模式，这些在 Java 版中需要大量样板代码
- **团队技能**：AI 团队通常以 Python 为主要语言，Python 版本更易于协作维护

> 补充：不是"Java 不好"，而是 AI Agent 开发场景下 Python 生态更合适。对于传统微服务、高并发交易系统，Java/Spring 仍然是更好的选择。

---

## 2. "简历匹配为什么用多智能体而不是工作流？"

**回答要点：**

- **三个维度互不依赖**：技术匹配、经验匹配、风险评估是三个独立的评估角度，分析的是同一份简历和 JD 的不同方面，没有先后依赖关系
- **并行化收益**：使用 `asyncio.gather` 并行执行，总耗时 ≈ max(单 Agent 耗时) ≈ 10-15 秒，串行则需要 30-45 秒
- **专业化 Prompt**：每个 Agent 有独立的 System Prompt 和评估标准：
  - TechMatchAgent（技术面试官视角）：逐技能比对
  - ExpMatchAgent（业务负责人视角）：行业/项目规模匹配
  - RiskAssessAgent（HR 视角）：职业稳定性
- **可扩展**：将来增加新的评估维度（如"文化匹配 Agent"、"薪资匹配 Agent"），只需新增 Agent + 调整权重，不修改现有逻辑
- **对比纯工作流**：如果用工作流（步骤1→2→3），每个步骤是固定的 prompt 模板，缺乏 Agent 的灵活推理能力

---

## 3. "三个 Agent 并行，如何保证结果一致性？"

**回答要点：**

- **temperature=0**：所有评估 Agent 使用 temperature=0，确保相同输入产生确定性输出。这是评分场景的关键配置
- **相同的输入**：三个 Agent 接收完全相同的简历文本和 JD 文本，信息对称
- **统一的评分标准**：每个 Agent 的 System Prompt 中明确规定了 1-10 分的评分细则，汇总层使用统一的加权公式
- **JSON 输出约束**：每个 Agent 被要求输出结构化 JSON（`{"score": N, "reason": "...", ...}`），便于程序解析和汇总
- **可重现性验证**：同一份简历+JD 多次运行，评分误差应 <0.5 分

---

## 4. "如果两个 Agent 评分差异很大，如何处理？"

**回答要点：**

- **差异本身有价值**：技术 9 分 + 经验 2 分 → "技术很强但方向不匹配"，这正是多 Agent 设计想要揭示的信息。如果只有一个综合评估，这个重要洞察会被掩盖
- **不做强制对齐**：三个维度独立展示，让决策者（HR/面试官）看到完整图景，而非抹平差异
- **报告中的体现**：
  - 各维度独立评分 + 详细理由
  - 综合评分给出加权平均
  - 建议部分指出各维度的强项和短板
- **异常处理**：如果某 Agent 返回 `error`（LLM 调用失败），汇总函数仍有优雅降级，使用默认评分 5 分，并在报告中标注

---

## 5. "Token 计费模块如何保证数据不丢失？"

**回答要点：**

- **主库优先写入**：Token 记录首先写入 PostgreSQL 主库
- **死信队列兜底**：主库写入失败时（如连接断开），记录自动保存到本地 SQLite 死信队列
- **定期重试**：后台任务定期从 SQLite 读取待重试记录，重新写入 PostgreSQL，成功后删除
- **重试策略**：每条记录最多重试 3 次，超过后保留在 SQLite 中等待人工处理
- **可观测性**：`GET /health/ready` 返回 `dead_letter_pending` 数量，`GET /admin/dead-letter/count` 可查询详细状态
- **对比 Java 版**：Java 使用 RabbitMQ + DLQ 实现异步消费，Python 版简化为内嵌容错（无需中间件依赖），可靠性相当

---

## 6. "企业级加固具体体现在哪些地方？"

**回答要点：**

### 可靠性
- **熔断器**：连续 5 次失败 → 打开熔断 60 秒，防止级联故障
- **降级缓存**：工具结果 TTL 缓存，失败时返回过期缓存兜底
- **超时控制**：查询 15 秒、写入 20 秒，防止工具调用阻塞 Agent
- **重复调用检测**：同一工具连续 ≥3 次 → 终止 Agent
- **优雅关闭**：FastAPI lifespan 处理 SIGTERM，等待现有请求完成

### 安全性
- **Prompt Injection 防御**：12 组中英文正则 + 防御提示词追加
- **PII 脱敏**：SSE 输出中自动替换邮箱/手机号/身份证/IP/API Key
- **系统提示词泄漏检测**：输出中监测并隐藏系统提示词片段

### 可观测性
- **结构化日志**：loguru JSON 格式，含 request_id/user_id/session_id
- **Prometheus 指标**：/metrics 端点暴露请求量、延迟、错误率
- **审计日志**：每次工具调用记录到 tool_audit_log 表，可查询追溯
- **Token 统计**：按模型/按日期/汇总多维统计

### 运维
- **K8s 探针分离**：/health/live（存活）+ /health/ready（就绪）
- **健康检查**：就绪探针检测 ChromaDB、PostgreSQL、LLM 连通性
- **日志级别热更新**：PUT /admin/log-level 无需重启
- **数据清理**：cron 定期清理过期审计日志和 Token 记录
- **ChromaDB 备份**：导出 collection 到 JSON 文件
