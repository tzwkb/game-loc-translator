#!/usr/bin/env python3
"""Diff review: sample 10% non-no_change rows for manual verification."""
import sqlite3, sys, random
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "core"))
import config

db = sqlite3.connect(str(config.WORKSPACE_DIR / "workspace.db"))
db.row_factory = sqlite3.Row

# 1. False negative: no_change but draft != translation
fn = db.execute(
    "SELECT * FROM rows WHERE change_type = 'no_change' AND draft != translation"
).fetchall()
print("=" * 60)
print("FALSE NEGATIVES (no_change but draft != translation)")
print("=" * 60)
for r in fn:
    print(f"Row {r['row_num']}:")
    print(f"  DRAFT:     {r['draft'][:100]}")
    print(f"  OPTIMIZED: {r['translation'][:100]}")
    print(f"  -> Should be: style_alignment or polish")
    db.execute(
        "UPDATE rows SET change_type = ?, change_reason = ? WHERE id = ?",
        ("style_alignment", "调整文风与风格锚点一致", r["id"])
    )
if fn:
    db.commit()
    print(f"Fixed {len(fn)} false negatives -> style_alignment")
else:
    print("None found.")

# 2. Sample 10% non-no_change for review
sample = db.execute(
    "SELECT * FROM rows WHERE change_type != 'no_change' AND change_type != '' ORDER BY RANDOM() LIMIT 60"
).fetchall()
print(f"\n{'=' * 60}")
print(f"SAMPLE REVIEW ({len(sample)} rows, ~10%)")
print("=" * 60)

fixes = 0
for r in sample:
    src = r['source'][:80]
    draft = r['draft'][:80]
    opt = r['translation'][:80]
    ctype = r['change_type']
    creason = r['change_reason']
    
    # Auto-check: if draft == opt, should be no_change
    if draft.strip() == opt.strip() and ctype != 'no_change':
        print(f"\nRow {r['row_num']} [FIXED]:")
        print(f"  draft == optimized but ctype={ctype}")
        db.execute(
            "UPDATE rows SET change_type = ?, change_reason = ? WHERE id = ?",
            ("no_change", "", r["id"])
        )
        fixes += 1
        continue
    
    # Auto-check: if only terminology differs, should be terminology_fix
    draft_words = set(draft.lower().split())
    opt_words = set(opt.lower().split())
    diff_words = draft_words.symmetric_difference(opt_words)
    
    print(f"\nRow {r['row_num']} [{ctype}] {creason[:30]}")
    print(f"  SRC: {src}")
    print(f"  DRA: {draft}")
    print(f"  OPT: {opt}")

if fixes:
    db.commit()
    print(f"\nFixed {fixes} false positives -> no_change")

# 3. Terminology deviation check (check all rows against glossary)
from ingest import load_glossary
glossary = load_glossary(str(config.BASE_DIR / 'input' / 'glossary_deduped.xlsx'))
print(f"\n{'=' * 60}")
print("TERMINOLOGY DEVIATION CHECK")
print("=" * 60)

all_rows = db.execute("SELECT * FROM rows WHERE status = 'done'").fetchall()
deviations = 0
for r in all_rows:
    src = str(r['source'] or '')
    opt = str(r['translation'] or '')
    for st, tt in glossary:
        if st in src and tt not in opt:
            # Skip short terms that are substrings of other words
            if len(st) <= 1:
                continue
            # Check if the term is in a different case
            if tt.lower() in opt.lower():
                continue
            deviations += 1
            if deviations <= 10:
                print(f"Row {r['row_num']}: '{st}' in source -> '{tt}' not in optimized")
            break

print(f"Total deviations: {deviations}")

db.close()
print(f"\n{'=' * 60}")
print("DIFF REVIEW COMPLETE")
print("=" * 60)
