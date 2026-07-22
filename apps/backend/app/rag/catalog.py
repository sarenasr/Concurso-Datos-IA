"""Catalog ingestion + retrieval over Supabase pgvector.

`ingest_catalog` loads every Socrata catalog row into the `catalog` table.
`search_catalog` does hybrid retrieval: dense vector cosine search + keyword
(ilike) fallback, fused with Reciprocal Rank Fusion (RRF). A priority-dataset
boost and a keyword-based safety net guarantee the Hero-10 datasets surface
correctly.

The vector leg uses the `match_catalog` Supabase RPC (see
`infra/supabase/migrations/004_match_catalog.sql`). On RPC failure we log and
skip the vector leg unless `NUMPY_FALLBACK=1` enables a slow
in-process NumPy fallback.
"""

from __future__ import annotations

import logging
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.config import settings
from app.rag.embeddings import embed_text
from app.socrata.client import SocrataClient

log = logging.getLogger("manglar.rag")

_PRIORITY_YAML = Path(__file__).resolve().parent.parent.parent / "data" / "priority_datasets.yaml"

_RRF_K = 60
_PRIORITY_BOOST_ADD = 0.02
_PRIORITY_FALLBACK_SCORE = 0.05
_PRIORITY_FALLBACK_THRESHOLD = 0.02
_MAX_KEYWORD_TOKENS = 5

_STOPWORDS = frozenset(
    {
        "los",
        "las",
        "del",
        "de",
        "para",
        "por",
        "con",
        "que",
        "hay",
        "cuantos",
        "cuantas",
        "cuales",
        "una",
        "uno",
        "unos",
        "unas",
        "más",
        "mas",
    }
)

_TOKEN_RE = re.compile(r"[^a-záéíóúüñ]+")


@lru_cache(maxsize=1)
def _supabase():
    from supabase import create_client

    return create_client(settings.supabase_url, settings.supabase_key_resolved)


@lru_cache(maxsize=1)
def _load_priority_datasets() -> list[dict]:
    """Load and cache the priority datasets list from YAML.

    Returns a list of dicts with keys: id, name, search_hint, sector.
    """
    if not _PRIORITY_YAML.exists():
        return []
    data = yaml.safe_load(_PRIORITY_YAML.read_text(encoding="utf-8")) or {}
    return data.get("priority_datasets", [])


@lru_cache(maxsize=1)
def _priority_ids() -> set[str]:
    """Return the set of priority dataset IDs (excluding 'TODO' placeholders)."""
    return {d["id"] for d in _load_priority_datasets() if d.get("id") and d["id"] != "TODO"}


def _expand_synonyms(words: set[str]) -> set[str]:
    """Expand a set of query words with common Spanish synonyms for dataset matching.

    This ensures that colloquial terms like 'ciudad' match 'municipio', that
    'contrato' matches 'contratos', and that 'secop' is recognised as a keyword
    even though it never appears in a dataset *name* — only in search_hints.
    """
    _SYNONYM_MAP: dict[str, set[str]] = {
        "contrato": {"contratos", "contratacion", "secop"},
        "contratos": {"contrato", "contratacion", "secop"},
        "ciudad": {"municipio", "ciudades", "localidad"},
        "municipio": {"ciudad", "municipios", "localidad"},
        "secop": {"contratos", "contratacion", "secop2"},
        "secop2": {"secop", "contratos"},
        "vacuna": {"vacunacion", "vacunas", "dosis"},
        "vacunacion": {"vacuna", "vacunas", "dosis"},
        "empleo": {"desempleo", "trabajo", "laboral"},
        "desempleo": {"empleo", "trabajo"},
        "medicamento": {"medicamentos", "cum", "invima"},
        "medicamentos": {"medicamento", "cum", "invima"},
        "habitantes": {"poblacion", "población", "censo", "demografia"},
        "poblacion": {"habitantes", "población", "censo", "demografia"},
        "población": {"habitantes", "poblacion", "censo", "demografia"},
    }
    expanded = set(words)
    for w in words:
        if w in _SYNONYM_MAP:
            expanded |= _SYNONYM_MAP[w]
    return expanded


def _tokenize_query(query: str) -> list[str]:
    """Tokenize a natural-language query into search terms for keyword retrieval.

    Lowercases, splits on non-alpha characters, keeps words with 3+ characters,
    removes Spanish stopwords, then expands synonyms. Returns a deduplicated list
    preserving first-seen order (original tokens first, then synonym additions).
    """
    q = query.lower()
    raw = [w for w in _TOKEN_RE.split(q) if len(w) >= 3 and w not in _STOPWORDS]
    seen: set[str] = set()
    result: list[str] = []
    for w in raw:
        if w not in seen:
            seen.add(w)
            result.append(w)
    for w in _expand_synonyms(set(raw)):
        if w not in seen:
            seen.add(w)
            result.append(w)
    return result


def _priority_keyword_match(query: str) -> list[dict]:
    """Find priority datasets whose name or search_hint keywords appear in the query.

    Scoring uses two signals:
    1. **name_hits** — overlap between query words (synonym-expanded) and the
       dataset's *name* tokens.
    2. **hint_hits** — overlap between query words and the dataset's
       *search_hint* tokens.  The search_hint is the hand-curated "this is what
       this dataset is about" signal, so it acts as a **tiebreaker** when
       name_hits are equal.

    Returns matching priority dataset entries sorted by (name_hits, hint_hits)
    descending.  Each entry is the original dict from priority_datasets.yaml.
    """
    q = query.lower()
    # Tokenize: split on non-alpha, keep words >= 3 chars, lowercase
    q_words_raw = {w for w in re.split(r"[^a-záéíóúüñ]+", q) if len(w) >= 3}
    q_words = _expand_synonyms(q_words_raw)
    matches = []
    for ds in _load_priority_datasets():
        if ds.get("id") == "TODO":
            continue
        # Name keywords
        name_text = ds.get("name", "").lower()
        name_words = {w for w in re.split(r"[^a-záéíóúüñ]+", name_text) if len(w) >= 3}
        name_hits = len(q_words & name_words)
        # Search-hint keywords (tiebreaker)
        hint_text = ds.get("search_hint", "").lower()
        hint_words = {w for w in re.split(r"[^a-záéíóúüñ]+", hint_text) if len(w) >= 3}
        hint_hits = len(q_words & hint_words)
        total = name_hits + hint_hits
        if total > 0:
            matches.append((name_hits, hint_hits, ds))
    # Sort by name_hits desc, then hint_hits desc
    matches.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [ds for _, _, ds in matches]


def _flatten(item: dict) -> dict[str, Any]:
    """Flatten a catalog result into a `catalog`-table row."""
    res = item.get("resource", {})
    classification = item.get("classification", {}) or {}
    cols = res.get("columns_name") or res.get("columns") or []
    field_names = res.get("columns_field_name") or []
    datatypes = res.get("columns_datatype") or []
    col_desc = res.get("columns_description") or []
    return {
        "id": res.get("id"),
        "name": res.get("name"),
        "description": res.get("description"),
        "type": res.get("type"),
        "domain_category": classification.get("domain_category"),
        "domain_tags": classification.get("domain_tags") or [],
        "domain_metadata": classification.get("domain_metadata") or {},
        "columns_name": list(cols) if cols else [],
        "columns_field_name": list(field_names),
        "columns_datatype": list(datatypes),
        "columns_description": list(col_desc),
        "page_views_last_week": res.get("page_views", {}).get("page_views_last_week"),
        "page_views_last_month": res.get("page_views", {}).get("page_views_last_month"),
        "page_views_total": res.get("page_views", {}).get("page_views_total"),
        "download_count": res.get("download_count"),
        "permalink": res.get("permalink") or f"https://{settings.socrata_domain}/d/{res.get('id')}",
        "updated_at": res.get("updatedAt") or res.get("updated_at"),
    }


def ingest_catalog(limit: int | None = None) -> int:
    """Iterate the Socrata catalog and upsert rows into Supabase `catalog`.

    Returns the number of rows upserted. Uses the `on conflict id` strategy.
    Deduplicates within each batch to avoid the "a second time" Postgres error.
    """
    sb = _supabase()
    client = SocrataClient(settings.socrata_domain, settings.socrata_app_token)
    n = 0
    batch: list[dict] = []
    for item in client.iter_catalog(limit=limit):
        row = _flatten(item)
        if not row["id"]:
            continue
        # Only index queryable tabular datasets; skip charts, maps, stories, etc.
        if row.get("type") != "dataset":
            continue
        batch.append(row)
        n += 1
        if n % 1000 == 0:
            print(f"  ... fetched {n} rows from catalog", flush=True)
        if len(batch) >= 200:
            _upsert_batch(sb, batch)
            batch = []
    if batch:
        _upsert_batch(sb, batch)
    print(f"  ... total fetched: {n}", flush=True)
    return n


def _upsert_batch(sb, batch: list[dict]) -> None:
    """Upsert a batch, deduplicating by id to avoid Postgres constraint error."""
    seen: dict[str, dict] = {}
    for row in batch:
        seen[row["id"]] = row
    deduped = list(seen.values())
    if deduped:
        sb.table("catalog").upsert(deduped, on_conflict="id").execute()


def search_catalog(
    query: str,
    sector: str | None = None,
    municipio: str | None = None,
    k: int = 10,
) -> list[dict]:
    """Retrieve the most relevant datasets for a natural-language `query`.

    Hybrid retrieval:
    1. Dense vector cosine search via pgvector RPC.
    2. Keyword search via per-token ``ilike`` on the catalog ``name`` column.
    3. Fuse both legs with Reciprocal Rank Fusion (RRF, k=60).
    4. Popularity prior as additive tie-breaker (not a multiplier).
    5. Priority-dataset boost: add a small absolute bump for datasets in the
       priority YAML list (hand-curated, high-confidence schemas).
    6. Keyword fallback: if no priority dataset lands in the top-5, inject the
       best keyword-matched priority dataset as result #1.
    7. LLM reranker (when ``ENABLE_RERANKER`` is true): ask a small LLM to
       score each candidate's relevance and blend with the fused score.
    """
    sb = _supabase()
    qvec = embed_text(query)

    try:
        params: dict[str, Any] = {
            "qvec": str(qvec),
            "k": k * 4,
        }
        if sector:
            params["sector"] = sector
        vector_rows = sb.rpc("match_catalog", params).execute().data
    except Exception as exc:
        log.warning("match_catalog RPC failed, skipping vector leg: %s", exc)
        if settings.numpy_fallback:
            vector_rows = _numpy_emergency_search(sb, qvec, k * 4, sector, municipio)
        else:
            vector_rows = []

    text_rows = _keyword_search(sb, query, k * 4)

    vector_preview = [
        (r.get("id"), r.get("name", "")[:50], f"{r.get('score', 0):.4f}")
        for r in vector_rows[:5]
        if r.get("score") is not None
    ]
    text_preview = [
        (r.get("id"), r.get("name", "")[:50], f"{r.get('text_score', 0):.4f}")
        for r in text_rows[:5]
        if r.get("text_score") is not None
    ]
    log.info("Vector leg top-5: %s", vector_preview)
    log.info("Keyword leg top-5: %s", text_preview)

    fused = _fuse_results(vector_rows, text_rows)

    fused_preview = [
        (r.get("id"), r.get("name", "")[:50], f"{r.get('score', 0):.4f}") for r in fused[:5]
    ]
    log.info("After fusion top-5: %s", fused_preview)

    fused = _apply_popularity_prior(fused)

    fused = _apply_priority_boost(fused)

    fused.sort(key=lambda r: r["score"], reverse=True)

    boosted_preview = [
        (r.get("id"), r.get("name", "")[:50], f"{r.get('score', 0):.4f}") for r in fused[:5]
    ]
    log.info("After priority boost top-5: %s", boosted_preview)

    fused = _priority_fallback(fused, query, k)

    final_preview = [
        (r.get("id"), r.get("name", "")[:50], f"{r.get('score', 0):.4f}") for r in fused[:k]
    ]
    log.info("Final results top-%d: %s", k, final_preview)

    if settings.enable_reranker:
        from app.rag.reranker import rerank_datasets

        fused = rerank_datasets(query, fused, top_k=k)

    return fused[:k]


def _keyword_search(sb, query: str, k: int) -> list[dict]:
    """Keyword search leg: per-token ``ilike`` on the catalog ``name`` column.

    Tokenizes the query (same pipeline as ``_priority_keyword_match``), then
    issues one ``ilike`` query per token (capped at ``_MAX_KEYWORD_TOKENS``).
    Results are unioned in Python; when a dataset matches multiple tokens its
    ``text_score`` uses the best (lowest) rank across all token queries.

    Returns a list of dicts with the same shape as vector results, with a
    ``text_score`` based on linear rank decay from 1.0 to 0.
    """
    tokens = _tokenize_query(query)[:_MAX_KEYWORD_TOKENS]
    if not tokens:
        return []

    best_rank: dict[str, int] = {}
    row_by_id: dict[str, dict] = {}

    for token in tokens:
        try:
            rows = (
                sb.table("catalog")
                .select("id, name, description, domain_category, permalink, page_views_last_month")
                .eq("type", "dataset")
                .ilike("name", f"%{token}%")
                .limit(k)
                .execute()
                .data
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("keyword search for token '%s' failed: %s", token, exc)
            continue

        for rank, r in enumerate(rows):
            rid = r.get("id")
            if not rid:
                continue
            if rid not in row_by_id:
                row_by_id[rid] = r
            if rid not in best_rank or rank < best_rank[rid]:
                best_rank[rid] = rank

    n = len(row_by_id)
    if n == 0:
        return []

    result: list[dict] = []
    for rid, row in row_by_id.items():
        entry = dict(row)
        entry["text_score"] = 1.0 - (best_rank[rid] / max(n, 1))
        result.append(entry)

    result.sort(key=lambda r: r["text_score"], reverse=True)
    return result[:k]


def _fuse_results(vector_rows: list[dict], text_rows: list[dict]) -> list[dict]:
    """Merge vector and keyword results using Reciprocal Rank Fusion.

    For each dataset ``d`` the fused score is::

        score(d) = sum( 1 / (_RRF_K + rank_in_leg(d)) )

    where ``rank_in_leg`` is 0-indexed within each leg. Datasets absent from a
    leg simply contribute nothing for that leg. The result is sorted by RRF
    score descending.
    """
    by_id: dict[str, dict] = {}

    for rank, r in enumerate(vector_rows):
        rid = r.get("id")
        if not rid:
            continue
        entry = dict(r)
        entry["score"] = 1.0 / (_RRF_K + rank)
        by_id[rid] = entry

    for rank, r in enumerate(text_rows):
        rid = r.get("id")
        if not rid:
            continue
        rrf_contrib = 1.0 / (_RRF_K + rank)
        if rid in by_id:
            by_id[rid]["score"] += rrf_contrib
        else:
            entry = dict(r)
            entry["score"] = rrf_contrib
            by_id[rid] = entry

    result = list(by_id.values())
    result.sort(key=lambda r: r["score"], reverse=True)
    return result


def _apply_priority_boost(rows: list[dict]) -> list[dict]:
    """Add a small absolute bump to the RRF score of priority datasets.

    RRF scores live in ``[0, ~0.033]`` so a multiplicative boost (the old 1.3×)
    would be disproportionate at this scale. Instead we add ``_PRIORITY_BOOST_ADD``
    (0.02) — enough to promote a priority dataset within the noise floor but not
    enough to swamp the similarity signal from the retrieval legs.
    """
    pids = _priority_ids()
    if not pids:
        return rows
    for r in rows:
        if r.get("id") in pids:
            r["score"] = float(r.get("score", 0.0)) + _PRIORITY_BOOST_ADD
    return rows


def _priority_fallback(rows: list[dict], query: str, k: int) -> list[dict]:
    """Ensure the best keyword-matched priority dataset is in the results.

    Two-stage logic:
    1. If the top result already *is* the best keyword-matched priority dataset
       with a score above ``_PRIORITY_FALLBACK_THRESHOLD``, do nothing.
    2. Otherwise inject (or boost) the best match to position #1.

    The injected entry gets ``_PRIORITY_FALLBACK_SCORE`` (0.05) — a small
    RRF-scale value that reliably promotes the priority dataset above the noise
    floor without fabricating a high-confidence score. Tagged with
    ``"reason": "priority_keyword_match"`` for auditability.
    """
    matches = _priority_keyword_match(query)
    if not matches:
        return rows

    best = matches[0]
    best_id = best["id"]
    best_name = best.get("name", best_id)

    top = rows[0] if rows else None
    if (
        top
        and top.get("id") == best_id
        and float(top.get("score", 0.0)) >= _PRIORITY_FALLBACK_THRESHOLD
    ):
        return rows

    existing = next((r for r in rows if r.get("id") == best_id), None)
    if existing:
        old_score = float(existing.get("score", 0.0))
        existing["score"] = max(
            old_score + _PRIORITY_BOOST_ADD,
            _PRIORITY_FALLBACK_SCORE,
        )
        log.info(
            "Priority fallback: boosted %s (%s) from %.4f to %.4f (was #%d, now #1)",
            best_id,
            best_name,
            old_score,
            existing["score"],
            next((i for i, r in enumerate(rows) if r.get("id") == best_id), -1) + 1,
        )
        rows.sort(key=lambda r: r["score"], reverse=True)
        return rows

    log.info(
        "Priority fallback: injected %s (%s) as #1 with score %.4f (was not in top results)",
        best_id,
        best_name,
        _PRIORITY_FALLBACK_SCORE,
    )
    injected = {
        "id": best_id,
        "name": best.get("name", ""),
        "description": "",
        "domain_category": best.get("sector", ""),
        "permalink": f"https://{settings.socrata_domain}/d/{best_id}",
        "page_views_last_month": 0,
        "score": _PRIORITY_FALLBACK_SCORE,
        "reason": "priority_keyword_match",
    }
    return [injected] + rows


def _apply_popularity_prior(rows: list[dict]) -> list[dict]:
    """Nudge scores by popularity as a tie-breaker, not a multiplier.

    Adds ``log1p(page_views_last_month) / 1000`` to each score so that
    popularity can break ties between equally-ranked datasets but never
    swallows the similarity signal from the retrieval legs.
    """
    for r in rows:
        pv = float(r.get("page_views_last_month") or 0)
        prior = math.log1p(max(pv, 0)) / 1000.0
        r["score"] = float(r.get("score", 0.0)) + prior
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows


def _parse_embedding(emb: Any) -> list[float] | None:
    """Parse an embedding value from Supabase into a list[float].

    Embeddings are stored as Python-list *strings* (e.g. ``"[-0.01, ...]"``) rather
    than native vectors, so ``np.asarray(emb, dtype=float)`` raises ``ValueError``.
    We detect strings and ``ast.literal_eval`` them first.
    """
    import ast

    if emb is None:
        return None
    if isinstance(emb, str):
        try:
            emb = ast.literal_eval(emb)
        except (ValueError, SyntaxError):
            return None
    try:
        return [float(x) for x in emb]
    except (TypeError, ValueError):
        return None


def _numpy_emergency_search(
    sb, qvec: list[float], k: int, sector: str | None, municipio: str | None
) -> list[dict]:
    """Naive fallback: pull embeddings table + catalog, compute cosine in numpy."""
    import numpy as np

    emb_rows = (
        sb.table("catalog_embeddings").select("dataset_id, embedding, doc_text").execute().data
    )
    cat_rows = (
        sb.table("catalog")
        .select("id, name, description, domain_category, permalink, page_views_last_month, type")
        .eq("type", "dataset")
        .execute()
        .data
    )
    cat_by_id = {r["id"]: r for r in cat_rows}

    q = np.asarray(qvec, dtype=float)
    qn = q / (np.linalg.norm(q) + 1e-9)
    scored = []
    for er in emb_rows:
        parsed = _parse_embedding(er.get("embedding"))
        if not parsed:
            continue
        v = np.asarray(parsed, dtype=float)
        if v.shape != q.shape:
            continue
        vn = v / (np.linalg.norm(v) + 1e-9)
        sim = float(qn @ vn)
        cat = cat_by_id.get(er["dataset_id"], {})
        scored.append(
            {
                "id": er["dataset_id"],
                "name": cat.get("name"),
                "description": cat.get("description"),
                "domain_category": cat.get("domain_category"),
                "score": sim,
                "permalink": cat.get("permalink"),
                "page_views_last_month": cat.get("page_views_last_month"),
            }
        )
    scored.sort(key=lambda r: r["score"], reverse=True)
    # Prefer sector matches but never return an empty list: top up with the best
    # unfiltered candidates so the agent always has something to try.
    if sector:
        sector_matches = [r for r in scored if r.get("domain_category") == sector]
        if sector_matches:
            ids = {r["id"] for r in sector_matches}
            sector_matches += [r for r in scored if r["id"] not in ids]
            return sector_matches[:k]
    return scored[:k]
