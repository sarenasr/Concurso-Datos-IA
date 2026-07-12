"""In-memory graph loader.

Loads `graph_nodes` + `graph_edges` from Supabase into a networkx graph and
exposes `graph_neighbors(dataset_id)` so the agent can find joinable / related
datasets.
"""

from __future__ import annotations

import networkx as nx

from app.config import settings

_GRAPH: nx.Graph | None = None


def _supabase():
    from supabase import create_client

    return create_client(settings.supabase_url, settings.supabase_key_resolved)


def load_graph() -> nx.Graph:
    """Build a networkx graph from Supabase tables (cached for the process)."""
    global _GRAPH
    if _GRAPH is not None:
        return _GRAPH
    sb = _supabase()
    nodes = sb.table("graph_nodes").select("*").execute().data
    edges = sb.table("graph_edges").select("*").execute().data
    g = nx.Graph()
    for n in nodes:
        g.add_node(n["id"], **{k: v for k, v in n.items() if k != "id"})
    for e in edges:
        if g.has_node(e["src"]) and g.has_node(e["dst"]):
            g.add_edge(
                e["src"],
                e["dst"],
                type=e["type"],
                confidence=e.get("confidence"),
                extra=e.get("extra"),
            )
    _GRAPH = g
    return g


def graph_neighbors(dataset_id: str) -> list[dict]:
    """Return neighbor datasets of `dataset_id` with edge type + confidence."""
    g = load_graph()
    if not g.has_node(dataset_id):
        return []
    out = []
    for _, nbr, data in g.edges(dataset_id, data=True):
        node = g.nodes[nbr]
        out.append(
            {
                "dataset_id": nbr,
                "label": node.get("label"),
                "edge_type": data.get("type"),
                "confidence": data.get("confidence"),
            }
        )
    out.sort(key=lambda x: x.get("confidence") or 0, reverse=True)
    return out


def reset_cache() -> None:
    global _GRAPH
    _GRAPH = None
