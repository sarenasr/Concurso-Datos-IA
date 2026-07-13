"""CLI: ingest the Socrata catalog into Supabase.

Usage:
    uv run python -m scripts.ingest_catalog            # full catalog
    uv run python -m scripts.ingest_catalog --limit 500 # sample
"""

from __future__ import annotations

import argparse

from app.rag.catalog import ingest_catalog


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Socrata catalog into Supabase")
    parser.add_argument("--limit", type=int, default=None, help="max rows (default: full catalog)")
    args = parser.parse_args()
    n = ingest_catalog(limit=args.limit)
    print(f"ingested {n} rows into catalog")


if __name__ == "__main__":
    main()
