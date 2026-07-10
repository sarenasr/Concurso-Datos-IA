"""Agent tools — LangGraph-compatible functions the agent can call.

Each tool wraps a lower-level module (socrata / rag / graph) so the agent and the
MCP server share the exact same implementations.
"""
from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any

from app.config import settings
from app.graph.loader import graph_neighbors
from app.rag.catalog import search_catalog
from app.socrata.client import SocrataClient

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
REGISTRY_PATH = SCHEMAS_DIR / "registry.yaml"


def _socrata() -> SocrataClient:
    return SocrataClient(settings.socrata_domain, settings.socrata_app_token)


def search_catalog_tool(query: str, sector: str | None = None, k: int = 10) -> list[dict]:
    """Find datasets in the Colombian open-data catalog relevant to a natural-language query.

    Args:
        query: a Spanish natural-language description of the data needed.
        sector: optional domain category filter (e.g. "Salud y Protección Social").
        k: number of results to return.

    Returns:
        List of {id, name, description, score, permalink}.
    """
    return search_catalog(query, sector=sector, k=k)


def get_schema(dataset_id: str) -> dict | None:
    """Return the cached schema (columns + types) for a dataset id.

    Reads from `app/schemas/registry.yaml`, which is populated by
    `scripts/pull_schemas.py`.
    """
    if not REGISTRY_PATH.exists():
        return None
    registry = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    datasets = registry.get("datasets", [])
    for d in datasets:
        if d.get("id") == dataset_id:
            return d
    return None


def query_dataset(dataset_id: str, soql: str) -> list[dict]:
    """Run a SoQL query against a Socrata dataset and return rows.

    Args:
        dataset_id: the 9-char Socrata resource id (e.g. "jbjy-vk9h").
        soql: a SoQL fragment, e.g. "$select=count(*) &$where=departamento='Antioquia'".
    """
    return _socrata().query(dataset_id, soql)


def graph_neighbors_tool(dataset_id: str) -> list[dict]:
    """Return datasets related to `dataset_id` (joinable / same-topic / located-in).

    Returns a list of {dataset_id, label, edge_type, confidence}.
    """
    return graph_neighbors(dataset_id)


def make_chart(
    data: list[dict],
    x: str,
    y: str,
    title: str = "",
    mark: str = "bar",
) -> dict:
    """Build a Vega-Lite spec from tabular data + an x/y intent.

    Args:
        data: list of row dicts (the output of `query_dataset`).
        x: field name to put on the x axis.
        y: field name to put on the y axis.
        title: optional chart title.
        mark: Vega-Lite mark type ("bar", "line", "area", "point").

    Returns:
        A Vega-Lite v5 spec dict the frontend renders directly.
    """
    spec: dict[str, Any] = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "description": title or f"{y} by {x}",
        "data": {"values": data},
        "mark": {"type": mark, "tooltip": True},
        "encoding": {
            "x": {"field": x, "type": "nominal"},
            "y": {"field": y, "type": "quantitative"},
        },
    }
    if title:
        spec["title"] = title
    return spec


# A registry consumed by the LangGraph agent and the MCP server.
TOOLS = {
    "search_catalog": search_catalog_tool,
    "get_schema": get_schema,
    "query_dataset": query_dataset,
    "graph_neighbors": graph_neighbors_tool,
    "make_chart": make_chart,
}
