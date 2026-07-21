"""Unit tests for Telegram formatting helpers (no live Telegram calls)."""

from __future__ import annotations

import pytest

from app.channels.telegram_bot import (
    TELEGRAM_MAX_LEN,
    _format_chart_info,
    _format_sources,
    _split,
)


@pytest.fixture
def two_sources() -> list[dict]:
    return [
        {"name": "Multas y Sanciones SECOP I", "permalink": "https://example.com/a"},
        {"name": "SECOP II Contratos <&>", "permalink": "https://example.com/b"},
    ]


def test_format_sources_includes_both_names_html_escaped(two_sources: list[dict]) -> None:
    text = _format_sources(two_sources)
    assert "Multas y Sanciones SECOP I" in text
    assert "SECOP II Contratos &lt;&amp;&gt;" in text
    assert 'href="https://example.com/a"' in text
    assert 'href="https://example.com/b"' in text


def test_format_chart_info_none_returns_empty() -> None:
    assert _format_chart_info(None) == ""


def test_format_chart_info_present_returns_note() -> None:
    note = _format_chart_info({"spec": "vega-lite"})
    assert note.strip() != ""
    assert "gr" in note.lower()


def test_split_respects_telegram_limit() -> None:
    long_text = ("x" * (TELEGRAM_MAX_LEN - 5) + "\n") * 3
    chunks = _split(long_text)
    assert all(len(c) <= TELEGRAM_MAX_LEN for c in chunks)
    assert "".join(chunks) == long_text


def test_split_empty_text_returns_empty_list() -> None:
    assert _split("") == []


def test_format_sources_empty_returns_empty() -> None:
    assert _format_sources([]) == ""
