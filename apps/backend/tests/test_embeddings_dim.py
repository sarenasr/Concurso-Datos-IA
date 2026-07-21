"""Verify that the embedding dimension is consistent across code and migrations."""

from __future__ import annotations

from pathlib import Path

from app.rag.embeddings import EMBEDDING_DIM, EMBEDDING_MODEL

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_embedding_dim_is_1024() -> None:
    assert EMBEDDING_DIM == 1024


def test_embedding_model_is_gemini_embedding_2() -> None:
    assert EMBEDDING_MODEL == "google/gemini-embedding-2"


def test_migration_004_defines_match_catalog() -> None:
    sql = (_REPO_ROOT / "infra" / "supabase" / "migrations" / "004_match_catalog.sql").read_text()
    assert "create or replace function match_catalog" in sql
