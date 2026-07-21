"""Tests for CORS middleware configuration (allow_credentials vs allow_origins)."""

from __future__ import annotations

import importlib
from unittest.mock import patch

import app.main


def _reload_main() -> None:
    importlib.reload(app.main)


def _restore_defaults() -> None:
    importlib.reload(app.main)


def test_demo_mode_empty_origins_disables_credentials() -> None:
    with patch.object(app.main.settings, "cors_origins", new=[]):
        _reload_main()
        assert app.main._cors_origins == ["*"]
        assert app.main._cors_allow_credentials is False


def test_deployed_mode_nonempty_origins_enables_credentials() -> None:
    with patch.object(app.main.settings, "cors_origins", new=["http://x"]):
        _reload_main()
        assert app.main._cors_origins == ["http://x"]
        assert app.main._cors_allow_credentials is True
