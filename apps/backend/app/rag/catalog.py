"""Catalog ingestion + retrieval over Supabase pgvector.

`ingest_catalog` loads every Socrata catalog row into the `catalog` table.
`search_catalog` does dense retrieval (cosine) with a popularity prior and
metadata filters. A TODO marks where BM25 + Reciprocal Rank Fusion will go.
"""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.rag.embeddings import embed_text
from app.socrata.client import SocrataClient


def _supabase():
    from supabase import create_client

    return create_client(settings.supabase_url, settings.supabase_key_resolved)


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

    Dense-only retrieval for now: embed the query, cosine search on
    `catalog_embeddings`, re-rank by similarity * (1 + log(page_views_last_month)/100)
    popularity prior, apply metadata filters (sector, municipio).

    TODO(phase2): add a BM25 (tsvector) leg and fuse with Reciprocal Rank Fusion (RRF).
    """
    sb = _supabase()
    qvec = embed_text(query)

    # pgvector cosine: call a stored-free RPC that orders by embedding <=> qvec.
    # We use an rpc `match_catalog` (created by migration 002 follow-up). If absent,
    # fall back to a manual cosine search via the Python client + numpy.
    try:
        params: dict[str, Any] = {
            "qvec": str(qvec),
            "k": k * 4,
        }
        if sector:
            params["sector"] = sector
        # NOTE: municipio filter is not yet supported by the match_catalog RPC;
        # it is intentionally omitted here to avoid an unknown-parameter error.
        rows = sb.rpc("match_catalog", params).execute().data
    except Exception:
        rows = _fallback_cosine_search(sb, qvec, k * 4, sector, municipio)

    ranked = _apply_popularity_prior(rows)
    return ranked[:k]


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
