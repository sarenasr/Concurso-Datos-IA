"""Gemini text embeddings via the google-genai SDK.

Uses `text-embedding-004` (768-dimensional). Batched at 100 inputs per request.
Free-tier rate limit is ~1500 rpm / 1m tpm — we batch and retry with backoff.

Import is `from google import genai` (package name on PyPI is `google-genai`).
"""
from __future__ import annotations

from typing import Iterable

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import settings

EMBEDDING_MODEL = "text-embedding-004"
EMBEDDING_DIM = 768
BATCH_SIZE = 100


class EmbeddingError(Exception):
    pass


def _client():
    from google import genai  # imported lazily so the module imports without a key
    return genai.Client(api_key=settings.gemini_api_key)


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _embed_batch(client, texts: list[str]) -> list[list[float]]:
    result = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=texts,
    )
    # google-genai returns an object with `.embeddings`
    return [list(e.values) for e in result.embeddings]


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    """Embed an iterable of strings with Gemini text-embedding-004 (768-dim).

    Batches at 100 inputs. Returns a list aligned 1:1 with the input order.
    """
    texts = list(texts)
    if not texts:
        return []
    client = _client()
    out: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        chunk = texts[i : i + BATCH_SIZE]
        out.extend(_embed_batch(client, chunk))
    return out


def embed_text(text: str) -> list[float]:
    """Convenience: embed a single string."""
    return embed_texts([text])[0]
