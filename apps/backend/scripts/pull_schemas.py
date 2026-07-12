"""CLI: build schema registry from the catalog table in Supabase.

Instead of fetching /api/views/{id}.json (which returns 403 on datos.gov.co),
this pulls column metadata directly from the `catalog` table where we already
stored it during ingest_catalog (columns_name, columns_field_name, etc.).

Also resolves `id: TODO` placeholders by searching the catalog via the DDA API.

Usage:
    uv run python -m scripts.pull_schemas
"""

from __future__ import annotations

from pathlib import Path

import yaml

from app.config import settings
from app.socrata.client import SocrataClient

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PRIORITY_FILE = DATA_DIR / "priority_datasets.yaml"
REGISTRY_PATH = Path(__file__).resolve().parent.parent / "app" / "schemas" / "registry.yaml"


def _supabase():
    from supabase import create_client

    return create_client(settings.supabase_url, settings.supabase_key_resolved)


def _resolve_todo(client: SocrataClient, hint: str) -> str | None:
    """Search the catalog for a hint and return the top result id."""
    data = client._get(  # noqa: SLF001
        "/api/catalog/v1",
        params={"q": hint, "domains": settings.socrata_domain, "limit": 1},
    )
    results = data.get("results", []) if isinstance(data, dict) else []
    if not results:
        return None
    res = results[0].get("resource", {})
    return res.get("id")


def main() -> None:
    priority = yaml.safe_load(PRIORITY_FILE.read_text(encoding="utf-8")) or {}
    datasets = priority.get("priority_datasets", [])
    client = SocrataClient(settings.socrata_domain, settings.socrata_app_token)
    sb = _supabase()

    # Update the priority_datasets.yaml with resolved IDs
    resolved_entries = []

    registry: list[dict] = []
    for entry in datasets:
        did = entry.get("id")
        if did == "TODO" or not did:
            did = _resolve_todo(client, entry.get("search_hint", entry.get("name", "")))
            if not did:
                print(f"  SKIP (unresolved): {entry.get('name')}")
                resolved_entries.append(entry)
                continue
            print(f"  resolved {entry.get('name')} -> {did}")
            entry["id"] = did
        resolved_entries.append(entry)

        # Pull schema from Supabase catalog table
        rows = (
            sb.table("catalog")
            .select(
                "id, name, columns_name, columns_field_name, columns_datatype, columns_description, permalink"
            )
            .eq("id", did)
            .execute()
            .data
        )
        if not rows:
            print(f"  SKIP (not in catalog): {did} ({entry.get('name')})")
            continue

        row = rows[0]
        col_names = row.get("columns_name") or []
        col_fields = row.get("columns_field_name") or []
        col_types = row.get("columns_datatype") or []
        col_descs = row.get("columns_description") or []

        cols = []
        for i in range(len(col_names)):
            cols.append(
                {
                    "name": col_names[i] if i < len(col_names) else None,
                    "field_name": col_fields[i] if i < len(col_fields) else None,
                    "datatype": col_types[i] if i < len(col_types) else None,
                    "description": col_descs[i] if i < len(col_descs) else None,
                }
            )

        registry.append(
            {
                "id": did,
                "name": row.get("name"),
                "permalink": row.get("permalink") or f"https://{settings.socrata_domain}/d/{did}",
                "columns": cols,
            }
        )
        print(f"  {did}: {row.get('name')} ({len(cols)} cols)")

    # Write updated priority_datasets.yaml with resolved IDs
    PRIORITY_FILE.write_text(
        yaml.safe_dump(
            {"priority_datasets": resolved_entries},
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    REGISTRY_PATH.write_text(
        yaml.safe_dump({"datasets": registry}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"registry written: {REGISTRY_PATH} ({len(registry)} datasets)")


if __name__ == "__main__":
    main()
