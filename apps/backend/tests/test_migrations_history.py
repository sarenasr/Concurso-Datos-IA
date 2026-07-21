from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "infra" / "supabase" / "migrations"


def test_002_embeddings_uses_768_dim() -> None:
    sql = (MIGRATIONS_DIR / "002_embeddings.sql").read_text(encoding="utf-8")
    assert "vector(768)" in sql
    assert "vector(1024)" not in sql


def test_005_fix_embedding_dim_contents() -> None:
    sql = (MIGRATIONS_DIR / "005_fix_embedding_dim.sql").read_text(encoding="utf-8")
    assert "alter column embedding type vector(1024)" in sql
    assert "truncate table catalog_embeddings" in sql
    assert "drop index if exists catalog_embeddings_embedding_idx" in sql


def test_migrations_have_strictly_ascending_prefixes() -> None:
    prefixes = [
        int(p.name.split("_", 1)[0])
        for p in sorted(MIGRATIONS_DIR.iterdir())
        if p.is_file() and p.suffix == ".sql" and p.name.split("_", 1)[0].isdigit()
    ]
    assert prefixes == sorted(prefixes)
    assert len(prefixes) == len(set(prefixes))
