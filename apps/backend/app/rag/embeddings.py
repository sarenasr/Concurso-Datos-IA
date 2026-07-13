"""Embeddings via OpenRouter using the OpenAI Python client.

Uses the official OpenAI client pointed at OpenRouter's API base to
generate embeddings via google/gemini-embedding-2 (1024-dim).
Supports batching with retry/backoff for rate limits.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Iterable

from openai import OpenAI

from app.config import settings

log = logging.getLogger("datia.rag.embeddings")

EMBEDDING_MODEL = "google/gemini-embedding-2"
EMBEDDING_DIM = 1024
BATCH_SIZE = 96
OPENROUTER_BASE = "https://openrouter.ai/api/v1"


class EmbeddingError(Exception):
    pass


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    """Return a shared OpenAI client pointed at OpenRouter."""
    key = settings.openrouter_api_key
    if not key:
        raise EmbeddingError("OPENROUTER_API_KEY not configured")
    return OpenAI(
        base_url=OPENROUTER_BASE,
        api_key=key,
    )


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    """Embed strings (1024-dim) via OpenRouter + OpenAI client.

    Batches at BATCH_SIZE. Returns a list aligned 1:1 with input order.
    """
    texts = list(texts)
    if not texts:
        return []

    client = _client()
    out: list[list[float]] = []

    for i in range(0, len(texts), BATCH_SIZE):
        chunk = texts[i : i + BATCH_SIZE]
        chunk = [t[:6000] if len(t) > 6000 else t for t in chunk]

        for attempt in range(5):
            try:
                resp = client.embeddings.create(
                    model=EMBEDDING_MODEL,
                    input=chunk,
                    dimensions=EMBEDDING_DIM,
                    encoding_format="float",
                    #extra_headers={
                    #    "HTTP-Referer": "https://concurso-datos-ia.vercel.app",
                    #    "X-OpenRouter-Title": "DATIA - Asistente IA Datos Colombia",
                    #},
                )
                out.extend([e.embedding for e in resp.data])
                break

            except Exception as e:
                if attempt == 4:
                    raise
                wait = 2**attempt
                print(f"  Retry {attempt + 1}/5 after {wait}s: {e}", flush=True)
                import time

                time.sleep(wait)

    return out


@lru_cache(maxsize=512)
def embed_text(text: str) -> list[float]:
    """Convenience: embed a single string (cached)."""
    return embed_texts([text])[0]
