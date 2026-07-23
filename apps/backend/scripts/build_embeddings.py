"""CLI: embed catalog rows that are missing vectors.

Reads all rows from `catalog`, builds a doc string per dataset, embeds with Google
`gemini-embedding-2` (1024-dim) via OpenRouter (see `app/rag/embeddings.py`), and
upserts into `catalog_embeddings`.

Usage:
    uv run python -m scripts.build_embeddings
"""

from __future__ import annotations

import time

from app.config import settings
from app.rag.embeddings import embed_texts, BATCH_SIZE, TASK_TYPE_DOCUMENT


def _supabase():
    from supabase import create_client

    return create_client(settings.supabase_url, settings.supabase_key_resolved)


def _doc(row: dict) -> str:
    parts = [row.get("name") or "", row.get("description") or ""]
    category = row.get("domain_category")
    if category:
        parts.append(f"Sector: {category}")
    tags = row.get("domain_tags") or []
    if tags:
        parts.append("Etiquetas: " + ", ".join(tags))
    col_names = row.get("columns_name") or []
    col_fields = row.get("columns_field_name") or []
    col_descs = row.get("columns_description") or []
    if col_names:
        col_parts = []
        for i, cn in enumerate(col_names):
            cf = col_fields[i] if i < len(col_fields) else ""
            cd = col_descs[i] if i < len(col_descs) and col_descs[i] else ""
            if cd:
                col_parts.append(f"{cn} ({cf}): {cd}")
            else:
                col_parts.append(f"{cn} ({cf})")
        parts.append("Columnas: " + "; ".join(col_parts))
    return " | ".join(p for p in parts if p)


def _fetch_all(sb, table: str, select: str, page_size: int = 1000) -> list[dict]:
    """Paginate through all rows of a Supabase table."""
    all_rows: list[dict] = []
    offset = 0
    while True:
        resp = sb.table(table).select(select).range(offset, offset + page_size - 1).execute()
        batch = resp.data
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return all_rows


def main() -> None:
    sb = _supabase()
    rows = _fetch_all(
        sb,
        "catalog",
        "id, name, description, domain_category, domain_tags, columns_name, columns_field_name, columns_description",
    )

    done = {
        r["dataset_id"] for r in sb.table("catalog_embeddings").select("dataset_id").execute().data
    }
    todo = [r for r in rows if r["id"] not in done]
    print(f"{len(rows)} catalog rows, {len(todo)} missing embeddings")

    for i in range(0, len(todo), BATCH_SIZE):
        batch = todo[i : i + BATCH_SIZE]
        docs = [_doc(r) for r in batch]
        vectors = embed_texts(docs, task_type=TASK_TYPE_DOCUMENT)
        if len(vectors) != len(batch):
            print(f"  WARNING: got {len(vectors)} vectors for {len(batch)} docs — skipping batch")
            continue
        upsert = [
            {"dataset_id": r["id"], "embedding": v, "doc_text": d}
            for r, v, d in zip(batch, vectors, docs)
        ]
        try:
            sb.table("catalog_embeddings").upsert(upsert, on_conflict="dataset_id").execute()
            if i % 200 == 0:
                count = (
                    sb.table("catalog_embeddings")
                    .select("dataset_id", count="exact")
                    .execute()
                    .count
                )
                print(f"  embedded {i + len(batch)}/{len(todo)} (DB total: {count})", flush=True)
            else:
                print(f"  embedded {i + len(batch)}/{len(todo)}", flush=True)
        except Exception as e:
            print(f"  ERROR at batch {i}: {e}", flush=True)
        time.sleep(0.5)
    print("done")


if __name__ == "__main__":
    main()
