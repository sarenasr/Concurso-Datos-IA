"""End-to-end test for the MCP make_chart wrapper.

Proves the wrapper forwards keyword args (``title``, ``chart_type``) to
:func:`app.agents.tools.make_chart` correctly — the bug fixed in this changeset
was that the wrapper previously passed ``intent=...`` which does not exist on
the underlying function, causing a ``TypeError`` at runtime.
"""

from __future__ import annotations

from app.agents.tools import make_chart
from app.mcp_server.server import make_chart_tool


SAMPLE = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]


def test_make_chart_tool_auto_returns_vegalite_spec() -> None:
    spec = make_chart_tool(SAMPLE, title="X")

    assert "$schema" in spec and "vega-lite" in spec["$schema"]
    assert "mark" in spec


def test_make_chart_tool_forced_bar_mark() -> None:
    spec = make_chart_tool(SAMPLE, title="X", chart_type="bar")

    mark = spec["mark"]
    mark_type = mark["type"] if isinstance(mark, dict) else mark
    assert mark_type == "bar"


def test_make_chart_tool_signature_matches_underlying() -> None:
    """The wrapper must accept the same kwargs as the underlying function."""
    direct = make_chart(SAMPLE, title="Direct", chart_type="auto")
    wrapped = make_chart_tool(SAMPLE, title="Direct", chart_type="auto")
    assert direct == wrapped


def test_make_chart_detects_socrata_stringified_numbers() -> None:
    spec = make_chart(
        [{"municipio": "MedellÃ­n", "total": "120"}, {"municipio": "Envigado", "total": "80"}]
    )

    assert spec["mark"]["type"] == "bar"
    assert spec["encoding"]["y"]["field"] == "total"
