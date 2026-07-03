# Game Localization Translator

中文 | [English](README.md)


**Agent Skill** — 游戏本地化 AI 翻译与 MTPE 内核，基于术语强制约束、风格指南和 RAG 语料参考执行 ZH→目标语言翻译流程。

**Agent Skill** — RAG-based game-localization translation engine for fresh translation and MTPE, with terminology enforcement, style-guide control, and corpus-backed references.

---

## 核心能力

| 能力 | 说明 |
|---|---|
| **双模式翻译** | Mode A 全新翻译 / Mode B 初译优化，自动识别 |
| **术语强制约束** | 独立术语表上传，翻译后自动扫描校准，100% 确定性替换 |
| **知识库风格控制** | 可选上传世界观、角色、禁忌等设定，约束翻译风格 |
| **RAG 语料参考** | 按「游戏类型+题材+语言对」三维分仓检索历史优质译文 |
| **批次调度** | 自动分批次并发处理，支持重试与错误恢复 |
| **差异追踪** | Mode B 输出修改痕迹（change_type + change_reason） |
| **语料沉淀** | 优质句对一键入库，持续反哺后续项目 |

---

## 文件准备指南

本模块无 Web 上传界面。用户只需将文件放到 `input/` 目录（或任意位置），然后向 Agent 提供路径即可。

### 1. 输入文件（待翻译）

放到 `input/` 目录。Agent 自动检测列名。

**Excel 格式（推荐）：**

Mode A — 纯原文：
```
| id | source                     | key            | locked |
|----|----------------------------|----------------|--------|
| 1  | The Dragon attacks.        | dlg_boss_001   | 0      |
```

Mode B — 原文+初译：
```
| id | source                     | draft            | key            | locked |
|----|----------------------------|------------------|----------------|--------|
| 1  | The Dragon attacks.        | 龙发起了攻击。   | dlg_boss_001   | 0      |
```

**自动识别的列名：**

| 列 | 识别关键词 |
|---|---|
| source | `source` / `原文` / `源语` / `text` |
| draft | `draft` / `初译` / `mt` |
| key | `key` / `id` / `context` |
| locked | `locked` / `锁定` / `skip` |
| placeholder | `placeholder` / `变量` / `param` / `format_spec` |
| max_length | `max_length` / `长度限制` / `char_limit` |
| gender | `gender` / `性` / `语法性别` |

> `locked=1/TRUE/是` 的行会直接原样输出，不经过 API。

### 2. 术语表

放到 `input/` 目录。支持多种格式。

**TXT 格式（最简单）：**
```
Dragon = 巨龙
Warrior = 战士
Arcane Crystal = 奥术水晶
HP = 生命值
```
分隔符支持 `=` `\t` `|` `: ` 自动识别。

**Excel/CSV 格式：**
```
| source_term | target_term |
|-------------|-------------|
| Dragon      | 巨龙        |
| Warrior     | 战士        |
```

**JSON 格式：**
```json
[{"source":"Dragon","target":"巨龙"}]
```

### 3. 知识库

放到 `input/` 目录。按 category 组织约束。

**TXT 格式（推荐）：**
```
world
这片大陆被巨龙统治，人类在边缘生存。
---
style
技能描述使用四字短语，对话口语化。
---
禁忌
不得出现"能量""升级"等过于现代化的词汇。
---
角色
主角李青云 — 昆仑派弟子，性格沉稳，自称"在下"
```
用 `---` 分隔区块，首行为 category，后续为 text。

**Excel/CSV 格式：**
```
| category | note | text                                      |
|----------|------|-------------------------------------------|
| 风格     |      | 技能描述使用四字短语，对话口语化。        |
| 禁忌     |      | 不得出现"能量""升级"。                   |
| 角色     | 主角 | 李青云 — 昆仑派弟子，性格沉稳。           |
```

**支持的 category（建议）：**

| category | 作用 | 在流程中的使用位置 |
|---|---|---|
| `禁忌` | 禁用词清单 | process prompt 硬约束 + qa 清单对照 |
| `风格` | 翻译风格要求 | process prompt 风格约束 |
| `设定` | 世界观/背景设定 | process prompt 语境约束 |
| `角色` | 角色名、口癖、称谓 | process prompt 角色约束 |

### 怎么交给 Agent

不需要手动执行命令。直接告诉 Agent：

```
翻译 input/game_text.xlsx，术语表用 input/glossary.txt，知识库用 input/kb.txt。
项目类型 RPG，题材 fantasy，语言对 EN-ZH。
```

Agent 自动调度 ingest-agent → process-agent → qa-agent 完成全流程。

---

## 快速开始

### 1. 配置 API

复制 `.env.example` 为 `.env` 并填入密钥：
```bash
cp .env.example .env
# 编辑 .env
GAME_LOC_API_BASE=https://api.yourservice.com/v1
GAME_LOC_API_KEY=sk-xxx
```

或直接编辑 `scripts/core/config.py`。

### 3. 执行流程

```bash
cd scripts

# Step 1: 环境检查
python cli.py doctor

# Step 2: 加载项目
python cli.py ingest \
  --input ../input/source.xlsx \
  --glossary ../input/glossary.txt \
  --knowledge-base ../input/kb.txt \
  --project-id neoepoch \
  --game-type RPG \
  --theme fantasy \
  --lang-pair EN-ZH

# Step 3: 翻译/优化（单行模式，自动前十行风格锚点）
python cli.py process

# Step 4: 术语强制替换
python cli.py glossary

# Step 5: 导出结果
python cli.py export

# 或一键串流（Step 2-5 合并）
python cli.py run --input ../input/source.xlsx --glossary ../input/glossary.txt
```

输出文件位于 `output/` 目录：
- `source_translated.xlsx` — 终稿
- `source_diff.xlsx` — 修改痕迹（Mode B  only）

---

## 文件格式支持

### 输入文件
| 格式 | 说明 |
|---|---|
| `.xlsx` | 推荐，支持多列自动识别 |
| `.csv` | UTF-8 with BOM |
| `.txt` | 纯文本，每行一句 |

Agent 会自动检测列名（source / draft / key / locked），检测完成后向你汇报确认。

### 术语表
| 格式 | 示例 |
|---|---|
| `.xlsx/.csv` | 两列：source_term / target_term |
| `.txt` | `Dragon = 巨龙`（支持 `=` `\t` `|` `: ` 自动识别） |
| `.json` | `[{"source":"Dragon","target":"巨龙"}]` 或 `{"Dragon":"巨龙"}` |
| `.tsv` | Tab 分隔 |

### 知识库
| 格式 | 示例 |
|---|---|
| `.xlsx/.csv` | 三列：category / note / text |
| `.txt` | 用 `---` 分隔的区块，首行为 category，后续为 text |
| `.json` | `[{"category":"world","note":"","text":"..."}]` |
| `.md` | 整篇 Markdown 作为单条 entry |

---

## 命令参考

| 命令 | 作用 | 常用参数 |
|---|---|---|
| `cli.py ingest` | 解析输入文件，加载术语表、知识库 | `--input` `--glossary` `--knowledge-base` `--project-id` `--game-type` `--theme` `--lang-pair` `--source-col` `--draft-col` `--key-col` `--locked-col` |
| `cli.py process` | 执行翻译/优化 | `--style-anchor` |
| `cli.py glossary` | 术语强制替换 | 无 |
| `cli.py export` | 导出终稿 xlsx | `--csv` |
| `cli.py diff` | 生成 Mode B 修改痕迹 | 无 |
| `cli.py retrieve` | RAG 语料检索 | `--query` `--game-type` `--theme` `--lang-pair` `--top-k` |
| `cli.py corpus` | 语料库管理 | `add/list/import/delete` |

---

## 项目结构

```
game-loc-translator/
├── input/              # 放输入文件
├── output/             # 输出结果
├── workspace/          # 运行时 DB、元数据、日志
│   ├── workspace.db    # SQLite 行数据
│   ├── corpus.db       # RAG 语料库
│   └── project_meta.json
├── logs/               # API 调用日志
├── prompts/
│   ├── translate_base.md      # Mode A 通用 prompt
│   ├── optimize_base.md       # Mode B 通用 prompt
│   └── translate_project_*.md # 项目专属 prompt（可选）
├── scripts/
│   ├── cli.py              # CLI 入口
│   ├── review_output.py    # 输出审查脚本
│   ├── diff_review.py      # 差异终审脚本
│   └── core/
│       ├── config.py       # 配置中心
│       ├── ingest.py       # 文件解析
│       ├── engine.py       # API 引擎、prompt 组装
│       ├── glossary.py     # 术语强制替换
│       ├── export.py       # 结果导出
│       ├── diff.py         # Mode B 差异分析
│       ├── scout.py        # 上下文分析（可选增强）
│       ├── qa.py           # 规则扫描（可选增强）
│       ├── corpus_store.py       # RAG 语料存储
│       ├── corpus_search.py      # RAG 向量检索
│       └── project_memory.py     # 项目记忆持久化
├── requirements.txt    # 依赖清单
├── .env.example        # 环境变量模板
└── .gitignore
```

---

## 存储与数据流

### 五类存储

| # | 存储名 | 类型 | 来源 | 路径 | 说明 |
|---|---|---|---|---|---|
| 1 | **术语表** | 用户文件 | 用户上传 | `input/glossary.*` | 项目专属术语映射，process 阶段加载 |
| 2 | **知识库** | 用户文件 | 用户上传 | `input/kb.*` | 风格/设定/禁忌/角色约束，ingest 解析后 process 加载 |
| 3 | **输入数据** | 用户文件 | 用户上传 | `input/*.xlsx` 等 | 待翻译源文本，ingest 解析后入 workspace.db |
| 4 | **workspace.db** | SQLite | 运行时生成 | `workspace/workspace.db` | 行数据 + 项目元数据（kb_file、术语命中数等） |
| 5 | **corpus.db + corpus.faiss** | SQLite + FAISS | 运行时生成/语料沉淀 | `workspace/corpus.db` / `workspace/corpus.faiss` | RAG 语料存储（文本+向量），`corpus` 命令管理 |

其中 1-3 为**用户提供的项目库**，4-5 为**系统运行时库**。

### 数据流

```
用户上传
  ├── 输入文件 ──→ ingest-agent ──→ workspace.db (rows 表)
  ├── 术语表 ─────→ ingest-agent ──→ workspace meta (glossary_file)
  └── 知识库 ─────→ ingest-agent ──→ workspace meta (kb_file)
                                          │
                                          ↓
                                    process-agent
                                          │
                                          ├─→ 术语表 → glossary_hints → API prompt
                                          ├─→ 知识库 → kb_snippets → API prompt
                                          ├─→ RAG → rag_refs → API prompt (corpus>=10)
                                          └─→ 翻译结果 → workspace.db
                                                            │
                                                            ↓
                                                      glossary 替换
                                                            │
                                                            ↓
                                                      qa-agent
                                                            │
                                                            ├─→ 审查通过 → export → output/
                                                            └─→ 语料沉淀 → corpus.db/.faiss
```

### workspace.db 结构

| 表名 | 内容 |
|---|---|
| `rows` | 待处理/已处理的行数据（id, source, draft, translation, status, notes, locked, key, change_type, change_reason） |
| `project` | 项目元数据（project_id, game_type, theme, lang_pair, kb_file, kb_count, glossary_file, glossary_count, mode） |

### corpus.db 结构

| 表名 | 内容 |
|---|---|
| `corpus` | 历史语料（id, project_id, game_type, theme, lang_pair, source, target, quality_score, created_at） |
| `query_cache` | 嵌入向量缓存（query_key, vector），避免重复编码 |

`corpus.faiss` 为向量索引文件，与 `corpus.db` 通过 `id` 关联。

**当前 corpus 状态**：仅含 1 条测试数据（`cli.py corpus add` 插入），RAG 未生效（`< 10` 条时自动跳过检索）。真实项目沉淀语料后自动启用。

---

## 配置说明

`scripts/core/config.py`：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `MODEL` | `gemini-3.1-pro-preview` | 统一模型 |
| `TEMPERATURE` | `0.3` | 创造性/随机性 |
| `BATCH_SIZE` | `1` | 每批 API 处理行数（单行模式，避免截断） |
| `MAX_WORKERS` | `100` | 并发上限 |
| `MAX_RETRIES` | `5` | API 失败重试次数 |
| `RAG_SIM_THRESHOLD` | `0.65` | RAG 相似度阈值 |
| `RAG_TOP_K` | `3` | RAG 召回条数 |

---

## 资源优先级（不可修改）

1. 自定义项目术语表（最高，强制遵循）
2. 项目题材知识库（次高，风格 & 设定约束）
3. RAG 历史优质语料（参考级，风格 & 译法参考）
4. LLM 自由生成（最低，仅无任何参考时启用）

---

## 多 Agent 架构

本模块采用 **主 Agent 调度 + 子 Agent 执行** 的多 Agent 架构。主 Agent 是纯粹的调度者，禁止直接操作脚本、文件或 API。所有执行动作委派给专用子 Agent。

### Agent 分工

| Agent | 职责 | 独占权限 | 参考手册 |
|---|---|---|---|
| **主 Agent** | 决策、调度、审查回传、终决 | 禁止直接执行任何脚本 | `SKILL.md` |
| **ingest-agent** | 数据解析、列检测、术语预检、环境检查、`ingest`/`scout`、语料运营 | 数据摄入与归档 | `SKILL.md` / `SUB_ingest.md` |
| **process-agent** | API 翻译/优化、`glossary` 术语替换、并发管理、截断重试 | API 调用与术语强制替换 | `SKILL.md` / `SUB_process.md` |
| **qa-agent** | 质检抽检、差异终审（Mode B）、输出审查、`export` 导出、格式修复、RAG 一致性对比 | 质检审查与交付导出 | `SKILL.md` / `SUB_qa.md` |

### 调度流程

```
主 Agent
  │
  ├─→ ingest-agent
  │       ├─→ 启动扫描 / 列检测 / 术语预检
  │       ├─→ cli.py ingest
  │       │   └─→ knowledge_profile.json（知识库结构化输出）
  │       ├─→ cli.py scout（可选）
  │       └─→ 回传参数、异常、知识库统计
  │
  ├─→ process-agent ←── knowledge_profile.json
  │       ├─→ 知识库注入 API prompt（风格/设定/禁忌）
  │       ├─→ RAG 检索 → few-shot（corpus>=10 时自动启用）
  │       ├─→ cli.py process / run
  │       ├─→ cli.py glossary（术语强制替换）
  │       └─→ 回传翻译结果、RAG 命中统计
  │
  ├─→ qa-agent ←── knowledge_profile.json
  │       ├─→ 知识库清单对照审查
  │       ├─→ RAG 一致性对比（cli.py retrieve）
  │       ├─→ 质检抽检 / 差异终审（Mode B）
  │       ├─→ 输出审查（结构化 9 项）
  │       ├─→ cli.py export
  │       └─→ 回传质检结论、导出文件
  │
  └─→ 终决：交付 / 报 PM / 回流
```

### 上下文传递规范

主 Agent 向子 Agent 下发任务时必须携带：
1. 项目标识（workspace 路径、项目名）
2. 当前阶段目标
3. 上游子 Agent 的输出摘要或关键结论
4. 已知风险点（术语冲突、格式约束、max_length 超限历史等）
5. `knowledge_profile_path`：知识库结构化摘要路径
6. `rag_enabled`：当前项目 corpus 是否 >= 10
7. 回传要求：结构化摘要 + 原始输出文件路径 + 异常标记

子 Agent 回传时必须提供：
1. 执行摘要（成功/失败/异常）
2. 关键数据（行数、术语命中数、异常行号、评分）
3. 输出文件路径
4. 下一步建议 / 阻塞项

### 核心机制

**ingest-agent**
- 解析输入后输出 `workspace/knowledge_profile.json`，按 category 分组（禁忌/风格/设定/角色）
- 支持可选 `cli.py scout` 上下文分析
- 语料运营：`cli.py corpus add/export/import`

**process-agent**
- 读取 `knowledge_profile.json`，将 `风格`/`设定`/`角色`/`禁忌` 注入 API system prompt
- 自动 RAG 检索：每行 source 执行 `search_corpus()`（corpus >= 10 时启用），similarity >= 0.65 的命中注入 few-shot
- 术语强制替换 `cli.py glossary` 作为 process 流程的收尾

**qa-agent**
- 自主审查：直接读取数据，用自己的推理能力完成全部审查项
- 知识库清单对照：逐项核对知识库约束执行情况
- RAG 一致性对比：对抽检行执行 `cli.py retrieve`，对比当前输出与历史 approved translation
- 审查通过后执行 `cli.py export`，形成"审查 → 决策 → 交付"闭环

### Skill 文件结构

```
SKILL.md              # 主 Agent 调度手册（禁令、流程图、决策规则）
SUB_ingest.md         # ingest-agent 执行手册
SUB_process.md        # process-agent 执行手册
SUB_qa.md             # qa-agent 执行手册
```

加载方式：
```bash
kimi-cli --skill game-loc-translator
```

主 Agent 调度时读取对应子 Agent 手册，将内容作为上下文注入子 Agent 的 system prompt。

---

## 常见问题

**Q：术语表格式不对怎么办？**  
A：支持 `.xlsx` `.csv` `.txt` `.json` `.tsv` 五种格式，Agent 会自动检测并告知解析结果。

**Q：处理到一半断网了怎么办？**  
A：中间结果存在 `workspace/workspace.db` 中，重新执行 `cli.py process` 会从断点继续（pending/failed 行自动恢复）。

**Q：不会用命令行怎么办？**  
A：让 Agent 帮你跑。你只需提供文件路径和项目信息，Agent 自动调用脚本。
