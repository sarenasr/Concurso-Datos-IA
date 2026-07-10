"""CLI: fetch /api/views/{id}.json for priority datasets -> schemas/registry.yaml.

Resolves `id: TODO` placeholders by searching the catalog with `search_hint`.

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

    return create_client(settings.supabase_url, settings.supabase_service_key)


def _resolve_todo(client: SocrataClient, hint: str) -> str | None:
    """Search the catalog for a hint and return the top result id."""
    data = client._get(  # noqa: SLF001
        "/api/catalog/v1", params={"q": hint, "domains": settings.socrata_domain, "limit": 1}
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

    registry: list[dict] = []
    for entry in datasets:
        did = entry.get("id")
        if did == "TODO" or not did:
            did = _resolve_todo(client, entry.get("search_hint", entry.get("name", "")))
            if not did:
                print(f"  SKIP (unresolved): {entry.get('name')}")
                continue
            print(f"  resolved {entry.get('name')} -> {did}")
        try:
            view = client.get_views(did)
        except Exception as exc:  # noqa: BLE001
            print(f"  SKIP (fetch failed) {did}: {exc}")
            continue
        cols = [
            {
                "name": c.get("name"),
                "field_name": c.get("fieldName"),
                "datatype": c.get("dataTypeName"),
                "description": c.get("description"),
            }
            for c in (view.get("columns") or [])
        ]
        registry.append(
            {
                "id": did,
                "name": view.get("name"),
                "permalink": f"https://{settings.socrata_domain}/d/{did}",
                "columns": cols,
            }
        )
        print(f"  {did}: {view.get('name')} ({len(cols)} cols)")

    REGISTRY_PATH.write_text(
        yaml.safe_dump({"datasets": registry}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"registry written: {REGISTRY_PATH} ({len(registry)} datasets)")


if __name__ == "__main__":
    main()
