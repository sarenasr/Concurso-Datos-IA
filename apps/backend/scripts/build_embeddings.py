"""CLI: embed catalog rows that are missing vectors.

Reads all rows from `catalog`, builds a doc string per dataset, embeds with Gemini
text-embedding-004, and upserts into `catalog_embeddings`.

Usage:
    uv run python -m scripts.build_embeddings
"""
from __future__ import annotations

from app.config import settings
from app.rag.embeddings import embed_texts


def _supabase():
    from supabase import create_client

    return create_client(settings.supabase_url, settings.supabase_service_key)


def _doc(row: dict) -> str:
    parts = [row.get("name") or "", row.get("description") or ""]
    tags = row.get("domain_tags") or []
    if tags:
        parts.append(", ".join(tags))
    cols = row.get("columns_name") or []
    if cols:
        parts.append("Columnas: " + ", ".join(cols))
    return " | ".join(p for p in parts if p)


def main() -> None:
    sb = _supabase()
    rows = sb.table("catalog").select("id, name, description, domain_tags, columns_name").execute().data

    # find which datasets already have embeddings
    done = {r["dataset_id"] for r in sb.table("catalog_embeddings").select("dataset_id").execute().data}
    todo = [r for r in rows if r["id"] not in done]
    print(f"{len(rows)} catalog rows, {len(todo)} missing embeddings")

    for i in range(0, len(todo), 100):
        batch = todo[i : i + 100]
        docs = [_doc(r) for r in batch]
        vectors = embed_texts(docs)
        upsert = [
            {"dataset_id": r["id"], "embedding": v, "doc_text": d}
            for r, v, d in zip(batch, vectors, docs)
        ]
        sb.table("catalog_embeddings").upsert(upsert, on_conflict="dataset_id").execute()
        print(f"  embedded {len(batch)} ({i + len(batch)}/{len(todo)})")
    print("done")


if __name__ == "__main__":
    main()
