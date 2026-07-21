"""Guard test: ensure dead registry.yaml / pull_schemas references stay removed.

The schema registry YAML and the script that generated it were deleted to reduce
surface area (no cache-invalidation race for a hackathon). These assertions prevent
anyone from accidentally re-introducing references to the removed artefacts.
"""

from __future__ import annotations

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = BACKEND_ROOT / "app"
SCRIPTS_DIR = BACKEND_ROOT / "scripts"

FORBIDDEN_SUBSTRINGS = ("registry.yaml", "pull_schemas")


def _iter_python_files(*roots: Path) -> list[Path]:
    """Collect every ``.py`` file under the given directories."""
    files: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        files.extend(root.glob("**/*.py"))
    return files


def test_no_python_file_references_registry_yaml_or_pull_schemas() -> None:
    """No ``.py`` under app/ or scripts/ may mention registry.yaml or pull_schemas."""
    py_files = _iter_python_files(APP_DIR, SCRIPTS_DIR)
    assert py_files, "expected at least one .py file under app/ or scripts/"

    violations: list[str] = []
    for path in py_files:
        try:
            text = path.read_text(encoding="utf-8").lower()
        except (UnicodeDecodeError, OSError):
            continue
        for forbidden in FORBIDDEN_SUBSTRINGS:
            if forbidden.lower() in text:
                rel = path.relative_to(BACKEND_ROOT)
                violations.append(f"{rel} contains '{forbidden}'")

    assert not violations, "Dead-code references found:\n  " + "\n  ".join(violations)


def test_registry_yaml_does_not_exist() -> None:
    """The file ``app/schemas/registry.yaml`` must not exist."""
    target = APP_DIR / "schemas" / "registry.yaml"
    assert not target.exists(), f"dead file still present: {target}"


def test_pull_schemas_script_does_not_exist() -> None:
    """The file ``scripts/pull_schemas.py`` must not exist."""
    target = SCRIPTS_DIR / "pull_schemas.py"
    assert not target.exists(), f"dead file still present: {target}"
