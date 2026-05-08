#!/usr/bin/env python3
"""
cli.py — Unified command-line entry for game-loc-translator.
Usage: python cli.py <command> [args]

Commands:
  ingest      Parse input file + glossary + KB into workspace
  retrieve    RAG corpus search
  process     Execute batch translation/optimization via API
  glossary    Post-process glossary enforcement
  export      Write final output xlsx
  diff        Generate 4-column diff (optimize mode)
  corpus      Manage corpus (add / list / import)
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

# Ensure core/ is importable
sys.path.insert(0, str(Path(__file__).parent / "core"))

import config
from engine import init_api_log
from corpus_store import init_db as init_corpus_db


def cmd_ingest(args):
    from ingest import parse_input, load_glossary, load_knowledge_base, save_project_meta
    meta = parse_input(
        args.input,
        source_col=args.source_col,
        draft_col=args.draft_col,
        key_col=args.key_col,
        locked_col=args.locked_col,
    )
    print(f"[ingest] Mode: {meta['mode']}, Rows: {meta.get('total_rows', '?')}")

    if args.glossary:
        glossary = load_glossary(args.glossary, args.glossary_st_col, args.glossary_tt_col)
        save_project_meta("glossary_file", args.glossary)
        save_project_meta("glossary_count", str(len(glossary)))
        print(f"[ingest] Glossary: {len(glossary)} terms")

    if args.knowledge_base:
        kb = load_knowledge_base(args.knowledge_base)
        save_project_meta("kb_file", args.knowledge_base)
        save_project_meta("kb_count", str(len(kb)))
        print(f"[ingest] Knowledge Base: {len(kb)} entries")

    if args.project_id:
        save_project_meta("project_id", args.project_id)
    if args.game_type:
        save_project_meta("game_type", args.game_type)
    if args.theme:
        save_project_meta("theme", args.theme)
    if args.lang_pair:
        save_project_meta("lang_pair", args.lang_pair)

    # Output metadata JSON for agent
    meta_path = config.WORKSPACE_DIR / "project_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ingest] Meta -> {meta_path}")


def cmd_retrieve(args):
    from corpus_search import search_corpus
    hits = search_corpus(
        query_text=args.query,
        game_type=args.game_type or "",
        theme=args.theme or "",
        lang_pair=args.lang_pair or "",
        top_k=args.top_k,
    )
    out = []
    for h in hits:
        out.append({
            "id": h.entry_id,
            "similarity": round(h.similarity, 4),
            "source": h.source,
            "target": h.target,
            "quality": h.quality_score,
        })
    output = json.dumps(out, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"[retrieve] {len(out)} hits -> {args.output}")
    else:
        print(output)


async def cmd_translate_async(args):
    import asyncio
    import sqlite3
    from ingest import get_pending_rows, get_project_meta, load_knowledge_base
    from engine import translate_batch, find_matching_terms
    from corpus_search import search_corpus
    from export import export_xlsx

    rows = get_pending_rows()
    if not rows:
        print("[process] No pending rows.")
        # Still try auto-export in case everything was already done
        _auto_export()
        return

    project_id = get_project_meta("project_id") or ""
    game_type  = get_project_meta("game_type") or ""
    theme      = get_project_meta("theme") or ""
    lang_pair  = get_project_meta("lang_pair") or ""
    mode       = get_project_meta("mode") or "new"
    user_style_anchor = args.style_anchor or ""

    # Load glossary (resolve relative paths against project root)
    glossary = []
    gfile = get_project_meta("glossary_file")
    if gfile:
        from ingest import load_glossary
        gpath = Path(gfile)
        if not gpath.is_absolute():
            gpath = config.BASE_DIR / gfile
        if gpath.exists():
            glossary = load_glossary(str(gpath))
        else:
            print(f"[process] Glossary not found: {gpath}")

    db_path = str(config.WORKSPACE_DIR / "workspace.db")

    # Pre-check corpus size to avoid loading embedding model for empty/small corpus
    corpus_count = 0
    try:
        conn = sqlite3.connect(config.CORPUS_DB_PATH)
        corpus_count = conn.execute("SELECT COUNT(*) FROM corpus").fetchone()[0]
        conn.close()
    except Exception:
        pass
    skip_rag = corpus_count < 10
    if skip_rag:
        print(f"[process] Corpus has {corpus_count} entries (< 10), skipping RAG.")

    # Migrate DB: add change_type / change_reason if missing
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    for col in ["change_type", "change_reason"]:
        try:
            c.execute(f"ALTER TABLE rows ADD COLUMN {col} TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()

    # -------------------------------------------------------------------------
    # Helper: translate one row and update DB
    # -------------------------------------------------------------------------
    async def _translate_one(row, style_anchor_to_use, sem):
        async with sem:
            item = {
                "label": row["id"],
                "source": row["source"],
                "draft": row.get("draft", ""),
                "key": row.get("key", ""),
            }
            glossary_hints = find_matching_terms(row["source"], glossary)
            kb_snippets = []
            kb_file = get_project_meta("kb_file")
            if kb_file:
                kb_path = Path(kb_file)
                if not kb_path.is_absolute():
                    kb_path = config.BASE_DIR / kb_file
                if kb_path.exists():
                    for entry in load_knowledge_base(str(kb_path)):
                        cat = entry.get("category", "")
                        text = entry.get("text", "")
                        if cat and text:
                            kb_snippets.append((cat, text))
            rag_refs = []
            if not skip_rag:
                hits = search_corpus(row["source"], game_type, theme, lang_pair, top_k=3)
                for h in hits:
                    if h.similarity >= config.RAG_SIM_THRESHOLD:
                        rag_refs.append((h.source, h.target))

            best_result = {}
            truncated = False
            for attempt in range(3):
                results = await translate_batch(
                    batch_items=[item],
                    mode=mode,
                    project_id=project_id,
                    style_anchor=style_anchor_to_use,
                    glossary_hints=glossary_hints,
                    kb_snippets=kb_snippets,
                    rag_refs=rag_refs,
                    semaphore=None,
                )
                # Systematic truncation: don't waste retries
                if results.pop("_truncated", False):
                    truncated = True
                    print(f"    [WARN] Row {item['label']} truncated (max_tokens insufficient)")
                    break
                data = results.get(item["label"], {})
                text = data.get("translation") if isinstance(data, dict) else str(data)
                if text:
                    best_result = data if isinstance(data, dict) else {"translation": text}
                    break
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)

            text = best_result.get("translation", "") if isinstance(best_result, dict) else str(best_result)
            if mode == "optimize" and isinstance(best_result, dict):
                ctype = best_result.get("change_type", "") or ""
                creason = best_result.get("change_reason", "") or ""
            else:
                ctype = ""
                creason = ""
            status = "done" if text else "failed"

            conn = sqlite3.connect(db_path)
            conn.execute(
                "UPDATE rows SET translation = ?, status = ?, change_type = ?, change_reason = ? WHERE id = ?",
                (text, status, ctype, creason, item["label"])
            )
            conn.commit()
            conn.close()
            return status, text

    # -------------------------------------------------------------------------
    # Step 1: Identify first 10 non-locked rows as style anchor
    # -------------------------------------------------------------------------
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    anchor_rows = conn.execute(
        "SELECT * FROM rows WHERE locked = 0 ORDER BY row_num LIMIT 10"
    ).fetchall()
    conn.close()
    anchor_rows = [dict(r) for r in anchor_rows]

    effective_style_anchor = user_style_anchor

    if anchor_rows:
        pending_anchors = [r for r in anchor_rows if r.get("status") != "done"]
        if pending_anchors:
            print(f"[process] Translating {len(pending_anchors)} anchor rows (first 10) to establish style baseline...")
            anchor_sem = asyncio.Semaphore(5)
            await asyncio.gather(*[
                _translate_one(r, user_style_anchor, anchor_sem) for r in pending_anchors
            ])
            print("[process] Anchor rows done.")

        # Re-read anchor translations from DB
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        refreshed = conn.execute(
            "SELECT * FROM rows WHERE locked = 0 ORDER BY row_num LIMIT 10"
        ).fetchall()
        conn.close()
        refreshed = [dict(r) for r in refreshed]

        samples = []
        for r in refreshed:
            trans = r["translation"] or ""
            if trans:
                if mode == "optimize":
                    samples.append(
                        f"SOURCE: {r['source']}\nDRAFT: {r.get('draft', '')}\nOPTIMIZED: {trans}"
                    )
                else:
                    samples.append(
                        f"SOURCE: {r['source']}\nTRANSLATION: {trans}"
                    )
        if samples:
            auto_anchor = "【风格参考——前10行基准译文】\n" + "\n---\n".join(samples)
            if user_style_anchor:
                effective_style_anchor = user_style_anchor + "\n\n" + auto_anchor
            else:
                effective_style_anchor = auto_anchor
            print(f"[process] Built style anchor from first {len(samples)} rows.")

    # -------------------------------------------------------------------------
    # Step 2: Translate remaining pending/failed rows
    # -------------------------------------------------------------------------
    remaining = get_pending_rows()
    if remaining:
        print(f"[process] {len(remaining)} remaining rows -> row-by-row mode")
        main_sem = asyncio.Semaphore(config.MAX_WORKERS)

        async def _process_row(idx, total, row):
            status, _ = await _translate_one(row, effective_style_anchor, main_sem)
            print(f"  {idx}/{total} done ({status})", flush=True)

        tasks = [asyncio.create_task(_process_row(i + 1, len(remaining), r)) for i, r in enumerate(remaining)]
        await asyncio.gather(*tasks)
        print(f"[process] Completed {len(remaining)} rows.", flush=True)
    else:
        print("[process] No remaining rows to translate.")

    # -------------------------------------------------------------------------
    # Step 3: Auto-export
    # -------------------------------------------------------------------------
    _auto_export()


def _auto_export():
    """Export results if input file is recorded."""
    from ingest import get_project_meta
    input_file = get_project_meta("input_file")
    if not input_file:
        print("[process] No input file recorded, skipping auto-export.")
        return
    from export import export_xlsx
    mode = get_project_meta("mode") or "new"
    suffix = "_translated" if mode == "new" else "_optimized"
    out_xlsx = config.OUTPUT_DIR / (Path(input_file).stem + suffix + ".xlsx")
    export_xlsx(str(out_xlsx), mode)
    print(f"[process] Auto-exported -> {out_xlsx}")


def cmd_translate(args):
    import asyncio
    init_api_log()
    asyncio.run(cmd_translate_async(args))


def cmd_glossary(args):
    from ingest import get_project_meta
    from glossary import enforce_glossary
    import sqlite3

    gfile = get_project_meta("glossary_file")
    if not gfile:
        print("[glossary] No glossary loaded.")
        return

    from ingest import load_glossary
    gpath = Path(gfile)
    if not gpath.is_absolute():
        gpath = config.BASE_DIR / gfile
    if not gpath.exists():
        print(f"[glossary] Glossary not found: {gpath}")
        return
    glossary = load_glossary(str(gpath))

    db_path = str(config.WORKSPACE_DIR / "workspace.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, translation FROM rows WHERE status = 'done'").fetchall()
    conn.close()

    translations = {r["id"]: r["translation"] for r in rows}
    enforced, log = enforce_glossary(translations, glossary)

    conn = sqlite3.connect(db_path)
    for row_id, text in enforced.items():
        if row_id in log:
            # Build change_reason from log
            terms = [f"{item['term']}→{item['replacement']}" for item in log[row_id]]
            reason = "术语修正：" + ", ".join(terms)
            conn.execute("UPDATE rows SET translation = ?, change_type = 'terminology_fix', change_reason = ? WHERE id = ?", (text, reason, row_id))
        else:
            conn.execute("UPDATE rows SET translation = ? WHERE id = ?", (text, row_id))
    conn.commit()
    conn.close()
    print(f"[glossary] Enforced on {len(enforced)} rows, {len(log)} rows with replacements")


def cmd_changed_terms(args):
    """Export changed terms report (Mode B)."""
    from ingest import get_project_meta
    from glossary import detect_changed_terms, export_changed_terms
    import sqlite3

    gfile = get_project_meta("glossary_file")
    if not gfile:
        print("[changed-terms] No glossary loaded.")
        return

    from ingest import load_glossary
    gpath = Path(gfile)
    if not gpath.is_absolute():
        gpath = config.BASE_DIR / gfile
    if not gpath.exists():
        print(f"[changed-terms] Glossary not found: {gpath}")
        return
    glossary = load_glossary(str(gpath))

    db_path = str(config.WORKSPACE_DIR / "workspace.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT row_num, source, draft, translation FROM rows WHERE status = 'done'").fetchall()
    conn.close()

    # Convert to list of dicts
    row_data = []
    for r in rows:
        row_data.append({
            "row_num": r["row_num"],
            "source": r["source"],
            "draft": r["draft"],
            "optimized": r["translation"]
        })

    changed_terms = detect_changed_terms(row_data, glossary)

    if not changed_terms:
        print("[changed-terms] No terminology changes detected.")
        return

    # Export to xlsx
    input_file = get_project_meta("input_file")
    if input_file:
        out_path = config.OUTPUT_DIR / (Path(input_file).stem + "_changed_terms.xlsx")
    else:
        out_path = config.OUTPUT_DIR / "changed_terms.xlsx"

    export_changed_terms(changed_terms, str(out_path))
    print(f"[changed-terms] Exported {len(changed_terms)} changed terms to {out_path}")


def cmd_term_hits(args):
    """Export term hits report (Mode A)."""
    from ingest import get_project_meta
    from glossary import detect_term_hits, export_term_hits
    import sqlite3

    gfile = get_project_meta("glossary_file")
    if not gfile:
        print("[term-hits] No glossary loaded.")
        return

    from ingest import load_glossary
    gpath = Path(gfile)
    if not gpath.is_absolute():
        gpath = config.BASE_DIR / gfile
    if not gpath.exists():
        print(f"[term-hits] Glossary not found: {gpath}")
        return
    glossary = load_glossary(str(gpath))

    db_path = str(config.WORKSPACE_DIR / "workspace.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT row_num, source, translation FROM rows WHERE status = 'done'").fetchall()
    conn.close()

    # Convert to list of dicts
    row_data = []
    for r in rows:
        row_data.append({
            "row_num": r["row_num"],
            "source": r["source"],
            "translation": r["translation"]
        })

    term_hits = detect_term_hits(row_data, glossary)

    if not term_hits:
        print("[term-hits] No term hits detected.")
        return

    # Export to xlsx
    input_file = get_project_meta("input_file")
    if input_file:
        out_path = config.OUTPUT_DIR / (Path(input_file).stem + "_term_hits.xlsx")
    else:
        out_path = config.OUTPUT_DIR / "term_hits.xlsx"

    export_term_hits(term_hits, str(out_path))
    print(f"[term-hits] Exported {len(term_hits)} term hits to {out_path}")


def cmd_export(args):
    from ingest import get_project_meta
    from export import export_xlsx, export_csv

    input_file = get_project_meta("input_file")
    if not input_file:
        print("[export] No input file recorded. Run ingest first.")
        return

    mode = get_project_meta("mode") or "new"
    suffix = "_translated" if mode == "new" else "_optimized"
    out_xlsx = config.OUTPUT_DIR / (Path(input_file).stem + suffix + ".xlsx")
    export_xlsx(str(out_xlsx), mode)

    if args.csv:
        out_csv = config.OUTPUT_DIR / (Path(input_file).stem + suffix + ".csv")
        export_csv(str(out_csv))


def cmd_diff(args):
    from diff import generate_diff
    from ingest import get_project_meta
    input_file = get_project_meta("input_file")
    if not input_file:
        print("[diff] No input file recorded.")
        return
    out_path = config.OUTPUT_DIR / (Path(input_file).stem + "_diff.xlsx")
    generate_diff(str(out_path))


def cmd_status(args):
    import sqlite3
    db_path = str(config.WORKSPACE_DIR / "workspace.db")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT status, COUNT(*) FROM rows GROUP BY status")
    for r in c.fetchall():
        print(f"  {r[0]}: {r[1]}")
    c.execute("SELECT COUNT(*) FROM rows")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM rows WHERE locked = 1")
    locked = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM rows WHERE translation != '' AND translation IS NOT NULL")
    translated = c.fetchone()[0]
    conn.close()
    print(f"  total: {total}, locked: {locked}, translated: {translated}")


def _check_gate(required_files: list, required_db_checks: list = None) -> bool:
    """Check prerequisite files and DB states. Print errors and return False if any missing."""
    missing = []
    for f in required_files:
        if not Path(f).exists():
            missing.append(f"file missing: {f}")
    if required_db_checks:
        db_path = str(config.WORKSPACE_DIR / "workspace.db")
        if not Path(db_path).exists():
            missing.append("DB missing: workspace.db")
        else:
            conn = sqlite3.connect(db_path)
            for sql, desc in required_db_checks:
                row = conn.execute(sql).fetchone()
                if not row or row[0] == 0:
                    missing.append(f"DB state: {desc}")
            conn.close()
    if missing:
        print("[GATE] Prerequisites not met:")
        for m in missing:
            print(f"  - {m}")
        return False
    return True


def cmd_scout(args):
    if not _check_gate([args.input]):
        return
    from scout import run_scout
    report = run_scout(args.input, args.glossary, args.knowledge_base)
    if report:
        print(f"[scout] Genre: {report.get('genre', '?')}, Tone: {report.get('tone', '?')}")


def cmd_qa(args):
    db_checks = [
        ("SELECT COUNT(*) FROM rows WHERE status = 'done'", "no done rows"),
    ]
    if not _check_gate([], db_checks):
        return
    from qa import run_qa
    report = run_qa(args.glossary)
    if report:
        print(f"[qa] Overall score: {report.get('overall_score', '?')}, Failed: {len(report.get('failed_rows', []))}")


def cmd_doctor(args):
    """Check environment, dependencies, API connectivity."""
    import importlib.util, sys, os, subprocess
    print("[doctor] Checking environment...")

    # Python version
    py_ok = sys.version_info >= (3, 10)
    print(f"  Python {sys.version_info.major}.{sys.version_info.minor}: {'OK' if py_ok else 'FAIL (>=3.10 required)'}")

    # Dependencies
    deps = ["openai", "openpyxl", "numpy"]
    for dep in deps:
        spec = importlib.util.find_spec(dep)
        print(f"  {dep}: {'OK' if spec else 'MISSING'}")

    # API connectivity
    print(f"  API base: {config.API_BASE_URL}")
    key_set = bool(config.API_KEY and not config.API_KEY.startswith("your-"))
    print(f"  API key: {'SET' if key_set else 'NOT SET'}")
    if key_set:
        try:
            import urllib.request
            req = urllib.request.Request(
                config.API_BASE_URL.replace("/v1", "/v1/models"),
                headers={"Authorization": f"Bearer {config.API_KEY}"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                print(f"  API ping: OK ({resp.status})")
        except Exception as e:
            print(f"  API ping: FAIL ({e})")

    # Directories
    for d in [config.INPUT_DIR, config.OUTPUT_DIR, config.WORKSPACE_DIR, config.LOG_DIR]:
        print(f"  {d.name}: {'OK' if d.exists() else 'CREATED'}")
        d.mkdir(parents=True, exist_ok=True)

    print("[doctor] Done.")


def cmd_run(args):
    """One-shot: ingest -> process -> glossary -> export."""
    print("[run] Starting full pipeline...")
    cmd_ingest(args)
    cmd_translate(args)
    cmd_glossary(args)

    # Mode-specific reports
    from ingest import get_project_meta
    mode = get_project_meta("mode") or "new"
    if mode == "new":
        cmd_term_hits(args)
    else:
        cmd_changed_terms(args)

    cmd_export(args)
    print("[run] Pipeline complete.")


def cmd_project(args):
    """Manage project profiles."""
    import json
    profiles_path = config.PROJECT_PROFILES

    if args.action == "list":
        if not profiles_path.exists():
            print("[project] No projects found.")
            return
        data = json.loads(profiles_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = [data]
        for p in data:
            print(f"  {p.get('project_id', '?')}: {p.get('file', '?')} ({p.get('mode', '?')})")

    elif args.action == "switch":
        # Copy selected project's workspace.db and meta
        print(f"[project] Switch not yet implemented. Select by re-running ingest with --project-id.")


def cmd_corpus(args):
    from corpus_store import init_db, insert_entry, get_connection
    init_db()

    if args.action == "add":
        from corpus_store import CorpusEntry
        e = CorpusEntry(
            source=args.source,
            target=args.target,
            project_id=args.project_id or "",
            game_type=args.game_type or "",
            theme=args.theme or "",
            lang_pair=args.lang_pair or "",
            quality_score=args.quality or 3.0,
        )
        eid = insert_entry(e)
        print(f"[corpus] Added entry id={eid}")

    elif args.action == "list":
        conn = get_connection()
        rows = conn.execute("SELECT * FROM corpus ORDER BY id DESC LIMIT ?", (args.limit or 20,)).fetchall()
        conn.close()
        for r in rows:
            print(f"  [{r['id']}] ({r['game_type']}/{r['theme']}/{r['lang_pair']}) {r['source'][:40]} -> {r['target'][:40]}")

    elif args.action == "import":
        import json
        path = Path(args.file)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        from corpus_store import CorpusEntry, insert_entries_batch
        entries = [CorpusEntry(**item) for item in data]
        ids = insert_entries_batch(entries)
        print(f"[corpus] Imported {len(ids)} entries")

    elif args.action == "delete":
        from corpus_store import delete_entry
        deleted = delete_entry(args.id)
        if deleted:
            print(f"[corpus] Deleted entry id={args.id}")
        else:
            print(f"[corpus] Entry id={args.id} not found")

    elif args.action == "export":
        import json
        conn = get_connection()
        rows = conn.execute("SELECT * FROM corpus").fetchall()
        conn.close()
        out = [dict(r) for r in rows]
        out_path = Path(args.file or config.OUTPUT_DIR / "corpus_export.json")
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[corpus] Exported {len(out)} entries -> {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Game Localization Translator CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # ingest
    p = sub.add_parser("ingest", help="Parse input files")
    p.add_argument("--input", required=True, help="Input xlsx/csv/txt")
    p.add_argument("--glossary", help="Glossary xlsx/csv/txt/json/tsv")
    p.add_argument("--glossary-st-col", type=int, default=1)
    p.add_argument("--glossary-tt-col", type=int, default=2)
    p.add_argument("--knowledge-base", help="Knowledge base xlsx/csv/txt/json/md")
    p.add_argument("--source-col", type=int, help="1-based column index for source text")
    p.add_argument("--draft-col", type=int, help="1-based column index for draft/MT text")
    p.add_argument("--key-col", type=int, help="1-based column index for key/id")
    p.add_argument("--locked-col", type=int, help="1-based column index for locked flag")
    p.add_argument("--project-id", help="Project identifier")
    p.add_argument("--game-type", help="e.g. RPG, SLG, ACT")
    p.add_argument("--theme", help="e.g. wuxia, sci-fi, fantasy")
    p.add_argument("--lang-pair", help="e.g. EN-ZH, JA-ZH")

    # scout
    p = sub.add_parser("scout", help="Context analysis (multi-agent)")
    p.add_argument("--input", required=True, help="Input file")
    p.add_argument("--glossary", help="Glossary file")
    p.add_argument("--knowledge-base", help="Knowledge base file")

    # qa
    p = sub.add_parser("qa", help="Quality assurance (multi-agent)")
    p.add_argument("--glossary", help="Glossary file for terminology check")

    # retrieve
    p = sub.add_parser("retrieve", help="RAG corpus search")
    p.add_argument("--query", required=True)
    p.add_argument("--game-type", default="")
    p.add_argument("--theme", default="")
    p.add_argument("--lang-pair", default="")
    p.add_argument("--top-k", type=int, default=3)
    p.add_argument("--output", help="Write JSON results to file")

    # process
    p = sub.add_parser("process", help="Run translation/optimization")
    # strong model parameter removed — unified model only
    p.add_argument("--style-anchor", default="", help="Style baseline text")
    p.add_argument("--limit-batches", type=int, default=0, help="Limit number of batches (0 = no limit)")

    # glossary
    sub.add_parser("glossary", help="Enforce glossary replacements")

    # changed-terms
    sub.add_parser("changed-terms", help="Export changed terms report")

    # term-hits
    sub.add_parser("term-hits", help="Export term hits report")

    # export
    p = sub.add_parser("export", help="Export final results")
    p.add_argument("--csv", action="store_true", help="Also export CSV")

    # diff
    sub.add_parser("diff", help="Generate diff report")

    # status
    sub.add_parser("status", help="Show workspace row status")

    # doctor
    sub.add_parser("doctor", help="Check environment and dependencies")

    # run
    p = sub.add_parser("run", help="Full pipeline: ingest + process + glossary + export")
    p.add_argument("--input", required=True, help="Input file")
    p.add_argument("--glossary", help="Glossary file")
    p.add_argument("--glossary-st-col", type=int, default=1)
    p.add_argument("--glossary-tt-col", type=int, default=2)
    p.add_argument("--knowledge-base", help="Knowledge base file")
    p.add_argument("--source-col", type=int)
    p.add_argument("--draft-col", type=int)
    p.add_argument("--key-col", type=int)
    p.add_argument("--locked-col", type=int)
    p.add_argument("--project-id", help="Project identifier")
    p.add_argument("--game-type", help="e.g. RPG, SLG, ACT")
    p.add_argument("--theme", help="e.g. wuxia, sci-fi, fantasy")
    p.add_argument("--lang-pair", help="e.g. EN-ZH, JA-ZH")
    p.add_argument("--style-anchor", default="", help="Style baseline text")
    p.add_argument("--csv", action="store_true", help="Also export CSV")

    # project
    p = sub.add_parser("project", help="Project management")
    p.add_argument("action", choices=["list", "switch"])
    p.add_argument("--id", help="Project ID to switch to")

    # corpus
    p = sub.add_parser("corpus", help="Corpus management")
    p.add_argument("action", choices=["add", "list", "import", "delete", "export"])
    p.add_argument("--source", help="For add")
    p.add_argument("--target", help="For add")
    p.add_argument("--project-id", default="")
    p.add_argument("--game-type", default="")
    p.add_argument("--theme", default="")
    p.add_argument("--lang-pair", default="")
    p.add_argument("--quality", type=float, default=3.0)
    p.add_argument("--file", help="For import/export: JSON file path")
    p.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()

    if args.command == "ingest":
        cmd_ingest(args)
    elif args.command == "retrieve":
        cmd_retrieve(args)
    elif args.command == "process":
        cmd_translate(args)
    elif args.command == "glossary":
        cmd_glossary(args)
    elif args.command == "changed-terms":
        cmd_changed_terms(args)
    elif args.command == "term-hits":
        cmd_term_hits(args)
    elif args.command == "export":
        cmd_export(args)
    elif args.command == "diff":
        cmd_diff(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "corpus":
        cmd_corpus(args)
    elif args.command == "doctor":
        cmd_doctor(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "project":
        cmd_project(args)
    elif args.command == "scout":
        cmd_scout(args)
    elif args.command == "qa":
        cmd_qa(args)


if __name__ == "__main__":
    main()
