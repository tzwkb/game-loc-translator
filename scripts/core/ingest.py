"""
ingest.py — Parse input files and load into workspace.
Supports .xlsx, .csv, .txt.
"""

import json
import re
import sqlite3
from pathlib import Path
from engine import get_file_headers, get_cell_text, load_workbook
import config

WORKSPACE_DB = str(config.WORKSPACE_DIR / "workspace.db")


def init_workspace() -> sqlite3.Connection:
    conn = sqlite3.connect(WORKSPACE_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS rows (
            id INTEGER PRIMARY KEY,
            row_num INTEGER NOT NULL,
            source TEXT NOT NULL,
            draft TEXT DEFAULT '',
            translation TEXT DEFAULT '',
            key TEXT DEFAULT '',
            locked INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending'
        );
        CREATE TABLE IF NOT EXISTS project (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    conn.commit()
    return conn


def parse_input(filepath: str, source_col=None, draft_col=None,
                key_col=None, locked_col=None, mode=None) -> dict:
    """Parse input file. Returns metadata + loads rows into workspace DB."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {filepath}")

    conn = init_workspace()
    conn.execute("DELETE FROM rows")
    conn.execute("DELETE FROM project")
    conn.commit()

    # Fallback detection if any col not provided
    if source_col is None or draft_col is None or key_col is None or locked_col is None or mode is None:
        headers = get_file_headers(filepath)
        header_names = [h[1].lower() for h in headers]
        has_draft = any("draft" in h or "初译" in h or "mt" in h for h in header_names)

        def find_col(*candidates):
            for cand in candidates:
                for idx, name in headers:
                    if cand.lower() in name.lower():
                        return idx
            return None

        if source_col is None:
            source_col = find_col("source", "原文", "源语", "st", "source_text") or 1
        if draft_col is None:
            draft_col = find_col("draft", "初译", "mt", "machine") if has_draft else None
        if key_col is None:
            key_col = find_col("key", "id", "context", "键")
        if locked_col is None:
            locked_col = find_col("locked", "锁定", "skip", "ignore")
        if mode is None:
            mode = "optimize" if draft_col else "new"

    # Insert rows
    if path.suffix.lower() == ".csv":
        import csv
        with open(filepath, encoding="utf-8-sig", errors="replace") as f:
            reader = csv.reader(f)
            next(reader, None)  # skip header
            for i, row in enumerate(reader, start=2):
                _insert_row(conn, i, row, source_col, draft_col, key_col, locked_col)
    else:
        wb = load_workbook(filepath, read_only=True, data_only=True)
        ws = wb.active
        for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            _insert_row(conn, i, row, source_col, draft_col, key_col, locked_col)
        wb.close()

    # Save metadata
    conn.executemany("INSERT INTO project (key, value) VALUES (?, ?)", [
        ("input_file", str(path.name)),
        ("mode", mode),
        ("total_rows", str(conn.execute("SELECT COUNT(*) FROM rows").fetchone()[0])),
        ("locked_rows", str(conn.execute("SELECT COUNT(*) FROM rows WHERE locked=1").fetchone()[0])),
    ])
    conn.commit()
    conn.close()

    return {
        "file": path.name,
        "mode": mode,
        "source_col": source_col,
        "draft_col": draft_col,
        "key_col": key_col,
        "locked_col": locked_col,
    }


def _insert_row(conn, row_num, row, source_col, draft_col, key_col, locked_col):
    def get(col_idx):
        if col_idx is None or col_idx > len(row):
            return ""
        val = row[col_idx - 1]
        return str(val) if val is not None else ""

    source = get(source_col).strip()
    if not source:
        return
    draft = get(draft_col).strip() if draft_col else ""
    key = get(key_col).strip() if key_col else ""
    locked_raw = get(locked_col).strip().lower() if locked_col else ""
    locked = 1 if locked_raw in ("1", "true", "yes", "y", "是", "锁定") else 0

    conn.execute(
        "INSERT INTO rows (row_num, source, draft, key, locked) VALUES (?, ?, ?, ?, ?)",
        (row_num, source, draft, key, locked)
    )


def load_glossary(filepath: str, st_col: int = 1, tt_col: int = 2) -> list:
    """Load glossary as list of (source, target) tuples.
    Supports: .xlsx, .csv, .tsv, .txt (tab/=/|: delimited), .json
    """
    from engine import load_bilingual_file
    path = Path(filepath)
    suffix = path.suffix.lower()

    if suffix == ".json":
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return [(k.strip(), v.strip()) for k, v in data.items() if k and v]
        if isinstance(data, list):
            out = []
            for item in data:
                if isinstance(item, dict):
                    st = str(item.get("source", item.get("st", ""))).strip()
                    tt = str(item.get("target", item.get("tt", ""))).strip()
                    if st and tt:
                        out.append((st, tt))
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    st, tt = str(item[0]).strip(), str(item[1]).strip()
                    if st and tt:
                        out.append((st, tt))
            return out
        return []

    if suffix == ".tsv":
        rows = []
        with open(filepath, encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 2:
                    st, tt = parts[0].strip(), parts[1].strip()
                    if st and tt:
                        rows.append((st, tt))
        return rows

    if suffix == ".txt":
        rows = []
        delimiters = ["\t", "=", "|", ": "]
        with open(filepath, encoding="utf-8-sig", errors="replace") as f:
            lines = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
        # Auto-detect delimiter from first line
        chosen = None
        for d in delimiters:
            if lines and d in lines[0]:
                chosen = d
                break
        if chosen is None:
            chosen = "\t"
        for line in lines:
            if chosen in line:
                parts = line.split(chosen, 1)
                if len(parts) >= 2:
                    st, tt = parts[0].strip(), parts[1].strip()
                    if st and tt:
                        rows.append((st, tt))
        return rows

    # Fallback to xlsx / csv
    return load_bilingual_file(filepath, st_col, tt_col)


def load_knowledge_base(filepath: str) -> list:
    """Load knowledge base. Returns list of {category, note, text} dicts.
    Supports: .xlsx, .csv, .json, .txt, .md
    """
    path = Path(filepath)
    suffix = path.suffix.lower()

    if suffix == ".json":
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return [{"category": data.get("category", ""), "note": data.get("note", ""), "text": data.get("text", "")}]
        if isinstance(data, list):
            return [{"category": item.get("category", ""), "note": item.get("note", ""), "text": item.get("text", "")} for item in data]
        return []

    if suffix == ".txt":
        with open(filepath, encoding="utf-8-sig", errors="replace") as f:
            raw = f.read()
        entries = []
        # Split by delimiter lines (--- or blank line double break)
        blocks = [b.strip() for b in re.split(r"\n---+\n", raw) if b.strip()]
        if not blocks:
            blocks = [b.strip() for b in raw.split("\n\n") if b.strip()]
        for b in blocks:
            lines = [ln.strip() for ln in b.splitlines() if ln.strip()]
            category = lines[0] if lines else ""
            text = "\n".join(lines[1:]) if len(lines) > 1 else ""
            note = ""
            if ":" in category:
                category, note = category.split(":", 1)
                category = category.strip()
                note = note.strip()
            entries.append({"category": category, "note": note, "text": text})
        return entries

    if suffix == ".md":
        with open(filepath, encoding="utf-8-sig", errors="replace") as f:
            text = f.read().strip()
        return [{"category": "markdown", "note": path.stem, "text": text}]

    if suffix == ".csv":
        import csv
        with open(filepath, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            return [dict(r) for r in reader]

    # Fallback to xlsx
    wb = load_workbook(filepath, read_only=True, data_only=True)
    ws = wb.active
    headers = [str(c or "").strip() for c in next(ws.iter_rows(values_only=True))]
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        d = {}
        for h, v in zip(headers, row):
            d[h] = str(v) if v is not None else ""
        rows.append(d)
    wb.close()
    return rows


def save_project_meta(key: str, value: str):
    conn = sqlite3.connect(WORKSPACE_DB)
    conn.execute("INSERT OR REPLACE INTO project (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def get_project_meta(key: str) -> str | None:
    conn = sqlite3.connect(WORKSPACE_DB)
    row = conn.execute("SELECT value FROM project WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row[0] if row else None


def get_pending_rows() -> list:
    conn = sqlite3.connect(WORKSPACE_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM rows WHERE locked = 0 ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_row_result(row_id: int, translation: str, status: str = "done"):
    conn = sqlite3.connect(WORKSPACE_DB)
    conn.execute("UPDATE rows SET translation = ?, status = ? WHERE id = ?",
                 (translation, status, row_id))
    conn.commit()
    conn.close()
