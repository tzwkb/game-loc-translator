# Game Localization Translator

[中文](README_ZH.md) | English


## Overview

 Game-localization translation and MTPE Agent Skill using terminology enforcement, style guides, and RAG references.

## Key Capabilities

- Supports fresh translation and draft optimization modes.
- Controls output with termbases, style guides, and reference corpora.
- Targets project-based game-localization workflows.

## Usage

 Prepare project resources according to SKILL.md/README directories, modes, and input formats before invoking the skill.

## Status

 This repository is maintained or used according to the current README notes.

## Notes

 Translation output should follow project terminology, style, and client requirements.

## Command and Configuration Reference

The following code blocks are preserved from the primary README. Commands, paths, and configuration keys are not translated; adjust them for the actual environment.

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
翻译 input/game_text.xlsx，术语表用 input/glossary.txt，知识库用 input/kb.txt。
项目类型 RPG，题材 fantasy，语言对 EN-ZH。
```

## Detailed Technical Notes

The primary README keeps the original technical details, history notes, full commands, and file layout. This file maintains the English version of the core documentation; consult the primary README code blocks and paths when exact commands are needed.
