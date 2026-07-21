"""FastMCP server exposing the same tools the LangGraph agent uses.

Runnable standalone:
    uv run python -m app.mcp_server.server

The five tools mirror :mod:`app.agents.tools` so external MCP clients get the
exact same implementations as the in-process agent.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.agents.tools import (
    get_schema,
    graph_neighbors,
    make_chart,
    query_dataset,
    search_catalog,
)

mcp = FastMCP("Manglar")


@mcp.tool()
def search_catalog_tool(query: str, k: int = 5) -> list[dict]:
    """Search the Colombian open data catalog for datasets matching a natural language query."""
    return search_catalog(query, k)


@mcp.tool()
def get_schema_tool(dataset_id: str) -> dict | None:
    """Return the cached schema (columns + types) for a Socrata dataset id."""
    return get_schema(dataset_id)


@mcp.tool()
def query_dataset_tool(dataset_id: str, soql: str) -> dict:
    """Run a SoQL query against a Socrata dataset.

    Returns ``{rows: list[dict], count: int, error: str | None}``.
    """
    return query_dataset(dataset_id, soql)


@mcp.tool()
def graph_neighbors_tool(dataset_id: str) -> list[dict]:
    """Return datasets related to a dataset (joinable / same-topic / located-in)."""
    return graph_neighbors(dataset_id)


@mcp.tool()
def make_chart_tool(
    data: list[dict],
    title: str = "",
    chart_type: str = "auto",
) -> dict:
    """Build a Vega-Lite spec from tabular data.

    Args:
        data: rows as a list of flat dicts (all rows share the same keys).
        title: optional chart title rendered into the spec.
        chart_type: ``"auto"`` (default) picks the mark heuristically; pass
            ``"bar"``, ``"line"``, or ``"table"`` to force one.
    """
    return make_chart(data, title=title, chart_type=chart_type)


if __name__ == "__main__":
    mcp.run()
