"""Verify dataset `4n4q-k399` is the SECOP-Sancionados dataset and find a join key.

Usage (from apps/backend):
    uv run python -m scripts.verify_secop_sancionados
"""

from __future__ import annotations

import re
import sys

from app.config import settings
from app.socrata.client import SocrataClient

DATASET_ID = "4n4q-k399"
JOIN_KEY_RE = re.compile(r"documento|nit|identificaci[oó]n", re.IGNORECASE)


def main() -> None:
    client = SocrataClient(settings.socrata_domain, settings.socrata_app_token)
    view = client.get_views(DATASET_ID)

    name = view.get("name", "") or ""
    description = view.get("description", "") or ""
    permalink = view.get("permalink") or f"https://{settings.socrata_domain}/d/{DATASET_ID}"
    columns = view.get("columns") or []

    print(f"Dataset id: {DATASET_ID}")
    print(f"Name:       {name}")
    print(f"Permalink:  {permalink}")
    print(f"Description (first 300 chars):\n{description[:300]}")
    print()
    print(f"{'field_name':<40} {'dataTypeName':<20} {'name'}")
    print("-" * 100)
    for col in columns:
        fn = col.get("fieldName", "")
        dt = col.get("dataTypeName", "")
        cn = col.get("name", "")
        print(f"{fn:<40} {dt:<20} {cn}")

    name_ok = bool(re.search(r"sanci|secop", name, re.IGNORECASE))
    if not name_ok:
        print("\nVERIFICATION_FAIL", file=sys.stderr)
        print(
            f"Dataset name {name!r} does not mention 'Sanci' nor 'SECOP'.",
            file=sys.stderr,
        )
        sys.exit(2)

    candidates: list[str] = []
    for col in columns:
        blob = " ".join(str(col.get(k, "") or "") for k in ("name", "description", "fieldName"))
        if JOIN_KEY_RE.search(blob):
            fn = col.get("fieldName", "")
            if fn and fn not in candidates:
                candidates.append(fn)

    if not candidates:
        print("\nVERIFICATION_FAIL", file=sys.stderr)
        print(
            "No column mentions 'documento', 'NIT', or 'identificacion' — no join key.",
            file=sys.stderr,
        )
        sys.exit(2)

    print("\nVERIFICATION_OK")
    print(f"Join-key candidates (fieldNames): {candidates}")


if __name__ == "__main__":
    main()
