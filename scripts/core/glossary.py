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


def enforce_glossary(translations: dict, glossary: list) -> tuple:
    """
    translations: {row_id: text}
    glossary: list of (source, target)
    Returns: ({row_id: enforced_text}, {row_id: [{"term": str, "replacement": str, "count": int}]})
    Also writes replacement_log.json.

    Logic:
    1. Sort glossary by source length descending (longest first)
       -> "Dragon Fire" replaces before "Dragon", avoiding partial match
    2. Compile regex per term with appropriate boundary
    3. Scan each translation line, replace all occurrences
    """
    if not glossary:
        return translations, {}

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

    return results, dict(log)


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


def detect_changed_terms(rows: list, glossary: list) -> list:
    """
    Detect terminology changes between draft and optimized translations (Mode B).

    rows: list of dicts with keys: row_num, source, draft, optimized
    glossary: list of (source, target)

    Returns: list of dicts with keys: row_num, source_term, target_term, draft_term, context
    """
    if not glossary:
        return []

    # Build patterns for source terms (Chinese)
    sorted_glossary = sorted(glossary, key=lambda x: len(x[0]), reverse=True)
    source_patterns = []
    for st, tt in sorted_glossary:
        pat = _make_pattern(st)
        source_patterns.append((st, tt, pat))

    # Build patterns for target terms (English)
    target_patterns = []
    for st, tt in sorted_glossary:
        pat = _make_pattern(tt)
        target_patterns.append((st, tt, pat))

    changed_terms = []

    for row in rows:
        row_num = row.get("row_num")
        source = row.get("source", "")
        draft = row.get("draft", "")
        optimized = row.get("optimized", "")

        if not draft or not optimized or draft == optimized:
            continue

        # Check each glossary term
        for st, tt, src_pat in source_patterns:
            # Check if source term appears in source text
            src_matches = list(src_pat.finditer(source))
            if not src_matches:
                continue

            # Check if target term appears in draft (wrong usage)
            tgt_pat = _make_pattern(tt)
            draft_tgt_matches = list(tgt_pat.finditer(draft))

            # Check if target term appears in optimized (correct usage)
            opt_tgt_matches = list(tgt_pat.finditer(optimized))

            # If target term is NOT in draft but IS in optimized, it was added
            if not draft_tgt_matches and opt_tgt_matches:
                # Find context in source
                for match in src_matches:
                    start = max(0, match.start() - 20)
                    end = min(len(source), match.end() + 20)
                    context = source[start:end]
                    if start > 0:
                        context = "..." + context
                    if end < len(source):
                        context = context + "..."

                    changed_terms.append({
                        "row_num": row_num,
                        "source_term": st,
                        "target_term": tt,
                        "draft_term": "(missing)",
                        "context": context
                    })

            # If target term IS in draft but NOT in optimized, it was removed
            elif draft_tgt_matches and not opt_tgt_matches:
                # Find context in draft
                for match in draft_tgt_matches:
                    start = max(0, match.start() - 20)
                    end = min(len(draft), match.end() + 20)
                    context = draft[start:end]
                    if start > 0:
                        context = "..." + context
                    if end < len(draft):
                        context = context + "..."

                    changed_terms.append({
                        "row_num": row_num,
                        "source_term": st,
                        "target_term": tt,
                        "draft_term": match.group(),
                        "context": context
                    })

    return changed_terms


def export_changed_terms(changed_terms: list, output_path: str):
    """
    Export changed terms to xlsx file.
    """
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Changed Terms"

    # Write header
    headers = ["row_num", "source_term", "target_term", "draft_term", "context"]
    ws.append(headers)

    # Write data
    for item in changed_terms:
        ws.append([
            item["row_num"],
            item["source_term"],
            item["target_term"],
            item["draft_term"],
            item["context"]
        ])

    # Auto-adjust column widths
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width

    wb.save(output_path)


def detect_term_hits(rows: list, glossary: list) -> list:
    """
    Detect glossary term hits in source text and translation context (Mode A).

    rows: list of dicts with keys: row_num, source, translation
    glossary: list of (source, target)

    Returns: list of dicts with keys: row_num, source_term, target_term, occurrences, source_context, translation_context
    """
    if not glossary:
        return []

    # Build patterns for source terms (Chinese)
    sorted_glossary = sorted(glossary, key=lambda x: len(x[0]), reverse=True)
    patterns = []
    for st, tt in sorted_glossary:
        pat = _make_pattern(st)
        patterns.append((st, tt, pat))

    term_hits = []

    for row in rows:
        row_num = row.get("row_num")
        source = row.get("source", "")
        translation = row.get("translation", "")

        if not source:
            continue

        # Check each glossary term
        for st, tt, pat in patterns:
            # Find all occurrences in source
            matches = list(pat.finditer(source))
            if not matches:
                continue

            # Extract source context (around first match)
            first_match = matches[0]
            src_start = max(0, first_match.start() - 30)
            src_end = min(len(source), first_match.end() + 30)
            source_context = source[src_start:src_end]
            if src_start > 0:
                source_context = "..." + source_context
            if src_end < len(source):
                source_context = source_context + "..."

            # Extract translation context (find target term in translation)
            tgt_pat = _make_pattern(tt)
            tgt_matches = list(tgt_pat.finditer(translation))
            if tgt_matches:
                tgt_match = tgt_matches[0]
                tgt_start = max(0, tgt_match.start() - 30)
                tgt_end = min(len(translation), tgt_match.end() + 30)
                translation_context = translation[tgt_start:tgt_end]
                if tgt_start > 0:
                    translation_context = "..." + translation_context
                if tgt_end < len(translation):
                    translation_context = translation_context + "..."
            else:
                translation_context = "(not found)"

            term_hits.append({
                "row_num": row_num,
                "source_term": st,
                "target_term": tt,
                "occurrences": len(matches),
                "source_context": source_context,
                "translation_context": translation_context
            })

    return term_hits


def export_term_hits(term_hits: list, output_path: str):
    """
    Export term hits to xlsx file.
    """
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Term Hits"

    # Write header
    headers = ["row_num", "source_term", "target_term", "occurrences", "source_context", "translation_context"]
    ws.append(headers)

    # Write data
    for item in term_hits:
        ws.append([
            item["row_num"],
            item["source_term"],
            item["target_term"],
            item["occurrences"],
            item["source_context"],
            item["translation_context"]
        ])

    # Auto-adjust column widths
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width

    wb.save(output_path)
