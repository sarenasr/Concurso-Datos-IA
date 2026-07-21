import re
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "infra" / "supabase" / "migrations"


def test_migrations_are_contiguous_starting_at_001() -> None:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    assert files, "No migration files found in infra/supabase/migrations/"

    prefixes = []
    for f in files:
        m = re.match(r"\d{3}", f.name)
        assert m, f"Migration file {f.name} does not start with a 3-digit prefix"
        prefixes.append(int(m.group()))

    assert prefixes[0] == 1, f"First migration prefix is {prefixes[0]:03d}, expected 001"

    for i in range(1, len(prefixes)):
        assert prefixes[i] == prefixes[i - 1] + 1, (
            f"Migration gap: {prefixes[i - 1]:03d} -> {prefixes[i]:03d} "
            f"(expected {prefixes[i - 1] + 1:03d})"
        )
