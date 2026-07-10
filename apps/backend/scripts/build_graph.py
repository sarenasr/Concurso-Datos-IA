"""CLI: build the dataset knowledge graph for priority datasets.

Usage:
    uv run python -m scripts.build_graph
"""
from __future__ import annotations

from pathlib import Path

import yaml

from app.graph.builder import build_graph

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PRIORITY_FILE = DATA_DIR / "priority_datasets.yaml"


def main() -> None:
    priority = yaml.safe_load(PRIORITY_FILE.read_text(encoding="utf-8")) or {}
    entries = priority.get("priority_datasets", [])
    # only build for resolved (non-TODO) ids
    dataset_ids = [e["id"] for e in entries if e.get("id") and e["id"] != "TODO"]
    if not dataset_ids:
        print("no resolved dataset ids to build; run pull_schemas first")
        return
    print(f"building graph for {len(dataset_ids)} datasets")
    report = build_graph(dataset_ids)
    print(report)


if __name__ == "__main__":
    main()
