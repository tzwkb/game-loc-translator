"""
corpus_store.py — Game localization corpus storage.
SQLite + FAISS for RAG retrieval.
Based on: bge-m3 embedding + IndexFlatIP.
"""

import os
import hashlib
import sqlite3
from pathlib import Path
import numpy as np
import faiss
from dataclasses import dataclass
from typing import Optional

import config

os.environ.setdefault("HF_HUB_OFFLINE", "1")

DB_PATH    = str(config.CORPUS_DB_PATH)
FAISS_PATH = str(config.CORPUS_FAISS_PATH)
VECTOR_DIM = config.VECTOR_DIM

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    conn = get_connection()
    conn.cursor().executescript(f"""
        CREATE TABLE IF NOT EXISTS corpus (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id    TEXT    NOT NULL DEFAULT '',
            game_type     TEXT    NOT NULL DEFAULT '',
            theme         TEXT    NOT NULL DEFAULT '',
            lang_pair     TEXT    NOT NULL DEFAULT '',
            source        TEXT    NOT NULL,
            target        TEXT    NOT NULL,
            quality_score REAL    NOT NULL DEFAULT 3.0,
            created_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_corpus_project   ON corpus(project_id);
        CREATE INDEX IF NOT EXISTS idx_corpus_game_type ON corpus(game_type);
        CREATE INDEX IF NOT EXISTS idx_corpus_theme     ON corpus(theme);
        CREATE INDEX IF NOT EXISTS idx_corpus_lang_pair ON corpus(lang_pair);
        CREATE TABLE IF NOT EXISTS query_cache (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            query_key  TEXT    NOT NULL UNIQUE,
            vector     BLOB    NOT NULL
        );
    """)
    conn.commit()
    conn.close()
    print(f"[corpus_store] DB initialized at {DB_PATH}")


# ---------------------------------------------------------------------------
# Embedding model (lazy singleton)
# ---------------------------------------------------------------------------
_model = None
_rag_disabled = False


def _is_sentence_transformers_model(path: Path) -> bool:
    """Check if a cache dir contains a sentence-transformers model."""
    if (path / "modules.json").exists():
        return True
    for sub in path.rglob("modules.json"):
        return True
    return False


def _scan_cached_models() -> list[str]:
    """Scan local caches for all sentence-transformers models."""
    found = set()

    torch_cache = Path(os.path.expanduser("~/.cache/torch/sentence_transformers"))
    if torch_cache.exists():
        for p in torch_cache.iterdir():
            if p.is_dir() and not p.name.startswith(".") and _is_sentence_transformers_model(p):
                found.add(p.name.replace("_", "/"))

    hf_home = os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface"))
    hf_hub = Path(hf_home) / "hub"
    if hf_hub.exists():
        for p in hf_hub.iterdir():
            if p.is_dir() and p.name.startswith("models--"):
                if not _is_sentence_transformers_model(p):
                    continue
                parts = p.name.replace("models--", "").split("--")
                if len(parts) >= 2:
                    found.add("/".join(parts))

    st_home = os.environ.get("SENTENCE_TRANSFORMERS_HOME")
    if st_home:
        st_path = Path(st_home)
        if st_path.exists():
            for p in st_path.iterdir():
                if p.is_dir() and not p.name.startswith(".") and _is_sentence_transformers_model(p):
                    found.add(p.name.replace("_", "/"))

    return sorted(found)


def _model_is_cached(model_name: str) -> bool:
    """Check if sentence-transformers model is already cached locally."""
    safe_name = model_name.replace("/", "_")
    candidates = []

    st_home = os.environ.get("SENTENCE_TRANSFORMERS_HOME")
    if st_home:
        candidates.append(Path(st_home) / safe_name)

    torch_cache = os.path.expanduser("~/.cache/torch/sentence_transformers")
    candidates.append(Path(torch_cache) / safe_name)

    hf_home = os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface"))
    candidates.append(Path(hf_home) / "hub" / f"models--{model_name.replace('/', '--')}")

    for p in candidates:
        if p.exists():
            return True
    return False


def get_embedding_model():
    global _model, _rag_disabled
    if _rag_disabled or not config.RAG_ENABLED:
        return None
    if _model is not None:
        return _model

    from sentence_transformers import SentenceTransformer
    import sys

    cached_models = _scan_cached_models()

    # Multiple models — ask user to pick
    if len(cached_models) > 1:
        print(f"[corpus_store] Found {len(cached_models)} cached embedding models:")
        for i, name in enumerate(cached_models, 1):
            marker = " (current)" if name == config.EMBEDDING_MODEL else ""
            print(f"  {i}. {name}{marker}")
        if sys.stdin.isatty():
            try:
                choice = input(
                    f"  Select model (1-{len(cached_models)}, or Enter for default {config.EMBEDDING_MODEL}): "
                ).strip()
                if choice:
                    idx = int(choice) - 1
                    if 0 <= idx < len(cached_models):
                        config.EMBEDDING_MODEL = cached_models[idx]
            except (ValueError, EOFError, KeyboardInterrupt):
                pass
        else:
            print(f"  Using default: {config.EMBEDDING_MODEL}")

    # No models — ask to download or disable RAG
    elif len(cached_models) == 0:
        print(f"[corpus_store] No embedding model found locally.")
        print(f"  Required: {config.EMBEDDING_MODEL} (~500MB)")
        if sys.stdin.isatty():
            print(f"\n  Download from HuggingFace now?")
            try:
                resp = input("  [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                resp = "n"
            if resp not in ("y", "yes", "是", "ok"):
                print("  RAG corpus disabled for this session.")
                _rag_disabled = True
                config.RAG_ENABLED = False
                return None
        else:
            print("  RAG corpus disabled (non-interactive session, model not cached).")
            _rag_disabled = True
            config.RAG_ENABLED = False
            return None

    # Single model different from default — use it
    elif len(cached_models) == 1 and cached_models[0] != config.EMBEDDING_MODEL:
        print(f"[corpus_store] Using cached model: {cached_models[0]}")
        config.EMBEDDING_MODEL = cached_models[0]

    # Load / download
    if not _model_is_cached(config.EMBEDDING_MODEL):
        offline_keys = ["HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"]
        old_values = {}
        for key in offline_keys:
            old_values[key] = os.environ.pop(key, None)
        try:
            print(f"[corpus_store] Downloading {config.EMBEDDING_MODEL} ...")
            _model = SentenceTransformer(config.EMBEDDING_MODEL)
        finally:
            for key, val in old_values.items():
                if val is not None:
                    os.environ[key] = val
        return _model

    print(f"[corpus_store] Loading {config.EMBEDDING_MODEL} ...")
    _model = SentenceTransformer(config.EMBEDDING_MODEL)
    return _model


def _print_install_hint():
    print("  To install manually, run:")
    print(f'  python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer(\'{config.EMBEDDING_MODEL}\')"')
    print("  Or set HF_HOME to a local mirror path if you have one.")


def embed(texts: list[str]) -> np.ndarray:
    model = get_embedding_model()
    if model is None:
        return np.zeros((len(texts), config.VECTOR_DIM), dtype=np.float32)
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return vectors.astype(np.float32)


def embed_with_cache(texts: list[str]) -> np.ndarray:
    model = get_embedding_model()
    if model is None:
        return np.zeros((len(texts), VECTOR_DIM), dtype=np.float32)
    keys = [hashlib.sha256(t.encode("utf-8")).hexdigest() for t in texts]
    conn = get_connection()
    placeholders = ",".join("?" * len(keys))
    rows = conn.execute(
        f"SELECT query_key, vector FROM query_cache WHERE query_key IN ({placeholders}) GROUP BY query_key",
        keys
    ).fetchall()
    conn.close()
    cached = {row["query_key"]: np.frombuffer(row["vector"], dtype=np.float32) for row in rows}

    result = np.zeros((len(texts), VECTOR_DIM), dtype=np.float32)
    miss_indices, miss_texts = [], []
    for i, key in enumerate(keys):
        if key in cached:
            result[i] = cached[key]
        else:
            miss_indices.append(i)
            miss_texts.append(texts[i])

    if miss_texts:
        new_vecs = embed(miss_texts)
        conn = get_connection()
        for idx, vec in zip(miss_indices, new_vecs):
            result[idx] = vec
            conn.execute(
                "INSERT OR REPLACE INTO query_cache (query_key, vector) VALUES (?, ?)",
                (keys[idx], vec.tobytes())
            )
        conn.commit()
        conn.close()
    return result


# ---------------------------------------------------------------------------
# FAISS index
# ---------------------------------------------------------------------------
_faiss_index: Optional[faiss.IndexIDMap] = None

def get_faiss_index() -> faiss.IndexIDMap:
    global _faiss_index
    if _faiss_index is not None:
        return _faiss_index
    if os.path.exists(FAISS_PATH):
        _faiss_index = faiss.read_index(FAISS_PATH)
    else:
        base = faiss.IndexFlatIP(VECTOR_DIM)
        _faiss_index = faiss.IndexIDMap(base)
    return _faiss_index


def save_faiss_index() -> None:
    index = get_faiss_index()
    faiss.write_index(index, FAISS_PATH)


# ---------------------------------------------------------------------------
# Case / Entry dataclass
# ---------------------------------------------------------------------------
@dataclass
class CorpusEntry:
    source: str
    target: str
    project_id: str = ""
    game_type: str = ""
    theme: str = ""
    lang_pair: str = ""
    quality_score: float = 3.0


def insert_entry(entry: CorpusEntry) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO corpus (project_id, game_type, theme, lang_pair, source, target, quality_score)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (entry.project_id, entry.game_type, entry.theme, entry.lang_pair,
          entry.source, entry.target, entry.quality_score))
    entry_id = cursor.lastrowid
    conn.commit()
    conn.close()

    vector = embed([f"{entry.source} | {entry.target}"])
    index = get_faiss_index()
    index.add_with_ids(vector, np.array([entry_id], dtype=np.int64))
    save_faiss_index()
    return entry_id


def insert_entries_batch(entries: list[CorpusEntry]) -> list[int]:
    if not entries:
        return []
    conn = get_connection()
    cursor = conn.cursor()
    ids = []
    for e in entries:
        cursor.execute("""
            INSERT INTO corpus (project_id, game_type, theme, lang_pair, source, target, quality_score)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (e.project_id, e.game_type, e.theme, e.lang_pair, e.source, e.target, e.quality_score))
        ids.append(cursor.lastrowid)
    conn.commit()
    conn.close()

    vectors = embed([f"{e.source} | {e.target}" for e in entries])
    index = get_faiss_index()
    index.add_with_ids(vectors, np.array(ids, dtype=np.int64))
    save_faiss_index()
    return ids


def get_entry_by_id(entry_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM corpus WHERE id = ?", (entry_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_entry(entry_id: int) -> bool:
    """Delete from SQLite + FAISS. Returns True if deleted."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM corpus WHERE id = ?", (entry_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()

    if deleted:
        index = get_faiss_index()
        index.remove_ids(np.array([entry_id], dtype=np.int64))
        save_faiss_index()
    return deleted
