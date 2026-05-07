#!/usr/bin/env python3
"""
cli.py — Unified command-line entry for game-loc-translator.
Usage: python cli.py <command> [args]

Commands:
  ingest      Parse input file + glossary + KB into workspace
  retrieve    RAG corpus search
  translate   Execute batch translation/optimization via API
  glossary    Post-process glossary enforcement
  export      Write final output xlsx
  diff        Generate 4-column diff (optimize mode)
  corpus      Manage corpus (add / list / import)
"""

import argparse
import json
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
    print(json.dumps(out, ensure_ascii=False, indent=2))


async def cmd_translate_async(args):
    import asyncio
    from ingest import get_pending_rows, update_row_result, get_project_meta
    from engine import translate_batch, find_matching_terms
    from corpus_search import search_corpus

    rows = get_pending_rows()
    if not rows:
        print("[translate] No pending rows.")
        return

    project_id = get_project_meta("project_id") or ""
    game_type  = get_project_meta("game_type") or ""
    theme      = get_project_meta("theme") or ""
    lang_pair  = get_project_meta("lang_pair") or ""
    mode       = get_project_meta("mode") or "new"
    style_anchor = args.style_anchor or ""

    # Load glossary
    glossary = []
    gfile = get_project_meta("glossary_file")
    if gfile:
        from ingest import load_glossary
        glossary = load_glossary(gfile)

    # Batch preparation
    batch_size = config.BATCH_SIZE
    semaphore = asyncio.Semaphore(config.MAX_WORKERS)

    # Group rows into batches
    batches = []
    current = []
    for r in rows:
        current.append({
            "label": r["id"],
            "source": r["source"],
            "draft": r.get("draft", ""),
            "key": r.get("key", ""),
        })
        if len(current) >= batch_size:
            batches.append(current)
            current = []
    if current:
        batches.append(current)

    print(f"[translate] {len(rows)} rows -> {len(batches)} batches")

    # Process batches
    for i, batch in enumerate(batches, 1):
        # Per-batch glossary hints
        batch_text = " ".join(r["source"] for r in batch)
        glossary_hints = find_matching_terms(batch_text, glossary)

        # Per-batch RAG
        rag_refs = []
        if len(batch) > 0:
            # Use first sentence as query proxy
            hits = search_corpus(batch[0]["source"], game_type, theme, lang_pair, top_k=3)
            for h in hits:
                if h.similarity >= config.RAG_SIM_THRESHOLD:
                    rag_refs.append((h.source, h.target))

        results = await translate_batch(
            batch_items=batch,
            mode=mode,
            project_id=project_id,
            style_anchor=style_anchor,
            glossary_hints=glossary_hints,
            rag_refs=rag_refs,
            semaphore=semaphore,
        )

        for item in batch:
            row_id = item["label"]
            text = results.get(row_id)
            if text:
                update_row_result(row_id, text, "done")
            else:
                update_row_result(row_id, "", "failed")

        print(f"  Batch {i}/{len(batches)} done")


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
    glossary = load_glossary(gfile)

    import config
    db_path = str(config.WORKSPACE_DIR / "workspace.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, translation FROM rows WHERE status = 'done'").fetchall()
    conn.close()

    translations = {r["id"]: r["translation"] for r in rows}
    enforced = enforce_glossary(translations, glossary)

    conn = sqlite3.connect(db_path)
    for row_id, text in enforced.items():
        conn.execute("UPDATE rows SET translation = ? WHERE id = ?", (text, row_id))
    conn.commit()
    conn.close()
    print(f"[glossary] Enforced on {len(enforced)} rows")


def cmd_export(args):
    from ingest import get_project_meta
    from export import export_xlsx, export_csv

    input_file = get_project_meta("input_file")
    if not input_file:
        print("[export] No input file recorded. Run ingest first.")
        return

    mode = get_project_meta("mode") or "new"
    out_xlsx = config.OUTPUT_DIR / (Path(input_file).stem + config.OUTPUT_SUFFIX + ".xlsx")
    export_xlsx(str(config.INPUT_DIR / input_file), str(out_xlsx), mode)

    if args.csv:
        out_csv = config.OUTPUT_DIR / (Path(input_file).stem + config.OUTPUT_SUFFIX + ".csv")
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

    # retrieve
    p = sub.add_parser("retrieve", help="RAG corpus search")
    p.add_argument("--query", required=True)
    p.add_argument("--game-type", default="")
    p.add_argument("--theme", default="")
    p.add_argument("--lang-pair", default="")
    p.add_argument("--top-k", type=int, default=3)

    # translate
    p = sub.add_parser("translate", help="Run translation/optimization")
    # strong model parameter removed — unified model only
    p.add_argument("--style-anchor", default="", help="Style baseline text")

    # glossary
    sub.add_parser("glossary", help="Enforce glossary replacements")

    # export
    p = sub.add_parser("export", help="Export final results")
    p.add_argument("--csv", action="store_true", help="Also export CSV")

    # diff
    sub.add_parser("diff", help="Generate diff report")

    # corpus
    p = sub.add_parser("corpus", help="Corpus management")
    p.add_argument("action", choices=["add", "list", "import", "delete"])
    p.add_argument("--source", help="For add")
    p.add_argument("--target", help="For add")
    p.add_argument("--project-id", default="")
    p.add_argument("--game-type", default="")
    p.add_argument("--theme", default="")
    p.add_argument("--lang-pair", default="")
    p.add_argument("--quality", type=float, default=3.0)
    p.add_argument("--file", help="For import: JSON file path")
    p.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()

    if args.command == "ingest":
        cmd_ingest(args)
    elif args.command == "retrieve":
        cmd_retrieve(args)
    elif args.command == "translate":
        cmd_translate(args)
    elif args.command == "glossary":
        cmd_glossary(args)
    elif args.command == "export":
        cmd_export(args)
    elif args.command == "diff":
        cmd_diff(args)
    elif args.command == "corpus":
        cmd_corpus(args)


if __name__ == "__main__":
    main()
