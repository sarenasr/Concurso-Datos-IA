"""Throwaway script: find the SECOP-Sancionados dataset id on datos.gov.co.

Iterates the Socrata catalog v1 search endpoint with several queries and
prints candidates whose name/description mention 'sancionados' AND any of
('SECOP', 'contratación', 'empresa'). The goal is to resolve the `id: TODO`
row in data/priority_datasets.yaml.

Usage (from apps/backend):
    uv run python -m scripts.find_secop_sancionados
"""

from __future__ import annotations

import os
import re
import sys
from urllib.parse import urlencode

import httpx

DOMAIN = "www.datos.gov.co"
BASE = f"https://{DOMAIN}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}
APP_TOKEN = os.environ.get("SOCRATA_APP_TOKEN", "")
if APP_TOKEN:
    HEADERS["X-App-Token"] = APP_TOKEN

QUERIES = [
    "sancionados SECOP",
    "lista sancionados",
    "listado sancionados",
    "sanciones SECOP",
    "sancionados contratación",
    "registro sancionados",
]

SANCTIONED_RE = re.compile(r"sancionad[oa]s|sanciones|sanci[oó]n", re.IGNORECASE)
RELEVANCE_RE = re.compile(r"secop|contrataci[oó]n|empresa|proveedor|registro", re.IGNORECASE)


def search_catalog(q: str, limit: int = 100) -> list[dict]:
    params = {"domains": DOMAIN, "q": q, "limit": limit}
    url = f"{BASE}/api/catalog/v1?{urlencode(params)}"
    with httpx.Client(headers=HEADERS, timeout=30.0) as client:
        r = client.get(url)
        r.raise_for_status()
        data = r.json()
    return data.get("results", []) if isinstance(data, dict) else []


def score(item: dict) -> int:
    resource = item.get("resource", {}) or {}
    name = resource.get("name", "") or ""
    desc = resource.get("description", "") or ""
    blob = f"{name} {desc}"
    s = 0
    if SANCTIONED_RE.search(blob):
        s += 2
    if RELEVANCE_RE.search(blob):
        s += 1
    if "secop" in blob.lower():
        s += 2
    rtype = (resource.get("type") or "").lower()
    if rtype == "dataset":
        s += 1
    return s


def main() -> None:
    seen: dict[str, dict] = {}
    for q in QUERIES:
        print(f"\n--- query: {q!r} ---")
        try:
            results = search_catalog(q, limit=50)
        except Exception as e:
            print(f"  [err] {e}")
            continue
        print(f"  {len(results)} raw results")
        for item in results:
            resource = item.get("resource", {}) or {}
            rid = resource.get("id")
            if not rid or rid in seen:
                continue
            name = resource.get("name", "") or ""
            desc = resource.get("description", "") or ""
            blob = f"{name} {desc}"
            if SANCTIONED_RE.search(blob) and RELEVANCE_RE.search(blob):
                seen[rid] = {
                    "id": rid,
                    "name": name,
                    "description": desc[:200],
                    "permalink": resource.get("permalink", "") or f"{BASE}/d/{rid}",
                    "updatedAt": resource.get("updatedAt", ""),
                    "type": resource.get("type", ""),
                    "score": score(item),
                }

    ranked = sorted(seen.values(), key=lambda x: x["score"], reverse=True)
    print(f"\n=== TOP CANDIDATES ({len(ranked)}) ===")
    for i, c in enumerate(ranked[:10], 1):
        print(f"\n[{i}] score={c['score']}  type={c['type']}")
        print(f"    id:        {c['id']}")
        print(f"    name:      {c['name']}")
        print(f"    desc:      {c['description']}")
        print(f"    permalink: {c['permalink']}")
        print(f"    updated:   {c['updatedAt']}")

    if not ranked:
        print("\nNo candidates found. Broadening search...")
        sys.exit(1)


if __name__ == "__main__":
    main()
