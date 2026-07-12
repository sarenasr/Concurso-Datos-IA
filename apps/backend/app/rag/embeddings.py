"""Gemini embedding-001 embeddings via the google-genai SDK (768-dim).

Replaces the local sentence-transformers model (1.1GB RAM) with API-based
embeddings that are free on Gemini's generous free tier.  The model produces
768-dim vectors via ``output_dimensionality=768``, keeping the existing
Supabase pgvector column and ``match_catalog`` RPC compatible with no schema
migration.

Uses the ``GEMINI_API_KEY`` / ``GEMINI_API_KEYS`` env vars already configured
in the project's ``.env`` for quota cycling across multiple free-tier keys.
"""

from __future__ import annotations

import logging
import random
from typing import Iterable

from google import genai
from google.genai import types

from app.config import settings

log = logging.getLogger("datia.rag.embeddings")

EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 768
BATCH_SIZE = 100


class EmbeddingError(Exception):
    """Raised when an embedding API call fails with no recovery path."""


def _get_client() -> genai.Client:
    """Build a google-genai Client with a random key from the pool."""
    keys = settings.gemini_keys_list
    if not keys:
        raise EmbeddingError(
            "No GEMINI_API_KEY or GEMINI_API_KEYS configured. Set one in .env to enable embeddings."
        )
    api_key = random.choice(keys)
    return genai.Client(api_key=api_key)


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    """Embed an iterable of strings (768-dim) via Gemini's embedding API.

    Batches at ``BATCH_SIZE``.  Returns a list aligned 1:1 with the input
    order.  Raises ``EmbeddingError`` if the API call fails.
    """
    texts = list(texts)
    if not texts:
        return []

    client = _get_client()
    config = types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIM)
    out: list[list[float]] = []

    for i in range(0, len(texts), BATCH_SIZE):
        chunk = texts[i : i + BATCH_SIZE]
        try:
            resp = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=chunk,
                config=config,
            )
            out.extend([list(e.values) for e in resp.embeddings])
        except Exception as exc:
            log.error("gemini embed_content failed (batch %d): %s", i, exc)
            raise EmbeddingError(f"Embedding API call failed: {exc}") from exc

    return out


def embed_text(text: str) -> list[float]:
    """Convenience: embed a single string."""
    return embed_texts([text])[0]
