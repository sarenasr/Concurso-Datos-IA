"""Offline retrieval recall@k eval. Treats hero_questions.yaml as ground truth.

For each hero question:
  - calls app.rag.catalog.search_catalog(question, k=N)
  - checks whether the listed `datasets` for that question appear in the top-N
    results
  - reports recall@N for N in {1, 3, 5, 10}

Prints a per-question table + aggregate recall@k.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.rag.eval_utils import compute_recall_at_k

log = logging.getLogger("manglar.eval.retrieval")


def _load_hero_questions() -> list[dict]:
    """Re-export the graph's loader so the eval stays zero-hardcoding."""
    from app.agents.graph import _load_hero_questions as _graph_load

    return _graph_load()


def _eval_one(question: str, truth_ids: list[str], max_k: int) -> dict[str, Any]:
    """Call search_catalog once at max_k and derive recall@k for each k."""
    from app.rag.catalog import search_catalog

    t0 = time.time()
    try:
        results = search_catalog(question, k=max_k)
    except Exception as exc:
        log.exception("search_catalog failed for question: %s", question[:60])
        return {
            "error": str(exc),
            "returned_ids": [],
            "recall": {},
            "elapsed_s": time.time() - t0,
        }

    returned_ids = [r.get("id") for r in results if r.get("id")]
    recall: dict[str, float] = {}
    # Computed lazily per configured k in main(); here we just stash the ids.
    return {
        "error": None,
        "returned_ids": returned_ids,
        "recall": recall,
        "elapsed_s": time.time() - t0,
    }


def _truncate(text: str, max_len: int = 50) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _print_table(rows: list[dict], k_values: list[int]) -> None:
    """Print a compact per-hero recall table to stdout."""
    k_headers = [f"r@{k}" for k in k_values]
    header = ["id", "question", *k_headers, "ms"]
    widths = [3, 52, *[5 for _ in k_values], 6]

    def _fmt(cells: list[str]) -> str:
        return "  ".join(c.ljust(w) for c, w in zip(cells, widths))

    print(_fmt(header))
    print("-" * sum(widths + [2 * (len(widths) - 1)]))
    for r in rows:
        q_short = _truncate(r["question"], 52)
        recall_cells = [f"{r['recall'][k]:.2f}" for k in k_values]
        cells = [str(r["id"]), q_short, *recall_cells, f"{int(r['ms'])}"]
        print(_fmt(cells))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline retrieval recall@k eval against hero_questions.yaml."
    )
    parser.add_argument(
        "--k",
        default="1,3,5,10",
        help="Comma-separated list of k values for recall@k (default: 1,3,5,10)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Evaluate only the first N hero questions (0 = all)",
    )
    args = parser.parse_args(argv)

    try:
        k_values = sorted({int(x.strip()) for x in args.k.split(",") if x.strip()})
    except ValueError:
        print("ERROR: --k must be a comma-separated list of integers", file=sys.stderr)
        return 2
    if not k_values or min(k_values) < 1:
        print("ERROR: --k values must all be >= 1", file=sys.stderr)
        return 2

    heroes = _load_hero_questions()
    if not heroes:
        print("ERROR: hero_questions.yaml está vacío o no existe", file=sys.stderr)
        return 1

    if args.limit > 0:
        heroes = heroes[: args.limit]

    max_k = max(k_values)

    print(f"= Eval retrieval@k — {len(heroes)} preguntas, k={k_values}, max_k={max_k} =")
    print()

    rows: list[dict] = []
    aggregate: dict[int, list[float]] = {k: [] for k in k_values}

    for hero in heroes:
        qid = hero.get("id")
        question = hero.get("question", "")
        truth_ids = [d for d in (hero.get("datasets") or []) if d and d != "TODO"]

        if not truth_ids:
            # Nothing to measure against; skip but record a row for visibility.
            rows.append(
                {
                    "id": qid,
                    "question": question,
                    "recall": {k: 0.0 for k in k_values},
                    "ms": 0,
                    "skipped": True,
                }
            )
            continue

        result = _eval_one(question, truth_ids, max_k)
        if result["error"]:
            print(f"  [!] Q{qid} falló: {result['error']}", file=sys.stderr)
            rows.append(
                {
                    "id": qid,
                    "question": question,
                    "recall": {k: 0.0 for k in k_values},
                    "ms": int(result["elapsed_s"] * 1000),
                    "skipped": False,
                    "error": result["error"],
                }
            )
            continue

        returned = result["returned_ids"]
        recall_row = {k: compute_recall_at_k(returned, truth_ids, k) for k in k_values}
        for k in k_values:
            aggregate[k].append(recall_row[k])

        rows.append(
            {
                "id": qid,
                "question": question,
                "recall": recall_row,
                "ms": int(result["elapsed_s"] * 1000),
                "skipped": False,
            }
        )

    _print_table(rows, k_values)

    print()
    print("= Agregado =")
    for k in k_values:
        vals = aggregate[k]
        if not vals:
            print(f"  recall@{k:<2} =  n/a  (sin preguntas evaluables)")
            continue
        mean = sum(vals) / len(vals)
        print(f"  recall@{k:<2} = {mean:.3f}  (n={len(vals)})")

    # Optional JSON side-artifact
    out_path = (
        Path(__file__).resolve().parent.parent
        / "data"
        / f"eval_retrieval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    try:
        out_path.write_text(
            json.dumps(
                {
                    "k_values": k_values,
                    "aggregate": {
                        k: (sum(v) / len(v) if v else None) for k, v in aggregate.items()
                    },
                    "rows": [
                        {
                            "id": r["id"],
                            "question": r["question"],
                            "recall": r["recall"],
                            "ms": r["ms"],
                        }
                        for r in rows
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nJSON guardado en: {out_path}")
    except OSError as exc:
        print(f"\n(no se pudo escribir JSON: {exc})", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
