"""
corpus_search.py — RAG retrieval for game localization corpus.
Implements vector search with hard filters on game_type + theme + lang_pair.
"""

import numpy as np
from dataclasses import dataclass
from corpus_store import get_faiss_index, embed_with_cache, get_connection, get_entry_by_id
import config


@dataclass
class CorpusHit:
    entry_id: int
    similarity: float
    source: str
    target: str
    game_type: str
    theme: str
    lang_pair: str
    quality_score: float

    def to_prompt_context(self) -> str:
        return f"  SOURCE: {self.source}\n  TARGET: {self.target}"


def search_corpus(
    query_text: str,
    game_type: str = "",
    theme: str = "",
    lang_pair: str = "",
    top_k: int = None,
    search_multiplier: int = 5,
) -> list[CorpusHit]:
    top_k = top_k or config.RAG_TOP_K
    index = get_faiss_index()
    if index.ntotal == 0:
        return []

    query_vector = embed_with_cache([query_text])
    fetch_k = min(top_k * search_multiplier, index.ntotal)
    similarities, candidate_ids = index.search(query_vector, fetch_k)

    candidates = [(float(sim), int(cid))
                  for sim, cid in zip(similarities[0], candidate_ids[0])
                  if cid != -1]
    if not candidates:
        return []

    # Build SQL filter
    conditions = ["id IN ({ids})"]
    params = []
    id_list = [cid for _, cid in candidates]
    placeholders = ",".join("?" * len(id_list))

    filters = []
    if game_type:
        filters.append("game_type = ?")
        params.append(game_type)
    if theme:
        filters.append("theme = ?")
        params.append(theme)
    if lang_pair:
        filters.append("lang_pair = ?")
        params.append(lang_pair)

    where_sql = f"id IN ({placeholders})"
    if filters:
        where_sql += " AND " + " AND ".join(filters)

    conn = get_connection()
    rows = conn.execute(
        f"SELECT * FROM corpus WHERE {where_sql}",
        id_list + params
    ).fetchall()
    conn.close()

    valid_ids = {row["id"]: dict(row) for row in rows}

    results = []
    for sim, cid in candidates:
        if cid not in valid_ids:
            continue
        row = valid_ids[cid]
        results.append(CorpusHit(
            entry_id=cid,
            similarity=sim,
            source=row["source"],
            target=row["target"],
            game_type=row.get("game_type", ""),
            theme=row.get("theme", ""),
            lang_pair=row.get("lang_pair", ""),
            quality_score=row.get("quality_score", 3.0),
        ))
        if len(results) >= top_k:
            break

    # Sort by quality_score * similarity (high quality + high similarity wins)
    results.sort(key=lambda h: h.similarity * (h.quality_score / 5.0), reverse=True)
    return results


def decide_rag_usage(hits: list[CorpusHit]) -> tuple:
    """Returns (should_use: bool, filtered_hits: list).
    Drops hits below similarity threshold."""
    if not hits:
        return False, []
    filtered = [h for h in hits if h.similarity >= config.RAG_SIM_THRESHOLD]
    return bool(filtered), filtered
