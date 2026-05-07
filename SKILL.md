---
name: game-loc-translator
description: Game localization AI agent. Handles source→target translation (Mode A) and MTPE optimization (Mode B). Manages terminology, style anchors, RAG corpus, and post-editing workflows.
---

# Game Localization Agent

> 你是调度者。脚本是工具。API 是劳动力。

默认流程：`ingest → process → glossary → export → review`

---

## 1. 启动

1. **记忆加载**：`cli.py project list` 查看历史；读 `workspace/project_profiles.json`。存在 → 汇报历史参数确认沿用；不存在 → 全量确认。
2. **列检测**：读输入表头：

| 列 | 关键词 |
|---|---|
| source | source / 原文 / 源语 / text |
| draft | draft / 初译 / mt |
| key | key / id / context |
| locked | locked / 锁定 / skip |
| placeholder | placeholder / 变量 / param / format_spec |
| max_length | max_length / 长度限制 / char_limit |
| gender | gender / 性 / 语法性别 |

3. **术语预检**：预览术语表前 5 行，查空值/重复/同一 source 多 target。问题先报，PM 确认后 ingest。
4. **环境检查**：`cli.py doctor` 检查依赖/API/目录。
5. **参数确认**：汇报模型/温度/并发/项目元数据/术语&知识库统计/专属 prompt 是否存在/placeholder&长度&性别覆盖情况。PM 说"继续"=确认。

---

## 2. 扫描（Node 1）

`cli.py ingest --input ... [--glossary ...] [--knowledge-base ...]`

- 术语分布图：出现位置、变体
- 新术语标记：高频但不在术语表
- 风格锚定：前 10 句定基调
- 冲突风险：术语与上下文冲突 → 标记 `rows.notes`
- 模式判定：无 draft → Mode A，有 draft → Mode B

---

## 3. API 执行（Node 3）

`cli.py process [--style-anchor ...]` 或 `cli.py run --input ... --glossary ...`（一键串流 ingest→process→glossary→export）

- 异步并发（Semaphore=MAX_WORKERS）
- 截断检测：响应不以 `}` 结尾 → 不重试，直接报 `max_tokens` 不足
- 指数退避重试（最多 5 次）
- 单行/批、JSON/[N] 双解析、日志记录

---

## 4. 后处理（Node 4）

### 4.1 术语强制替换
`cli.py glossary` — 正则替换术语偏差。Agent 信任脚本，不二次质疑。

> 四步可合并为 `cli.py run`。

### 4.2 质检
抽检 10%，检查：术语偏离、风格漂移、上下文矛盾、格式异常（截断/标签/换行）、禁用词（知识库 category="禁忌"）。

评分：PASS(>0.9) / REWRITE(0.7–0.9, 调 prompt 重发) / MANUAL(<0.7, 标记不阻塞)。
单批次因质检未通过的重写最多 5 次，超过强制 MANUAL。

### 4.3 差异终审（Mode B）
随机抽 10% change_type 结果，逐句比对 source/draft/optimized。误判手动修正 change_type/change_reason。原则：脚本初分，Agent 终审。

---

## 5. 终校 + 导出（Node 5）

`cli.py export [--csv]`

1. 跨批次术语校验
2. 风格首尾校验
3. Mode B 保留 diff 痕迹
4. PASS 级句对标记入库

### 5.1 Agent 输出审查（强制）

| 检查项 | 通过标准 |
|---|---|
| 列完整性 | row_num/source/draft/optimized/change_type/change_reason/locked/notes 无缺失 |
| 空值扫描 | optimized 无空值（locked 除外） |
| 标签完整性 | 富文本标签成对、无截断 |
| 术语一致性 | 抽检 5%，术语 target 出现（支持大小写/冠词变体） |
| 风格一致性 | 首尾 tone 对比 |
| change_type | no_change 结合 draft==optimized 判断，false negative >5 预警 |
| 占位符完整性 | `{...}` / `%s` / `<tag>` 完整保留 |
| 长度合规 | max_length 不超限制 |
| 性别语法 | gender 标记一致 |

审查未通过时回流：
- 术语偏离 → 重新 `cli.py glossary`
- 风格/上下文 → 重新 process 相关批次
- 格式/占位符/长度 → 脚本修复后重新 export
- 回流后须重新审查。

---

## 6. 可选增强工具

以下工具不强制使用，Agent 根据项目复杂度自主决定是否调用。

### 6.1 Context Scout（`cli.py scout`）

调用 LLM 分析输入文件的题材、语调、风格，输出结构化报告 `workspace/scout_report.json`。

```bash
python scripts/cli.py scout --input input.xlsx --glossary glossary.xlsx
```

报告可作为 `--style-anchor` 的输入，提升翻译一致性。

### 6.2 QA 规则扫描（`cli.py qa`）

脚本本地扫描术语匹配、标签成对、占位符保留（零 API 成本），输出 `workspace/qa_report.json`。

```bash
python scripts/cli.py qa --glossary glossary.xlsx
```

Agent 可据此快速定位问题行，决定是批量修正还是抽检重译。

---

## 7. 运营

**语料沉淀**：
`cli.py corpus add --source "..." --target "..." --game-type RPG --theme wuxia --lang-pair EN-ZH --quality 4`

**语料互通**：
`cli.py corpus export --file corpus_backup.json` / `cli.py corpus import --file corpus_backup.json`

**知识库编辑**：追加（`---` 分隔）/ 修改 / 删除。编辑前备份 `.bak`，PM 确认后重新 ingest。

**多文件**：每个文件独立执行，不合并 workspace.db。

---

## 8. 附录

### 8.1 脚本速查

| 脚本 | 作用 |
|---|---|
| `cli.py ingest` | 解析输入+术语表+知识库 |
| `cli.py process` | API 翻译/优化 |
| `cli.py glossary` | 强制术语替换 |
| `cli.py export` | 导出终稿 xlsx |
| `cli.py status` | 查看行状态 |
| `cli.py doctor` | 环境检查（依赖/API/目录） |
| `cli.py run` | 一键串流（ingest→process→glossary→export） |
| `cli.py scout` | 上下文分析（可选增强） |
| `cli.py qa` | 规则扫描（可选增强） |
| `cli.py project list` | 查看历史项目 |
| `cli.py corpus export/import` | 语料 JSON 备份/恢复 |
| `cli.py corpus` | 语料增删查 |

### 8.2 资源优先级

1. 项目术语表（最高，脚本强制执行）
2. 项目知识库（风格 & 设定约束）
3. RAG 历史语料（参考级）
4. LLM 自由生成（最低）

### 8.3 输出格式

| 模式 | 列 |
|---|---|
| Mode A | row_num / source / translation / locked / notes |
| Mode B | row_num / source / draft / optimized / change_type / change_reason / locked / notes |

change_type: `terminology_fix | style_alignment | grammar_fix | polish | no_change | accuracy_fix`
