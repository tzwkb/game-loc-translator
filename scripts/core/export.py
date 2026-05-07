"""
export.py — Export final results to xlsx/csv.
"""

import csv
from pathlib import Path
from openpyxl import Workbook, load_workbook
from engine import get_cell_text
import sqlite3

import config
WORKSPACE_DB = str(config.WORKSPACE_DIR / "workspace.db")


def export_xlsx(input_path: str, output_path: str, mode: str = "new"):
    """Read workspace results and write to output xlsx."""
    conn = sqlite3.connect(WORKSPACE_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM rows ORDER BY row_num").fetchall()
    conn.close()

    # Load original to preserve structure
    wb = load_workbook(input_path)
    ws = wb.active

    # Find or create output column
    out_col = None
    for c in range(1, ws.max_column + 1):
        val = get_cell_text(ws.cell(row=1, column=c))
        if val.lower() in ("translation", "optimized", "译文", "优化"):
            out_col = c
            break
    if out_col is None:
        out_col = ws.max_column + 1
        ws.cell(row=1, column=out_col).value = "Translation" if mode == "new" else "Optimized"

    # Write results
    row_by_num = {r["row_num"]: dict(r) for r in rows}
    for row_idx in range(2, ws.max_row + 1):
        r = row_by_num.get(row_idx)
        if r:
            ws.cell(row=row_idx, column=out_col).value = r.get("translation", "")

    wb.save(output_path)
    print(f"[export] Saved -> {output_path}")


def export_csv(output_path: str):
    conn = sqlite3.connect(WORKSPACE_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT row_num, source, draft, translation, status FROM rows ORDER BY row_num").fetchall()
    conn.close()

    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["row_num", "source", "draft", "translation", "status"])
        for r in rows:
            writer.writerow([r["row_num"], r["source"], r["draft"], r["translation"], r["status"]])
    print(f"[export] Saved -> {output_path}")
