# Game Localization Translator

基于 RAG 的游戏本地化 AI 翻译内核模块。支持全新翻译（Mode A）与人工初译优化（Mode B）双模式，具备术语强制约束、知识库风格控制、RAG 语料参考三层资源体系。

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

## 快速开始

### 1. 准备文件

**输入文件（Excel/CSV）：**

Mode A — 纯原文：
```
| id | source                     | key            | locked |
|----|----------------------------|----------------|--------|
| 1  | The Dragon attacks.        | dlg_boss_001   | FALSE  |
```

Mode B — 原文+初译：
```
| id | source                     | draft            | key            | locked |
|----|----------------------------|------------------|----------------|--------|
| 1  | The Dragon attacks.        | 龙发起了攻击。   | dlg_boss_001   | FALSE  |
```

**术语表（Excel/CSV/TXT/JSON/TSV）：**
```
Dragon = 巨龙
Warrior = 战士
```

**知识库（Excel/CSV/TXT/JSON/Markdown）：**
```
world
这片大陆被巨龙统治，人类在边缘生存。
---
style
技能描述使用四字短语，对话口语化。
```

> `locked=TRUE` 的行会直接原样输出，不经过 API。

### 2. 配置 API

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

## 作为 Agent 嵌入使用

本模块设计为 **可被 AI Agent 调用的内核**，不绑定任何前端。Agent（如 Claude Code / Kimi CLI）的角色是：

1. **扫描确认**：读取文件 → 分析列名 → 汇报参数 → 等用户确认
2. **调度执行**：调用 `cli.py` 各命令，监控进度
3. **质检仲裁**：抽检结果，分析失败原因，重试或标记人工
4. **运营沉淀**：筛选优质句对入库，更新知识库

Agent 的行为规范定义在 `SKILL.md` 中。加载方式：
```bash
kimi-cli --skill game-loc-translator
```

---

## 常见问题

**Q：术语表格式不对怎么办？**  
A：支持 `.xlsx` `.csv` `.txt` `.json` `.tsv` 五种格式，Agent 会自动检测并告知解析结果。

**Q：处理到一半断网了怎么办？**  
A：中间结果存在 `workspace/workspace.db` 中，重新执行 `cli.py process` 会从断点继续（pending/failed 行自动恢复）。

**Q：不会用命令行怎么办？**  
A：让 Agent 帮你跑。你只需提供文件路径和项目信息，Agent 自动调用脚本。
