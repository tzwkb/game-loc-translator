"""
glossary.py — Post-processing glossary enforcement.
Exact-match replacement. 100% deterministic.
"""

import json
import re
from pathlib import Path
from collections import defaultdict


def enforce_glossary(translations: dict, glossary: list) -> dict:
    """
    translations: {row_id: text}
    glossary: list of (source, target)
    Returns: {row_id: enforced_text}
    Also writes replacement_log.json.
    """
    if not glossary:
        return translations

    # Build regex map: case-insensitive, whole word where possible
    patterns = []
    for st, tt in glossary:
        escaped = re.escape(st)
        # Use word boundary if source is alphabetic
        if st.isalpha():
            pat = re.compile(r'\b' + escaped + r'\b', re.IGNORECASE)
        else:
            pat = re.compile(escaped, re.IGNORECASE)
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
    # Add confirmed variants found in translations
    for st, tt in glossary:
        lower_st = st.lower()
        for text in translations.values():
            if not text:
                continue
            # If source is title-case, check for lowercase variant
            if st[0].isupper() and lower_st in text.lower():
                mapping[lower_st] = tt.lower() if tt[0].isupper() else tt
    return mapping
