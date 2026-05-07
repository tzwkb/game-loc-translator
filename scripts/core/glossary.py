"""
glossary.py — Post-processing glossary enforcement.
Longest-term-first, character-level replacement. 100% deterministic.
"""

import json
import re
from pathlib import Path
from collections import defaultdict


def _make_pattern(source_term: str):
    """Compile regex for a source term.
    Unified ASCII-alphanumeric boundary for bilingual (CN+EN) mixed text.
    - (?<![a-zA-Z0-9]) : preceding char is NOT ASCII letter/digit
    - (?![a-zA-Z0-9])  : following char is NOT ASCII letter/digit
    This works for:
      - English terms in Chinese text (e.g. "Dragon" in "这个Dragon很强大")
      - Mixed terms like "HP", "Dragon Fire"
      - Chinese terms in any text
    It prevents partial matches like "HP" inside "help".
    """
    escaped = re.escape(source_term)
    return re.compile(r'(?<![a-zA-Z0-9])' + escaped + r'(?![a-zA-Z0-9])', re.IGNORECASE)


def enforce_glossary(translations: dict, glossary: list) -> dict:
    """
    translations: {row_id: text}
    glossary: list of (source, target)
    Returns: {row_id: enforced_text}
    Also writes replacement_log.json.

    Logic:
    1. Sort glossary by source length descending (longest first)
       -> "Dragon Fire" replaces before "Dragon", avoiding partial match
    2. Compile regex per term with appropriate boundary
    3. Scan each translation line, replace all occurrences
    """
    if not glossary:
        return translations

    # Step 1: longest source term first
    sorted_glossary = sorted(glossary, key=lambda x: len(x[0]), reverse=True)

    patterns = []
    for st, tt in sorted_glossary:
        pat = _make_pattern(st)
        patterns.append((st, tt, pat))

    results = {}
    log = defaultdict(list)

    for row_id, text in translations.items():
        if not text:
            results[row_id] = text
            continue
        modified = text
        for st, tt, pat in patterns:
            new_text, count = pat.subn(tt, modified)
            if count > 0:
                log[row_id].append({"term": st, "replacement": tt, "count": count})
                modified = new_text
        results[row_id] = modified

    # Write log
    if log:
        log_path = Path("workspace/glossary_replacements.json")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(json.dumps(dict(log), ensure_ascii=False, indent=2), encoding="utf-8")

    return results


def build_glossary_map(glossary: list, translations: dict) -> dict:
    """Build runtime glossary map from confirmed translations.
    {source: target} based on glossary + actual usage.
    """
    mapping = {st: tt for st, tt in glossary}
    for st, tt in glossary:
        lower_st = st.lower()
        for text in translations.values():
            if not text:
                continue
            if st[0].isupper() and lower_st in text.lower():
                mapping[lower_st] = tt.lower() if tt[0].isupper() else tt
    return mapping
