#!/usr/bin/env python3
"""
reprocess_row.py — Reprocess a single row: reset status -> process -> glossary -> export.
Usage: python reprocess_row.py <row_id>
"""

import sqlite3
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "core"))

import config
from engine import init_api_log


def reset_row_status(row_id: int, status: str = "pending"):
    db_path = str(config.WORKSPACE_DIR / "workspace.db")
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE rows SET status = ? WHERE id = ?", (status, row_id))
    conn.commit()
    conn.close()
    print(f"[reset] Row {row_id} status -> {status}")


def run_process():
    from cli import cmd_translate_async
    import argparse
    args = argparse.Namespace(style_anchor="", limit_batches=0)
    init_api_log()
    asyncio.run(cmd_translate_async(args))


def run_glossary():
    from cli import cmd_glossary
    import argparse
    args = argparse.Namespace()
    cmd_glossary(args)


def run_export():
    from cli import cmd_export
    import argparse
    args = argparse.Namespace(csv=False)
    cmd_export(args)


def verify_row(row_id: int):
    db_path = str(config.WORKSPACE_DIR / "workspace.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id, row_num, status, translation FROM rows WHERE id = ?", (row_id,)
    ).fetchone()
    conn.close()
    if row:
        print(f"[verify] Row {row_id} (row_num={row['row_num']}): status={row['status']}")
        print(f"  translation: {row['translation'][:120]}...")
    else:
        print(f"[verify] Row {row_id} not found")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python reprocess_row.py <row_id>")
        sys.exit(1)

    row_id = int(sys.argv[1])
    print(f"=== Reprocessing Row {row_id} ===")

    reset_row_status(row_id)
    run_process()
    run_glossary()
    run_export()
    verify_row(row_id)

    print(f"=== Done ===")
