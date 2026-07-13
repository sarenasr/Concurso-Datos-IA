"""Catalog ingestion + retrieval over Supabase pgvector.

`ingest_catalog` loads every Socrata catalog row into the `catalog` table.
`search_catalog` does hybrid retrieval: dense vector cosine search + keyword
(ilike) fallback, with a priority-dataset boost and a keyword-based safety net
to guarantee the Hero-10 datasets surface correctly.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.config import settings
from app.rag.embeddings import embed_text
from app.socrata.client import SocrataClient

log = logging.getLogger("datia.rag")

_PRIORITY_YAML = Path(__file__).resolve().parent.parent.parent / "data" / "priority_datasets.yaml"
_PRIORITY_BOOST = 1.3  # score multiplier for priority datasets

# Weights for hybrid fusion (vector + keyword)
_VECTOR_WEIGHT = 0.6
_TEXT_WEIGHT = 0.4


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
    1. Dense vector cosine search via pgvector RPC (with popularity prior).
    2. Keyword search via ``ilike`` on the catalog ``name`` column.
    3. Fuse both legs: ``final_score = 0.6 * vector_score + 0.4 * text_score``.
       Datasets appearing in only one leg keep that score (normalised to 0-1).
    4. Priority-dataset boost: multiply by 1.3 for any dataset in the priority
       YAML list (hand-curated, high-confidence schemas).
    5. Keyword fallback: if no priority dataset lands in the top-5, inject the
       best keyword-matched priority dataset as result #1.
    """
    sb = _supabase()
    qvec = embed_text(query)

    # --- Leg 1: dense vector search ----------------------------------------
    try:
        params: dict[str, Any] = {
            "qvec": str(qvec),
            "k": k * 4,
        }
        if sector:
            params["sector"] = sector
        vector_rows = sb.rpc("match_catalog", params).execute().data
    except Exception:
        vector_rows = _fallback_cosine_search(sb, qvec, k * 4, sector, municipio)

    vector_rows = _apply_popularity_prior(vector_rows)

    # --- Leg 2: keyword search via ilike on name ---------------------------
    text_rows = _keyword_search(sb, query, k * 4)

    # --- Fuse both legs ----------------------------------------------------
    fused = _fuse_results(vector_rows, text_rows)

    # --- Priority boost ----------------------------------------------------
    fused = _apply_priority_boost(fused)

    # Re-sort after fusion + boost
    fused.sort(key=lambda r: r["score"], reverse=True)

    # --- Keyword fallback for priority datasets ----------------------------
    fused = _priority_fallback(fused, query, k)

    return fused[:k]


def _keyword_search(sb, query: str, k: int) -> list[dict]:
    """Keyword search leg: ilike on the catalog ``name`` column.

    Returns a list of dicts with the same shape as vector results, with a
    ``text_score`` normalised to [0, 1] based on position in the result set.
    """
    # Take the first meaningful words from the query (up to 50 chars) for ilike
    snippet = query[:50].strip()
    if not snippet:
        return []
    try:
        text_rows = (
            sb.table("catalog")
            .select("id, name, description, domain_category, permalink, page_views_last_month")
            .ilike("name", f"%{snippet}%")
            .limit(k)
            .execute()
            .data
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("keyword search failed: %s", exc)
        return []

    # Assign text_score: 1.0 for first result, decaying linearly
    n = len(text_rows)
    for i, r in enumerate(text_rows):
        r["text_score"] = 1.0 - (i / max(n, 1))
    return text_rows


def _fuse_results(vector_rows: list[dict], text_rows: list[dict]) -> list[dict]:
    """Merge vector and keyword results by dataset ID.

    Scoring:
    - If a dataset appears in both legs: ``0.6 * vector_score + 0.4 * text_score``
    - If only in vector leg: keep vector score (already normalised by popularity).
    - If only in text leg: keep text_score (already normalised to [0, 1]).
    """
    by_id: dict[str, dict] = {}

    for r in vector_rows:
        rid = r.get("id")
        if not rid:
            continue
        entry = dict(r)
        entry["_vector_score"] = float(entry.get("score", 0.0))
        entry["_text_score"] = 0.0
        by_id[rid] = entry

    for r in text_rows:
        rid = r.get("id")
        if not rid:
            continue
        text_score = float(r.get("text_score", 0.0))
        if rid in by_id:
            by_id[rid]["_text_score"] = text_score
        else:
            entry = dict(r)
            entry["_vector_score"] = 0.0
            entry["_text_score"] = text_score
            entry["score"] = text_score
            by_id[rid] = entry

    # Compute fused score
    for entry in by_id.values():
        vs = entry.pop("_vector_score", 0.0)
        ts = entry.pop("_text_score", 0.0)
        if vs > 0 and ts > 0:
            entry["score"] = _VECTOR_WEIGHT * vs + _TEXT_WEIGHT * ts
        elif vs > 0:
            entry["score"] = vs
        else:
            entry["score"] = ts

    return list(by_id.values())


def _apply_priority_boost(rows: list[dict]) -> list[dict]:
    """Multiply the score of priority datasets by ``_PRIORITY_BOOST`` (1.3x)."""
    pids = _priority_ids()
    if not pids:
        return rows
    for r in rows:
        if r.get("id") in pids:
            r["score"] = float(r.get("score", 0.0)) * _PRIORITY_BOOST
    return rows


def _priority_fallback(rows: list[dict], query: str, k: int) -> list[dict]:
    """Ensure the best keyword-matched priority dataset is in the results.

    Two-stage logic:
    1. If the top-5 already contains the *best* keyword-matched priority dataset
       (the one with the most hits), do nothing.
    2. Otherwise inject (or boost) the best match to position #1.

    This fixes the bug where a *different* priority dataset (e.g. Bolsa A)
    lands in the top-5 via vector similarity, causing the old early-return to
    skip injecting the *correct* priority dataset (e.g. SECOP II Contratos).
    """
    matches = _priority_keyword_match(query)
    if not matches:
        return rows

    best = matches[0]
    best_id = best["id"]

    # If the best keyword match is already #1 with a strong score, leave it
    top = rows[0] if rows else None
    if top and top.get("id") == best_id and float(top.get("score", 0.0)) >= 0.5:
        return rows

    # Check if the best match is already somewhere in the results
    existing = next((r for r in rows if r.get("id") == best_id), None)
    if existing:
        # Boost it to the top with a high score
        existing["score"] = max(float(existing.get("score", 0.0)) * _PRIORITY_BOOST, 0.95)
        rows.sort(key=lambda r: r["score"], reverse=True)
        return rows

    # Inject as result #1 with a high confidence score
    injected = {
        "id": best_id,
        "name": best.get("name", ""),
        "description": "",
        "domain_category": best.get("sector", ""),
        "permalink": f"https://{settings.socrata_domain}/d/{best_id}",
        "page_views_last_month": 0,
        "score": 0.95,  # high confidence injection
    }
    return [injected] + rows


def _apply_popularity_prior(rows: list[dict]) -> list[dict]:
    import math

    for r in rows:
        sim = float(r.get("score", 0.0))
        pv = float(r.get("page_views_last_month") or 0)
        prior = 1.0 + math.log(max(pv, 1)) / 100.0
        r["score"] = sim * prior
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


def _fallback_cosine_search(
    sb, qvec: list[float], k: int, sector: str | None, municipio: str | None
) -> list[dict]:
    """Naive fallback: pull embeddings table + catalog, compute cosine in numpy."""
    import numpy as np

    emb_rows = (
        sb.table("catalog_embeddings").select("dataset_id, embedding, doc_text").execute().data
    )
    cat_rows = (
        sb.table("catalog")
        .select("id, name, description, domain_category, permalink, page_views_last_month")
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
