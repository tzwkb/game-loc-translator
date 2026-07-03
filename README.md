# Game Localization Translator

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Agent Skill](https://img.shields.io/badge/Agent%20Skill-Codex-blue.svg)](SKILL.md)
[![Python](https://img.shields.io/badge/Python-3.x-blue.svg)](https://www.python.org/)

English | [中文](README_ZH.md)

## Overview

 Game-localization translation and MTPE Agent Skill using terminology enforcement, style guides, and RAG references.

## Key Capabilities

- Supports fresh translation and draft optimization modes.
- Controls output with termbases, style guides, and reference corpora.
- Targets project-based game-localization workflows.

## Usage

 Prepare project resources according to SKILL.md/README directories, modes, and input formats before invoking the skill.

## Notes

 Translation output should follow project terminology, style, and client requirements.

## Command and Configuration Reference

The following code blocks keep commands, paths, filenames, and configuration keys literal; explanatory comments are translated for the English README.

```
| id | source                     | key            | locked |
|----|----------------------------|----------------|--------|
| 1  | The Dragon attacks.        | dlg_boss_001   | 0      |
```

```
| id | source                     | draft            | key            | locked |
|----|----------------------------|------------------|----------------|--------|
| 1  | The Dragon attacks.        | 龙发起了攻击。   | dlg_boss_001   | 0      |
```

```
Dragon = 巨龙
Warrior = 战士
Arcane Crystal = 奥术水晶
HP = 生命值
```

```
| source_term | target_term |
|-------------|-------------|
| Dragon      | 巨龙        |
| Warrior     | 战士        |
```

```json
[{"source":"Dragon","target":"巨龙"}]
```

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

```
| category | note | text                                      |
|----------|------|-------------------------------------------|
| 风格     |      | 技能描述使用四字短语，对话口语化。        |
| 禁忌     |      | 不得出现"能量""升级"。                   |
| 角色     | 主角 | 李青云 — 昆仑派弟子，性格沉稳。           |
```

```
Translate input/game_text.xlsx, use input/glossary.txt as the glossary, and use input/kb.txt as the knowledge base.
Project type: RPG; genre: fantasy; language pair: EN-ZH.
```
