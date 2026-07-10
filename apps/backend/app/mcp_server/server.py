"""FastMCP server exposing the same tools the LangGraph agent uses.

Runnable standalone:
    uv run python -m app.mcp_server.server
"""
from __future__ import annotations

from app.agents import tools as T
from app.mcp_server import server as _self  # noqa: F401 (avoid name clash helper)


def _make_server():
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("datia")

    @mcp.tool()
    def search_catalog(query: str, sector: str | None = None, k: int = 10) -> list[dict]:
        """Find Colombian open-data datasets relevant to a natural-language query."""
        return T.search_catalog_tool(query, sector=sector, k=k)

    @mcp.tool()
    def get_schema(dataset_id: str) -> dict | None:
        """Return the cached schema (columns + types) for a dataset id."""
        return T.get_schema(dataset_id)

    @mcp.tool()
    def query_dataset(dataset_id: str, soql: str) -> list[dict]:
        """Run a SoQL query against a Socrata dataset and return rows."""
        return T.query_dataset(dataset_id, soql)

    @mcp.tool()
    def graph_neighbors(dataset_id: str) -> list[dict]:
        """Return datasets related to a dataset (joinable / same-topic / located-in)."""
        return T.graph_neighbors_tool(dataset_id)

    @mcp.tool()
    def make_chart(data: list[dict], x: str, y: str, title: str = "", mark: str = "bar") -> dict:
        """Build a Vega-Lite spec from tabular data + an x/y intent."""
        return T.make_chart(data, x=x, y=y, title=title, mark=mark)

    return mcp


server = _make_server()


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
