# Workflow Specification

## Node 1: Project Scan

**Trigger:** After `cli.py ingest` completes.

**Input:**
- Full source text (from workspace DB)
- Glossary list
- Knowledge base (optional)
- Project config (game_type, theme, lang_pair)

**Outputs:**
- `project_summary.json`: terminology_distribution, style_anchor, risk_points, mode

**Steps:**
1. Read all source sentences into context
2. Count glossary term occurrences and positions
3. Detect glossary variants (plural, lowercase, possessive)
4. Analyze first 10 sentences for style baseline
5. Flag sentences with potential term-context conflicts
6. Determine mode (new / optimize) by column presence

## Node 2: Batch Dispatch

**Trigger:** After scan completes.

**Inputs:**
- `project_summary.json`
- Pending rows from workspace DB

**Outputs:**
- `batch_commands.json`: list of batches with custom prompts and API params

**Dispatch Rules:**
- Normal batch: <=15 rows, no risk flags, covered glossary
- High-risk batch: <=5 rows, has risk flags or uncovered terms
- Manual-review: rows with unresolved conflicts or sensitive content
- Locked rows: skipped, copied as-is

## Node 3: API Execution

**Trigger:** After dispatch.

**Tool:** `cli.py translate`

**Parallelization:**
- Normal batches: default model, temp=0.3
- High-risk batches: strong model, temp=0.2
- All batches share semaphore=100

## Node 4: Glossary Enforcement

**Trigger:** After all API calls complete.

**Tool:** `cli.py glossary`

**Guarantee:** 100% exact-match replacement. No exceptions.

## Node 5: Quality Acceptance

**Trigger:** After glossary enforcement.

**Sampling:**
- Full scan for terminology deviations (should be 0)
- 10% deep sample for style drift and context errors
- All high-risk batches get full scan

**Grading:**
- PASS: no issues or minor acceptable deviations
- REWRITE: detectable issues, root cause known, retry allowed
- MANUAL: ambiguous or severe issues, human required

**Retry Logic:**
- Max 3 retries per batch
- Each retry must change strategy (model, prompt, or batch size)

## Node 6: Global Consistency & Export

**Trigger:** After all batches pass or are flagged manual.

**Checks:**
1. Cross-batch term uniformity
2. Style首尾 alignment
3. Generate diff (Mode B only)

**Tools:**
- `cli.py export` → final.xlsx
- `cli.py diff` → diff.xlsx (Mode B)

## Exception Handling

### API Failure
- Retry with exponential backoff (handled by engine.py)
- After 3 failures: mark batch as failed, do not block others

### Agent Context Overflow
- For projects >5000 rows: split into sub-projects of 1000 rows
- Sub-projects share glossary_map and style_anchor via workspace DB

### Glossary Conflict
- When term table conflicts with context: Agent decides override
- Decision logged in `exception_log.json`
- If uncertain: mark for manual review
