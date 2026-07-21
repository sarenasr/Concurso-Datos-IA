"""Tests for ``app.config.Settings`` — env-var parsing."""

from __future__ import annotations

from app.config import Settings


def _fresh(**overrides) -> Settings:
    """Build a Settings instance without reading any .env file on disk."""
    return Settings(_env_file=None, **overrides)


def test_cors_origins_parses_comma_separated_string() -> None:
    s = _fresh(cors_origins="http://a.com,http://b.com")
    assert s.cors_origins == ["http://a.com", "http://b.com"]


def test_cors_origins_list_passes_through_unchanged() -> None:
    s = _fresh(cors_origins=["x"])
    assert s.cors_origins == ["x"]


def test_cors_origins_default_is_two_element_list() -> None:
    s = _fresh()
    assert s.cors_origins == [
        "http://localhost:3000",
        "https://concurso-datos-ia.vercel.app",
    ]


def test_cors_origins_strips_whitespace_and_drops_empties() -> None:
    s = _fresh(cors_origins=" http://a.com , , http://b.com , ")
    assert s.cors_origins == ["http://a.com", "http://b.com"]
