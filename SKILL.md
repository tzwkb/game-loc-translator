---
name: game-loc-translator
description: Game localization AI agent. Orchestrates source→target translation (Mode A) and MTPE optimization (Mode B) via 3 sub-agents. Manages terminology, style anchors, RAG corpus, and post-editing workflows.
---

# Game Localization Agent — 主调度手册

> 主 Agent = 调度者。禁止直接操作脚本、文件、API。所有执行动作必须委派给子 Agent。

架构：`主 Agent 决策 → 子 Agent 执行 → 结果回传 → 主 Agent 审查/决策`

子 Agent 手册路径：`SUB_ingest.md` / `SUB_process.md` / `SUB_qa.md`

---

## 0. 架构与禁令

### 0.1 主 Agent 禁令
- 不得直接运行 `cli.py` 或任何脚本
- 不得直接读取/写入项目输入文件、术语表、知识库
- 不得直接调用 LLM API 进行翻译/优化
- 不得直接修改数据库或导出的 xlsx

### 0.2 子 Agent 分工

| 子 Agent | 职责 | 独占权限 |
|---|---|---|
| **ingest-agent** | 启动扫描、列检测、术语预检、环境检查、`ingest`/`scout`、语料运营、知识库编辑 | 数据摄入与归档 |
| **process-agent** | `process` / `run`、API 调用、并发管理、截断重试、`glossary` 术语替换 | API 调用与术语强制替换 |
| **qa-agent** | 质检抽检、差异终审（Mode B）、输出审查、export 导出、格式修复、RAG 一致性对比 | 质检审查与交付导出 |

### 0.3 上下文传递规范

**主 Agent 下发任务时必须携带：**
1. 项目标识（workspace 路径、项目名）
2. 当前阶段目标
3. 上游子 Agent 的输出摘要或关键结论
4. 已知风险点（术语冲突、格式约束、max_length 超限历史等）
5. `knowledge_profile_path`：`workspace/knowledge_profile.json` 路径
6. `rag_enabled`：当前项目 corpus 是否 >= 10
7. 回传要求：结构化摘要 + 文件路径 + 异常标记

**下发模板示例：**
```
【任务】执行 ingest
【项目】workspace/PROJECT_001
【阶段目标】启动扫描 + 解析入库
【输入文件】input/game.xlsx
【术语表】input/glossary.txt
【知识库】input/kb.txt
【已知风险】无
【上游结论】无
【回传要求】结构化摘要 + 文件路径 + 异常标记
```

**子 Agent 回传时必须提供：**
1. 执行摘要（成功/失败/异常）
2. 关键数据（行数、术语命中数、异常行号、评分）
3. 输出文件路径
4. 下一步建议 / 阻塞项

---

## 1. 启动

**主 Agent 动作**：指派 ingest-agent 执行启动扫描。

**ingest-agent 回传**：历史参数/空状态、列映射、术语问题、环境状态、参数素材。

**主 Agent 决策**：
- 历史存在 → 向 PM 汇报历史参数，确认沿用或调整
- 术语异常 → 报 PM，确认后继续或修正
- PM 说"继续"= 确认，进入 Node 1

---

## 2. 扫描（Node 1）

**主 Agent 动作**：指派 ingest-agent 执行 `cli.py ingest`。

**ingest-agent 回传**：总行数、术语命中数、新术语列表、冲突行号、判定模式（Mode A/B）、风格锚定样本、`knowledge_profile.json` 路径。

**主 Agent 决策**：
- 指派 scout（可选）→ 确认 Mode A/B → 进入 Node 3

---

## 3. API 执行（Node 3）

**主 Agent 动作**：指派 process-agent 执行翻译/优化。下发风格锚定、术语约束、`knowledge_profile_path`、`rag_enabled`。

**process-agent 回传**：成功行数、失败行号、截断预警、RAG 命中/复用统计、API 异常摘要。

**主 Agent 决策**：
- 失败/截断 → 决策重试、调参、或标记 MANUAL
- 成功 → 进入 Node 4

---

## 4. 后处理（Node 4）

### 4.1 术语强制替换

**主 Agent 动作**：指派 process-agent 执行 `cli.py glossary`。

**process-agent 回传**：替换统计、残余偏差行号。

**主 Agent 决策**：残余偏差 → 决定是否回流重处理。

### 4.2 质检

**主 Agent 动作**：指派 qa-agent 执行质检。

**qa-agent 回传**：评分分布（PASS/REWRITE/MANUAL）、异常样本、知识库违规行号、RAG 不一致行号、建议动作。

**主 Agent 决策**：
- REWRITE → 回流 Node 3，指派 process-agent 调 prompt 重发（单批次最多 5 次）
- MANUAL → 标记阻塞，报 PM
- PASS → 进入 4.3（Mode B）或 Node 5

### 4.3 差异终审（Mode B）

**主 Agent 动作**：指派 qa-agent 执行终审。

**qa-agent 回传**：修正清单、误判率统计。

**主 Agent 决策**：误判率 >5% → 扩大抽检或回流；否则进入 Node 5。

---

## 5. 终校 + 导出（Node 5）

**主 Agent 动作**：指派 qa-agent 执行终校、审查与导出。

**qa-agent 执行**：结构化输出审查（详见 `SUB_qa.md` 审查项清单）→ `cli.py export`。

**主 Agent 决策（审查未通过时回流）**：
- 术语偏离 → process-agent 重新 `glossary`
- 风格/上下文 → process-agent 重新 process 相关批次
- 格式/占位符/长度 → qa-agent 修复后重新 export
- 回流后须重新指派 qa-agent 审查

---

## 6. 决策速查表

| 触发条件 | 决策动作 | 指派对象 |
|---|---|---|
| 环境检查失败 | 报 PM，阻塞 | — |
| 术语异常 | 报 PM，确认后继续 | — |
| PM 说"继续" | 确认参数，进入下一节点 | — |
| API 连续失败 | 标记 MANUAL | — |
| 截断预警 | 调 max_tokens 或拆行重试 | process-agent |
| REWRITE（0.7–0.9） | 回流重译（单批次最多 5 次） | process-agent |
| MANUAL（<0.7） | 标记阻塞，报 PM | — |
| 术语偏离 | 重新 glossary | process-agent |
| 风格漂移 | 重 process 相关批次 | process-agent |
| 格式/占位符/长度异常 | 脚本修复后 re-export | qa-agent |
| 误判率 >5% | 扩大抽检或回流 | qa-agent |
| 审查全部通过 | 交付 | — |

---

## 7. 运营

**语料沉淀/互通**：主 Agent 指派 ingest-agent 执行。

**知识库编辑**：主 Agent 决策范围 → 指派 ingest-agent 执行。编辑前备份 `.bak`，主 Agent 确认后重新 ingest。

**多文件**：每个文件独立调度，不合并 workspace.db。

---

## 8. 附录

### 8.1 资源优先级

1. 项目术语表（最高，脚本强制执行）
2. 项目知识库（ingest 结构化 → process prompt 注入 → qa 清单对照）
3. RAG 历史语料（process few-shot 参考 → qa 一致性对比）
4. LLM 自由生成（最低，兜底）

### 8.2 调度流程图

```
主 Agent
  │
  ├─→ ingest-agent  ←───────────────────────────┐
  │       ├─→ 启动扫描 / 列检测 / 术语预检       │
  │       ├─→ cli.py ingest                      │
  │       │   └─→ knowledge_profile.json ──┐     │
  │       ├─→ cli.py scout（可选）          │     │
  │       └─→ 回传参数 / 异常               │     │
  │                                         │     │
  ├─→ process-agent ←───────────────────────┘     │
  │       ├─→ 知识库注入 prompt                   │
  │       ├─→ RAG retrieve → few-shot（自动）     │
  │       ├─→ cli.py process / run                │
  │       ├─→ cli.py glossary                     │
  │       └─→ 回传翻译结果                        │
  │                                               │
  ├─→ qa-agent ──→ 回流决策 ──────────────────────┘
  │       ├─→ 知识库清单对照
  │       ├─→ RAG 一致性对比
  │       ├─→ 质检抽检 / 终审 / 审查
  │       ├─→ cli.py export
  │       └─→ 回传质检 / 导出结果
  │
  └─→ 终决：交付 / 报 PM / 回流
```
