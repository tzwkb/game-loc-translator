# Exception Handling Rules

## Terminology Conflict Arbitration

**Rule:** Glossary table has highest priority. Context exception only applies when:
1. Context explicitly indicates the term is used as a name/title (e.g., "Dragon said: 'I am human'")
2. The glossary entry itself has a context note permitting the exception

**Decision Tree:**
```
Glossary says X → Y
Context suggests X is name, not term
  ├─ Glossary has context note for name usage → Follow context note
  ├─ Strong contextual evidence (pronouns, verbs) → Preserve original, flag exception
  └─ Ambiguous → Conservative: use glossary default, flag for manual review
```

## Style Drift Fix

**Symptom:** Batch N's tone differs from batch 1's anchor.

**Causes:**
1. Prompt lost style anchor (too many batches, context diluted)
2. Content type shift (narrative → dialogue)
3. Model temperature too high

**Fixes:**
1. Re-inject style anchor into system prompt
2. If content type shift is legitimate, accept with annotation
3. Lower temperature for remaining batches

## RAG Misleading Reference

**Symptom:** Retrieved corpus case has high similarity but different conclusion.

**Rule:** Do NOT blindly follow RAG. RAG is reference, not authority.

**Action:**
- If RAG contradicts glossary → Glossary wins
- If RAG contradicts knowledge base → Knowledge base wins
- If multiple RAG cases conflict → Use highest quality_score case
- If still ambiguous → Mark for manual review

## API Quality Degradation

**Symptom:** Batch returns garbled text, wrong language, or prompt injection artifacts.

**Causes:**
1. Model hallucination
2. Batch too large, JSON parsing failed
3. Temperature too high

**Escalation Chain:**
1. Retry same batch with same model (transient error)
2. Switch to strong model
3. Reduce batch size to 5
4. Reduce temperature to 0.1
5. If still failing → Mark manual, do not retry infinitely

## Context Window Overflow

**Symptom:** Agent can no longer see early project context.

**Mitigation:**
- Projects <= 1000 rows: single session
- Projects 1000-5000 rows: sub-project every 1000 rows, shared state in DB
- Projects > 5000 rows: chunked processing, human oversight recommended

## Manual Review Flagging

Always flag for manual review when:
- Terminology conflict cannot be resolved
- Cultural reference unknown to system
- Sensitive content (political, religious, sexual)
- Client explicitly marked row as locked
- Batch failed 3 retries
- Agent confidence < 0.7
