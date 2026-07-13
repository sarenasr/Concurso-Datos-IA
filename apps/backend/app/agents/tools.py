"""Agent tools — plain Python functions shared by the LangGraph agent and the MCP server.

Each tool wraps a lower-level module (socrata / rag / graph) so the agent and the
MCP server share the exact same implementations. They are intentionally *not*
LangChain tools: plain functions are simpler, more reliable to call, and trivially
exposable via FastMCP.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.config import settings
from app.graph.loader import graph_neighbors as _graph_neighbors
from app.rag.catalog import search_catalog as _rag_search_catalog
from app.socrata.client import SocrataClient

log = logging.getLogger("datia.tools")

REGISTRY_PATH = Path(__file__).resolve().parent.parent / "schemas" / "registry.yaml"

_DATE_HINTS = ("fecha", "mes", "año", "ano", "date", "vigencia")


@lru_cache(maxsize=1)
def _socrata() -> SocrataClient:
    """Build a SocrataClient configured for datos.gov.co (cached singleton)."""
    return SocrataClient(settings.socrata_domain, settings.socrata_app_token)


@lru_cache(maxsize=1)
def _load_registry() -> dict:
    """Load and cache the schema registry YAML as a dict."""
    if not REGISTRY_PATH.exists():
        return {}
    return yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}


def search_catalog(query: str, k: int = 5) -> list[dict]:
    """Find datasets in the Colombian open-data catalog relevant to a query.

    Args:
        query: a Spanish natural-language description of the data needed.
        k: number of results to return.

    Returns:
        List of {id, name, description, domain_category, permalink, score}.
    """
    try:
        rows = _rag_search_catalog(query=query, k=k)
    except Exception as exc:  # noqa: BLE001
        log.exception("search_catalog failed: %s", exc)
        return []
    out: list[dict] = []
    domain = settings.socrata_domain
    for r in rows:
        out.append(
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "description": (r.get("description") or "")[:200],
                "domain_category": r.get("domain_category"),
                "permalink": r.get("permalink") or f"https://{domain}/d/{r.get('id')}",
                "score": r.get("score"),
            }
        )
    return out


def get_schema(dataset_id: str) -> dict | None:
    """Return the schema for a dataset id, always from the live Socrata API.

    Returns a dict shaped like {id, name, permalink, columns: [...]} where each
    column is {name, field_name, datatype, description}.

    Always fetches from the live API to ensure correct column names (the registry
    YAML has encoding-corrupted field names that cause bad SoQL queries).
    """
    try:
        views = _socrata().get_views(dataset_id)
        columns = []
        for col in views.get("columns", []):
            columns.append(
                {
                    "name": col.get("name", ""),
                    "field_name": col.get("fieldName", ""),
                    "datatype": col.get("dataTypeName", ""),
                    "description": col.get("description", ""),
                }
            )

        domain = settings.socrata_domain
        return {
            "id": dataset_id,
            "name": views.get("name", dataset_id),
            "permalink": f"https://{domain}/d/{dataset_id}",
            "columns": columns,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to fetch schema from API for %s: %s", dataset_id, exc)
        return None


def query_dataset(dataset_id: str, soql: str) -> dict:
    """Run a SoQL query against a Socrata dataset.

    Args:
        dataset_id: the 9-char Socrata resource id (e.g. "jbjy-vk9h").
        soql: a SoQL fragment, e.g. "$select=count(*) &$where=departamento='Antioquia'".

    Returns:
        {rows: list[dict], count: int, error: str | None}. Exceptions are captured
        into ``error`` so the agent can self-correct.
    """
    try:
        rows = _socrata().query(dataset_id, soql)
    except Exception as exc:  # noqa: BLE001
        log.warning("query_dataset %s failed: %s", dataset_id, exc)
        return {"rows": [], "count": 0, "error": str(exc)}
    return {"rows": rows, "count": len(rows), "error": None}


def graph_neighbors(dataset_id: str) -> list[dict]:
    """Return datasets related to `dataset_id` (joinable / same-topic).

    Returns a list of {dataset_id, label, edge_type, confidence} sorted by confidence.
    """
    try:
        return _graph_neighbors(dataset_id)
    except Exception as exc:  # noqa: BLE001
        log.exception("graph_neighbors failed: %s", exc)
        return []


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _looks_like_date(key: str) -> bool:
    low = key.lower()
    return any(h in low for h in _DATE_HINTS)


def make_chart(
    data: list[dict],
    title: str = "",
    chart_type: str = "auto",
) -> dict:
    """Build a Vega-Lite v5 spec from tabular data.

    For ``chart_type="auto"`` the mark is chosen by heuristics:

    - **line** when one of the keys looks like a date (time series).
    - **bar** when at least one column is numeric (categorical comparison).
    - **table** (text mark) otherwise.

    An explicit ``chart_type`` ("bar", "line", "table") overrides the heuristic.
    Returns an empty dict when there is no data or fewer than 2 columns.
    """
    if not data:
        return {}
    sample = data[0]
    keys = list(sample.keys())
    if len(keys) < 2:
        return {}

    numeric_field = next((k for k in keys if _is_number(sample[k])), None)
    date_field = next((k for k in keys if _looks_like_date(k)), None)

    if chart_type == "auto":
        if date_field is not None:
            chart_type = "line"
        elif numeric_field is not None:
            chart_type = "bar"
        else:
            chart_type = "table"
    elif chart_type not in ("bar", "line", "table"):
        chart_type = "bar"

    spec: dict[str, Any] = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "data": {"values": data[:200]},
    }
    if title:
        spec["title"] = title

    if chart_type == "table":
        spec["mark"] = {"type": "text"}
        return spec

    x_field = date_field or next((k for k in keys if k != numeric_field), keys[0])
    y_field = numeric_field or keys[-1]
    x_type = "temporal" if (chart_type == "line" and x_field == date_field) else "nominal"

    spec["mark"] = {"type": chart_type, "tooltip": True}
    spec["encoding"] = {
        "x": {"field": x_field, "type": x_type},
        "y": {"field": y_field, "type": "quantitative"},
    }
    if len(data) > 12 and chart_type == "bar":
        spec["encoding"]["x"]["sort"] = "-y"
    return spec


# A registry consumed by the LangGraph agent and the MCP server.
TOOLS = {
    "search_catalog": search_catalog,
    "get_schema": get_schema,
    "query_dataset": query_dataset,
    "graph_neighbors": graph_neighbors,
    "make_chart": make_chart,
}
