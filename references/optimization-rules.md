# MTPE Optimization Red Lines

## Allowed Modifications (Four Categories Only)

1. **Correct mistranslation, omission, or terminology error**
   - Wrong term used (not matching glossary)
   - Missing meaning from source
   - Factual error in context

2. **Unify terminology throughout the document**
   - Same source term must use same target everywhere
   - Variant forms must be normalized

3. **Align to genre-standard style**
   - Match the style anchor established in first paragraph
   - Use genre-appropriate register (formal/casual/poetic)
   - Follow lore-consistent naming conventions

4. **Polish wording and sentence flow**
   - Fix awkward phrasing without changing core meaning
   - Improve readability for game context
   - Adjust for natural speech patterns in dialogue

## Forbidden Modifications

- **Do NOT rewrite reasonable human translations**
- **Do NOT change core meaning or intent**
- **Do NOT uniformize all sentence patterns** (preserve human variety)
- **Do NOT remove flavor or character voice**
- **Do NOT "improve" for the sake of improving** — if it's good, leave it

## Decision Criteria per Sentence

```
Is there a clear error?          → YES → Fix (category 1)
Does terminology mismatch?       → YES → Fix (category 2)
Does style clearly drift?        → YES → Fix (category 3)
Is wording genuinely awkward?    → YES → Fix (category 4)
None of the above?               → NO  → Preserve draft unchanged
```

## Output Format

For each modified sentence, annotate change type:
- `[TERM]` — terminology correction
- `[STYLE]` — style alignment
- `[GRAMMAR]` — grammatical fix
- `[POLISH]` — wording refinement

If no change: output draft exactly as-is, no annotation.
