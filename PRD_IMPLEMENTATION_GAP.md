# PRD vs 实现对比文档

> 基于《游戏AI翻译Agent 产品需求文档（PRD）V1.1》与当前实现对比

---

## 一、核心功能对比

### 1.1 双业务模式

| PRD 需求 | 实现状态 | 说明 |
|---|---|---|
| Mode A 全新翻译 | ✅ 已实现 | 自动检测无 draft 列 → mode=new |
| Mode B 初译优化 | ✅ 已实现 | 检测到 draft 列 → mode=optimize |
| 系统自动识别 | ✅ 已实现 | 脚本自动判断，Agent 汇报确认 |

### 1.2 术语表

| PRD 需求 | 实现状态 | 说明 |
|---|---|---|
| 独立上传、强制遵循 | ✅ 已实现 | `--glossary` 加载，prompt 注入 + 正则强制替换 |
| 支持 Excel/CSV/TXT/JSON/TSV | ✅ 已实现 | 多格式支持 |
| 译文后自动扫描校准 | ✅ 已实现 | `cli.py glossary` |
| 字段完整性校验 | ⚠️ Agent 层 | Agent 预览前 5 行预检 |
| 按项目 ID 绑定 | ✅ 已实现 | DB 记录 project_id，`cli.py project list` 查看历史 |
| 上传/替换/删除管理 | ⚠️ Agent 层 | Agent 通过对话操作文件 |

### 1.3 知识库

| PRD 需求 | 实现状态 | 说明 |
|---|---|---|
| 可选插拔 | ✅ 已实现 | `--knowledge-base` 为可选参数 |
| 支持 Excel/CSV/TXT/JSON/Markdown | ✅ 已实现 | 多格式支持 |
| 按类别分类 | ✅ 已实现 | {category, note, text} 结构 |
| 新增/编辑/删除 | ⚠️ Agent 层 | Agent 直接编辑文件 |
| 按项目绑定复用 | ⚠️ Agent 层 | Agent 维护 project_profiles.json |

### 1.4 RAG 语料库

| PRD 需求 | 实现状态 | 说明 |
|---|---|---|
| 三维分仓检索 | ✅ 已实现 | game_type + theme + lang_pair 硬过滤 |
| 向量检索 + 相似度阈值 | ✅ 已实现 | FAISS + bge-m3，阈值 0.65 |
| Top-K 召回 | ✅ 已实现 | 默认 Top-K=3 |
| 语料入库/批量导入 | ✅ 已实现 | `corpus add/import` |
| 分类打标 | ✅ 已实现 | add/import 支持三维标签 |
| 删除劣质语料 | ✅ 已实现 | `cli.py corpus delete --id N` |
| 多级召回（精准→泛化兜底） | ⚠️ Agent 层 | Agent 可手动执行两次 retrieve |
| 后台管理界面 | ❌ 已放弃 | PM 明确不需要 GUI |

### 1.5 一致性保障

| PRD 需求 | 实现状态 | 说明 |
|---|---|---|
| 文档级全局术语扫描 | ✅ 已实现 | `glossary.py` 正则替换 |
| 私有术语映射表 | ⚠️ Agent 层 | Agent 运行时扫描构建 |
| 首段锚定 | ✅ 已实现 | 前十行自动翻译作为风格锚点注入 prompt |
| 风格首尾对齐 | ⚠️ Agent 层 | Agent 对比首末段 tone |
| 句式一致性 | ⚠️ Agent 层 | Agent 抽检同类型句子 |

### 1.6 Mode B 优化

| PRD 需求 | 实现状态 | 说明 |
|---|---|---|
| 不推翻合理初译 | ✅ 已实现 | `optimize_base.md` 红线约束 |
| 四类有限修改 | ✅ 已实现 | prompt 中定义 |
| 差异比对 + 修改痕迹 | ✅ 已实现 | `cli.py diff` |
| 自动分类 change_type | ⚠️ Agent 层 | 脚本初分，Agent 抽检终审修正 |
| 保留合理句式 | ⚠️ 依赖模型 | prompt 约束，Agent 质检兜底 |

### 1.7 文件接入

| PRD 需求 | 实现状态 | 说明 |
|---|---|---|
| TXT / CSV / Excel | ✅ 已实现 | |
| Word | ❌ 未实现 | 无 `.docx` 输入解析 |
| 自动识别 Mode A/B | ✅ 已实现 | |
| 批量处理多文件 | ⚠️ Agent 层 | Agent 依次独立处理 |

---

## 二、非功能需求对比

| PRD 需求 | 实现状态 | 说明 |
|---|---|---|
| 1000+句 ≤30秒 | ❓ 未验证 | 依赖外部 LLM API，1000 句约 3-8 分钟 |
| 并发批量处理 | ✅ 已实现 | asyncio + Semaphore=100 |
| RAG 阈值/Top-K 可调 | ✅ 已实现 | `config.py` |
| 后台调参 | ⚠️ Agent 层 | Agent 直接改 `config.py` |
| 模块化 | ✅ 已实现 | RAG/术语/知识库/文件解析各自独立 |
| 代码注释 | ⚠️ 一般 | 核心函数有 docstring |
| 部署文档 | ⚠️ 部分实现 | README.md 已补齐 |
| 稳定性 | ⚠️ 依赖 API | gemini-3.1-pro-preview 响应慢，需长超时 |
| 易用性 | ⚠️ Agent 层 | Agent 对话交互降低门槛 |

---

## 三、差距清单（按优先级）

### P0 — 需代码修复

1. **API 模型稳定性**：gemini-3.1-pro-preview 响应极慢（需 300s+ 超时），provider 层面风险
2. **Word 输入格式**：PRD 明确要求支持 Word，未实现
3. ~~corpus delete~~：✅ 已实现 `cli.py corpus delete --id`

### P1 — Agent 层已解决（无需改代码）

4. **记忆功能** → Agent 维护 `project_profiles.json`
5. **术语表预检** → Agent 预览检查
6. **术语上下文冲突标记** → Agent 扫描标记 `rows.notes`
7. **禁用词合规过滤** → Agent 质检时扫描
8. **差异终审** → Agent 抽检修正 change_type
9. **风格首尾 check** → Agent 对比首末段
10. **知识库动态编辑** → Agent 直接改文件
11. **多文件批量** → Agent 依次处理
12. **后台调参** → Agent 改 `config.py`
13. **后台管理界面** → PM 明确不需要 GUI，Agent 对话即后台

### P2 — 体验优化

14. **多级 RAG 召回**：Agent 可手动兜底，代码层加 fallback 更干净
15. **项目持久化切换**：Agent 按 project_id 隔离 workspace 即可
16. ~~requirements.txt / setup.py~~：✅ 已添加 `requirements.txt` + `.env.example`
17. **性能基准测试**：未建立 1000+句基准

---

## 四、7天开发计划回顾

| 天 | PRD 计划 | 当前状态 |
|---|---|---|
| Day 1 | 架构 + 文件解析 + DB | ✅ 完成 |
| Day 2 | RAG 向量检索 + 语料存储 | ✅ 完成 |
| Day 3 | 术语约束 + 知识库加载 | ✅ 完成 |
| Day 4 | 双模式翻译链路 + Prompt | ✅ 完成 |
| Day 5 | 一致性引擎 + 差异比对 | ✅ 已实现，含 diff_review 脚本 |
| Day 6 | 后台管理 + 参数配置 | ❌ GUI 放弃，Agent 层替代 |
| Day 7 | 集成测试 + 文档 | ⚠️ CLI 测试完成，性能基准未建立 |

**结论**：核心内核（Day 1-5）已落地。Day 6 GUI 按 PM 要求放弃，由 Agent 对话替代。Day 7 性能基准和 Word 解析为剩余硬需求。
