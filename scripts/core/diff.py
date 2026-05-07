"""
diff.py — Generate 4-column diff for MTPE mode.
source | draft | optimized | change_type | change_reason
"""

import csv
import re
from pathlib import Path
from difflib import SequenceMatcher
import sqlite3

import config
WORKSPACE_DB = str(config.WORKSPACE_DIR / "workspace.db")


def classify_change(source: str, draft: str, optimized: str) -> tuple:
    """Returns (change_type, change_reason)."""
    if not optimized or optimized == draft:
        return "no_change", ""

    # Terminology check: if a word in draft is completely replaced in optimized
    draft_words = set(re.findall(r'\w+', draft.lower()))
    opt_words = set(re.findall(r'\w+', optimized.lower()))
    removed = draft_words - opt_words
    added = opt_words - draft_words

    # Heuristic: large word overlap change = terminology fix
    if removed and added:
        sm = SequenceMatcher(None, draft, optimized)
        ratio = sm.ratio()
        if ratio < 0.7:
            return "terminology_fix", f"Significant word change (ratio {ratio:.2f})"

    # Style check: same meaning but different tone
    sm = SequenceMatcher(None, draft, optimized)
    ratio = sm.ratio()
    if 0.7 <= ratio < 0.95:
        return "style_alignment", f"Tone/style adjustment (ratio {ratio:.2f})"

    # Grammar check: minor fixes
    if ratio >= 0.95:
        return "grammar_fix", "Minor grammatical correction"

    return "polish", "General refinement"


def generate_diff(output_path: str):
    conn = sqlite3.connect(WORKSPACE_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT row_num, source, draft, translation FROM rows WHERE draft != '' ORDER BY row_num"
    ).fetchall()
    conn.close()

    results = []
    for r in rows:
        ctype, creason = classify_change(r["source"], r["draft"], r["translation"])
        results.append({
            "row_num": r["row_num"],
            "source": r["source"],
            "draft": r["draft"],
            "optimized": r["translation"] or "",
            "change_type": ctype,
            "change_reason": creason,
        })

    # Write xlsx
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Diff"
    headers = ["row_num", "source", "draft", "optimized", "change_type", "change_reason"]
    ws.append(headers)
    for r in results:
        ws.append([r[h] for h in headers])
    wb.save(output_path)
    print(f"[diff] Saved -> {output_path} ({len(results)} rows)")

    # Write JSON for agent consumption
    json_path = str(Path(output_path).with_suffix(".json"))
    import json
    Path(json_path).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
