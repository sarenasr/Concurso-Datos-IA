"""Smoke-test Telegram formatting helpers against a fake JOIN agent state.

Usage (from apps/backend):
    uv run python -m scripts.verify_telegram_format
"""

from __future__ import annotations

import sys

from app.channels.telegram_bot import (
    TELEGRAM_MAX_LEN,
    _format_chart_info,
    _format_sources,
    _split,
)


def main() -> None:
    sources = [
        {"name": "Multas y Sanciones SECOP I", "permalink": "https://example.com/a"},
        {"name": "SECOP II Contratos <&>", "permalink": "https://example.com/b"},
    ]

    sources_text = _format_sources(sources)
    print("--- _format_sources ---")
    print(sources_text)
    assert "Multas y Sanciones SECOP I" in sources_text
    assert "SECOP II Contratos &lt;&amp;&gt;" in sources_text, sources_text

    chart_none = _format_chart_info(None)
    print("\n--- _format_chart_info(None) ---")
    print(repr(chart_none))
    assert chart_none == ""

    chart_yes = _format_chart_info({"spec": "vega-lite"})
    print("\n--- _format_chart_info({...}) ---")
    print(chart_yes)
    assert chart_yes.strip() != ""

    long_text = ("x" * (TELEGRAM_MAX_LEN - 5) + "\n") * 3
    chunks = _split(long_text)
    print(f"\n--- _split: {len(chunks)} chunks, lens={[len(c) for c in chunks]} ---")
    assert all(len(c) <= TELEGRAM_MAX_LEN for c in chunks), [len(c) for c in chunks]
    assert "".join(chunks) == long_text

    state = {
        "answer": "Respuesta del JOIN con 2 fuentes.",
        "sources": sources,
        "chart": None,
    }
    assert state.get("answer")
    assert len(state.get("sources") or []) == 2
    assert state.get("chart") is None

    print("\nVERIFICATION_OK")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"VERIFICATION_FAIL: {e}", file=sys.stderr)
        sys.exit(2)
