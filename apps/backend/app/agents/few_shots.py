"""Few-shot SoQL patterns loaded from `app/few_shots/patterns.json`."""

from __future__ import annotations

import json
from pathlib import Path

PATTERNS_PATH = Path(__file__).resolve().parent.parent / "few_shots" / "patterns.json"


def load_patterns() -> list[dict]:
    """Return the list of SoQL few-shot patterns."""
    if not PATTERNS_PATH.exists():
        return []
    return json.loads(PATTERNS_PATH.read_text(encoding="utf-8")).get("patterns", [])
