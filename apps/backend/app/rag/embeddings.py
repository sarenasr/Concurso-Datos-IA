"""Embeddings via OpenRouter (OpenAI text-embedding-3-small, 768-dim).

Uses OpenRouter's API with the OPENROUTER_API_KEY. The model supports
output_dimensionality=768 via the `dimensions` parameter, matching
our existing Supabase pgvector column and match_catalog RPC.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Iterable

import httpx

from app.config import settings

log = logging.getLogger("datia.rag.embeddings")

EMBEDDING_MODEL = "google/gemini-embedding-2"
EMBEDDING_DIM = 1024
BATCH_SIZE = 96
OPENROUTER_BASE = "https://openrouter.ai/api/v1"


class EmbeddingError(Exception):
    pass


def _get_api_key() -> str:
    key = settings.openrouter_api_key
    if not key:
        raise EmbeddingError("OPENROUTER_API_KEY not configured")
    return key


@lru_cache(maxsize=1)
def _client() -> httpx.Client:
    """Return a shared, long-lived httpx client for embedding requests."""
    return httpx.Client(timeout=60.0)


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    """Embed an iterable of strings (768-dim) via OpenRouter.

    Batches at BATCH_SIZE. Returns a list aligned 1:1 with input order.
    """
    texts = list(texts)
    if not texts:
        return []

    key = _get_api_key()
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    client = _client()
    out: list[list[float]] = []

    for i in range(0, len(texts), BATCH_SIZE):
        chunk = texts[i : i + BATCH_SIZE]

        # Truncate texts to fit OpenAI's 8192 token limit (~6000 chars)
        chunk = [t[:6000] if len(t) > 6000 else t for t in chunk]

        # Retry with exponential backoff for rate limits
        for attempt in range(5):
            try:
                resp = client.post(
                    f"{OPENROUTER_BASE}/embeddings",
                    headers=headers,
                    json={
                        "model": EMBEDDING_MODEL,
                        "input": chunk,
                        "dimensions": EMBEDDING_DIM,
                    },
                    timeout=60.0,
                )
                resp.raise_for_status()
                data = resp.json()

                if "data" not in data:
                    raise ValueError(f"Unexpected response format: {data}")

                out.extend([list(e["embedding"]) for e in data["data"]])
                break  # Success, exit retry loop

            except (httpx.HTTPStatusError, ValueError) as e:
                if attempt == 4:  # Last attempt
                    raise
                wait_time = 2**attempt  # 1, 2, 4, 8, 16 seconds
                print(f"  Retry {attempt + 1}/5 after {wait_time}s: {e}", flush=True)
                import time

                time.sleep(wait_time)

    return out


@lru_cache(maxsize=512)
def embed_text(text: str) -> list[float]:
    """Convenience: embed a single string (cached)."""
    return embed_texts([text])[0]
