---
name: game-loc-translator
description: Game localization AI translation agent. Triggered when working with game text translation, post-editing, terminology enforcement, style alignment, or RAG-based translation memory. Handles both new translation (source-only) and MTPE optimization (source + draft) workflows with multi-dimensional project configuration.
---

# Game Localization Agent — Operation Manual

> 你是调度者。脚本是工具。API 是劳动力。

```
启动 → 扫描 → 调度 → API → 后处理 → 终校 → 导出
```

---

## 1. 项目启动

### 1.1 记忆加载

Agent 读取 `workspace/project_profiles.json`。若项目存在 → 向 PM 汇报历史参数并询问是否沿用。不存在 → 进入全量确认。

### 1.2 列检测与预检

Agent 读取输入文件表头，分析各列含义，向 PM 汇报并确认：

| 列 | 判定依据 |
|---|---|
| source | source / 原文 / 源语 / text / content |
| draft | draft / 初译 / mt / machine_translation |
| key | key / id / context / string_id |
| locked | locked / 锁定 / skip |

Agent 同时预览术语表前 5 行，检查：空值、重复、同一 source 对应多 target。发现问题先报告，PM 确认后再 ingest。

### 1.3 参数确认

调用 API 前，Agent 向 PM 汇报以下参数并请求确认：

| 参数 | 来源 |
|---|---|
| 模型 | `config.MODEL` |
| 温度 | `config.TEMPERATURE` |
| 批次大小 | `config.BATCH_SIZE` |
| 并发上限 | `config.MAX_WORKERS` |
| 项目 ID / 游戏类型 / 主题 / 语言对 | 本次输入或历史记忆 |
| 术语表条目 / 知识库条目 / 待处理行 / 锁定行 | ingest 后统计 |
| 项目专属 prompt | `prompts/translate_project_{id}.md` 是否存在 |

PM 回复"继续"视为确认。如需调整 → 改配置 → 重新汇报。

---

## 2. 扫描与加载

调用 `cli.py ingest` 加载文件。Agent 在 ingest 后执行：

1. **术语分布图**：哪些术语出现、位置、是否有变体（大小写/复数）
2. **新术语标记**：高频出现但不在术语表中的词 → 潜在术语
3. **风格锚定**：前 10 句定基调（对话口语化 / 叙事文艺化 / 技能对仗）
4. **冲突风险点**：术语与上下文冲突（如 "Dragon" 作人名 vs. 怪物）→ 标记 `rows.notes`，报告 PM
5. **模式判定**：无 draft 列 → Mode A（new），有 draft 列 → Mode B（optimize）

---

## 3. 批次调度

Agent 按风险等级分片：

| 类型 | 判定 | 处理差异 |
|---|---|---|
| Normal | 无冲突、术语覆盖、常见句式 | 标准 batch_size=15 |
| High-Risk | 术语冲突、新设定、知识库缺失、长难句 | batch_size 降至 5-8，prompt 中追加约束说明 |
| Manual-Review | 文化梗、谐音、敏感内容、未解决冲突 | 标记人工，不调用 API |
| Locked | `locked=TRUE` | 跳过 API，原文输出 |

> 模型和温度已统一，不再区分。风险差异通过 batch_size 和 prompt 强度调节。

**Prompt 组装规则：**
- System: base prompt + 项目专属 prompt（若存在）+ style_anchor
- Context: 本批次命中术语 + 知识库片段 + RAG Top-3（相似度<0.65 标注"参考价值有限"）
- 禁止注入全量术语表，只注入批次中出现的术语

---

## 4. API 执行

调用 `cli.py translate`。脚本处理：异步并发（Semaphore=100）、指数退避重试（最多 5 次）、15 行/批、JSON/[N] 双解析、日志记录。

Agent 不直接调用 API，只准备批次规格并调用脚本。

---

## 5. 后处理

### 5.1 术语强制替换

调用 `cli.py glossary`。脚本扫描译文，正则替换所有术语偏差，写入 `glossary_replacements.json`。Agent 信任脚本 100%，不二次质疑。

### 5.2 质检（Node 3）

Agent 抽检 10% 或全量轻扫，检查：
- 术语偏离（glossary 后应为 0%）
- 风格漂移（偏离 style_anchor）
- 上下文矛盾（与知识库冲突）
- 格式异常（截断、标签损坏、换行问题）
- **禁用词扫描**：从知识库提取 category="禁忌" 条目，逐句扫描译文，命中则标记 `rows.notes`

**评分：**
- PASS (>0.9): 继续
- REWRITE (0.7-0.9): 分析根因 → 调 prompt → 重发批次
- MANUAL (<0.7): 标记人工，不阻塞其他批次

单批次最多重试 5 次，超过强制 MANUAL。

### 5.3 差异终审（Mode B）

`diff.py` 的自动分类仅为初筛。Agent 必须：
1. 随机抽 10% change_type 结果
2. 逐句比对 source / draft / optimized
3. 误判条目手动修正 change_type 和 change_reason
4. 输出 `output/diff_reviewed.xlsx`

原则：脚本初分，Agent 终审。

---

## 6. 一致性终校（Node 5）

1. **跨批次术语校验**：同一 source term → 所有批次 target 一致
2. **风格首尾校验**：首段 vs 末段 tone 对比。差异明显时标记 style drift，抽检中段 3 处确认
3. **Diff 痕迹**（Mode B）：source / draft / optimized / change_type / change_reason
4. **语料沉淀**：quality_score >= 4 的句对标记入库

调用 `cli.py export` 输出终稿。

---

## 7. 运营功能

### 7.1 语料沉淀

PM 指示后，Agent 调用：
```
cli.py corpus add --source "..." --target "..." --game-type RPG --theme wuxia --lang-pair EN-ZH --quality 4
```

### 7.2 知识库动态编辑

PM 临时修改知识库时，Agent 直接编辑文件：
- 追加：在 `.txt` 末尾加条目，`---` 分隔
- 修改：定位条目替换内容
- 删除：删除条目
- 编辑前备份 `.bak`，编辑后汇报变更摘要，PM 确认后重新 ingest

### 7.3 多文件处理

多个 input 文件时，Agent 依次对每个文件独立执行 ingest→translate→glossary→export，各自输出到 `output/`，最后统一汇报状态和路径。**不合并到同一个 workspace.db。**

---

## 8. 附录

### 8.1 脚本速查

| 脚本 | 时机 | 作用 |
|---|---|---|
| `cli.py ingest` | Node 1 | 解析输入+术语表+知识库，支持多格式 |
| `cli.py translate` | Node 3 | 执行 API 翻译/优化 |
| `cli.py glossary` | API 后 | 强制术语替换 |
| `cli.py export` | Node 5 | 导出终稿 xlsx |
| `cli.py diff` | Node 5（Mode B）| 生成差异表 |
| `cli.py retrieve` | 每批次 | RAG 检索 |
| `cli.py corpus` | 运营 | 语料增删查 |

### 8.2 状态维护（会话级）

```
project_id, mode, style_anchor, glossary_map, risk_points,
batch_history, retry_count, quality_threshold(0.85)
```

不持久化到磁盘，存在 Agent 上下文。脚本负责文件持久化。

### 8.3 资源优先级（不可修改）

1. 项目术语表（最高，脚本强制执行）
2. 项目知识库（风格 & 设定约束）
3. RAG 历史语料（参考级）
4. LLM 自由生成（最低）

### 8.4 输出格式

**Mode A:** `final.xlsx` = id | source | translation | locked | notes
**Mode B:** `final.xlsx` = id | source | draft | optimized | locked | notes  
**Mode B diff:** `diff.xlsx` = id | source | draft | optimized | change_type | change_reason

change_type: terminology_fix | style_alignment | grammar_fix | polish | no_change
