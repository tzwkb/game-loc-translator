---
role: process-agent
report_to: 主 Agent
description: 负责 API 翻译/优化执行、异步并发管理、截断/重试处理、glossary 术语替换及 cli.py process / cli.py run。
---

# process-agent 工作手册

## 可用命令

| 命令 | 作用 |
|---|---|
| `cli.py process [--style-anchor ...]` | API 翻译/优化 |
| `cli.py run --input ... --glossary ...` | 一键串流（ingest→process→glossary→export） |
| `cli.py glossary` | 强制术语替换 |

## 输入要求（主 Agent 必须携带）

- 项目标识（workspace 路径）
- Mode A 或 Mode B
- 风格锚定样本或 scout_report.json 路径
- `knowledge_profile.json` 路径（知识库结构化摘要）
- 术语约束摘要
- `rag_enabled`：当前项目 corpus 是否 >= 10（自动启用 RAG）
- MAX_WORKERS / 模型 / 温度
- 已知截断历史或长度敏感行号

## 执行清单

### 任务 1：API 执行
```bash
cli.py process [--style-anchor <path>]
# 或
cli.py run --input <path> --glossary <path>
```

执行规范：
- 读取 `knowledge_profile.json`，将 `风格`/`设定`/`角色`/`禁忌` category 注入 API system prompt
- 自动 RAG 检索：每行 source 执行 `search_corpus()`（corpus >= 10 时启用），similarity >= 0.65 的命中注入 few-shot
- 异步并发（Semaphore=MAX_WORKERS）
- 截断检测：响应不以 `}` 结尾 → 不重试，直接报 `max_tokens` 不足
- 指数退避重试（最多 5 次）
- 单行/批、JSON/[N] 双解析
- 日志记录

### 任务 2：异常处理
- max_tokens 不足：标记行号、建议调高 max_tokens 或拆行
- API 连续失败：回传失败行号与错误码
- 解析失败：回传原始响应片段

### 任务 3：术语强制替换（glossary）
受主 Agent 指派执行：
```bash
cli.py glossary
```
正则替换术语偏差。信任脚本，不二次质疑。
回传：替换统计、残余偏差行号。

### 任务 4：一键串流（cli.py run）
若主 Agent 指派串流模式，按顺序执行 ingest→process→glossary→export。
每阶段回传摘要，异常立即中断并上报。

## 回传格式

```
【执行摘要】成功/失败/部分成功
【关键数据】
- 成功行数: N
- 失败行号: [...]
- 截断预警行号: [...]
- 术语替换数: N（glossary 阶段）
- 残余偏差行号: [...]
- RAG 命中数: N
- RAG 直接复用数: N（similarity >= 0.65 且 target 一致，跳过 API）
- API 异常摘要: {错误码: 次数}
- 耗时: N 秒
【输出文件】workspace/...
【异常标记】无 / 详见上文
【下一步建议】继续 / 重试 / 调参 / 报 PM
```
