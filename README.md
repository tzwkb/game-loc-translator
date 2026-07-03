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

## Input Preparation

This skill has no web upload screen. Put files under `input/` or provide absolute paths to the Agent.

### Source Files

Excel is recommended. Mode A expects source-only rows; Mode B expects source plus draft translation. The pipeline auto-detects columns such as `source`, `draft`, `key`, `locked`, `placeholder`, `max_length`, and `gender`.

Rows with `locked=1`, `TRUE`, or equivalent values are passed through unchanged and are not sent to the API.

### Glossary

Glossaries can be TXT, Excel/CSV, or JSON. TXT entries may use separators such as `=`, tab, `|`, or `: `. Excel/CSV glossaries use source and target term columns. JSON entries use source/target objects.

### Knowledge Base

Knowledge-base files describe worldbuilding, style, forbidden terms, and character constraints. TXT files use `---` separated blocks; Excel/CSV files can use category, note, and text columns.

Recommended categories include forbidden terms, style, setting, and character notes. These categories feed process prompts and QA checks.

## Agent Handoff

Users do not need to run commands manually. Give the Agent the input file, glossary, knowledge base, project type, genre, and language pair. The Agent schedules ingest, processing, QA, glossary enforcement, and export.

## Quick Start

1. Copy `.env.example` to `.env` and configure API base URL and key.
2. Run `python cli.py doctor` from `scripts/`.
3. Run `python cli.py ingest` with input, glossary, knowledge base, project ID, game type, theme, and language pair.
4. Run `python cli.py process`, `python cli.py glossary`, and `python cli.py export`, or use `python cli.py run` for the combined flow.

## Supported File Formats

Inputs support `.xlsx`, `.csv`, and `.txt`. Glossaries support `.xlsx/.csv` term tables and TXT term pairs. The Agent reports detected columns before continuing.

## Outputs

Outputs are written to `output/`. Mode A produces translated files. Mode B also produces diff files with `change_type` and `change_reason` for MTPE review.

## Pipeline Components

### Ingest Agent

The ingest step reads source files, detects columns, normalizes glossary and knowledge-base inputs, and prepares the project state for downstream processing.

### Process Agent

The process step performs translation or MTPE. It applies terminology, style, knowledge-base constraints, retries truncated outputs, and keeps Mode B change information when draft translations are present.

### QA Agent

The QA step checks terminology, formatting, locked rows, placeholders, and project constraints before export. It is intended as a deterministic and review-oriented gate rather than a replacement for human final review.

### Corpus Reuse

High-quality sentence pairs can be stored by game type, theme, and language pair so later projects can retrieve better references through RAG.

## Directory Coverage

`input/` holds source files, glossaries, and knowledge bases. `scripts/` holds CLI and processing logic. `output/` holds translated files and MTPE diff exports. `SKILL.md` defines how the Agent should trigger and orchestrate the workflow.

## Chinese README Section Map

### Core Capabilities

Matches the Chinese `核心能力` table: dual translation modes, deterministic terminology enforcement, style-guide control, RAG references, batch scheduling, MTPE diff tracking, and corpus reuse.

### File Preparation Guide

Matches the Chinese `文件准备指南`: source files, glossary files, knowledge-base files, and how users hand them to the Agent.

### Quick Start and Execution Flow

Matches the Chinese `快速开始`: API configuration, environment check, ingest, process, glossary enforcement, export, and the combined `run` shortcut.

### File Format Support

Matches the Chinese `文件格式支持`: `.xlsx`, `.csv`, `.txt`, TXT/Excel/CSV/JSON glossary formats, and automatic column detection.

### Workflow and Components

Matches the Chinese implementation notes: ingest-agent prepares state, process-agent performs translation or MTPE, qa-agent checks output, and export writes final deliverables.

### Directory Layout

The Chinese README contains the fuller directory tree. The English README names the same working areas: `input/`, `scripts/`, `output/`, project state, glossary resources, and `SKILL.md` orchestration rules.
