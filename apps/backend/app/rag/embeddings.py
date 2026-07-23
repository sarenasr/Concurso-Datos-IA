"""Embeddings via OpenRouter using the OpenAI Python client.

Uses the official OpenAI client pointed at OpenRouter's API base to
generate embeddings via google/gemini-embedding-2 (1024-dim).
Supports batching with retry/backoff for rate limits.

NOTE on task_type: Gemini embeddings are asymmetric and are meant to be
called with a `task_type` of RETRIEVAL_DOCUMENT (for corpus docs) vs.
RETRIEVAL_QUERY (for the live search query) to maximize recall. The only
live embedding path here goes through OpenRouter's OpenAI-compatible
`/embeddings` endpoint, which does NOT expose a `task_type` parameter (it
maps to the OpenAI embeddings schema, not the native Gemini
`EmbedContentConfig`). `google-genai` is a project dependency but is not
wired up for embeddings anywhere in this codebase; switching the live
calls to it would very likely produce a *different* vector space than the
one already stored in `catalog_embeddings.embedding` (produced through
OpenRouter's "google/gemini-embedding-2" routing), since a different
client/endpoint can normalize or version the model differently. Doing
that safely would require validating vector-space compatibility (or
accepting a full re-embed of the catalog) — this must be an explicit,
separate decision, not a silent switch.

For now, `task_type` is accepted as a documented no-op passthrough (see
`embed_texts`/`embed_text`) so callers can already express intent
(RETRIEVAL_DOCUMENT vs RETRIEVAL_QUERY) without changing behavior. Flip it
to actually affect the request only after confirming the target path
supports it and preserves the existing 1024-dim vector space.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Iterable

from openai import OpenAI

from app.config import settings

log = logging.getLogger("manglar.rag.embeddings")

EMBEDDING_MODEL = "google/gemini-embedding-2"
EMBEDDING_DIM = 1024
BATCH_SIZE = 96
OPENROUTER_BASE = "https://openrouter.ai/api/v1"

# Gemini task_type values (see module docstring re: current no-op status).
TASK_TYPE_DOCUMENT = "RETRIEVAL_DOCUMENT"
TASK_TYPE_QUERY = "RETRIEVAL_QUERY"


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


def embed_texts(texts: Iterable[str], task_type: str | None = None) -> list[list[float]]:
    """Embed strings (1024-dim) via OpenRouter + OpenAI client.

    Batches at BATCH_SIZE. Returns a list aligned 1:1 with input order.

    `task_type` (e.g. TASK_TYPE_DOCUMENT / TASK_TYPE_QUERY) lets callers
    express Gemini retrieval intent (document vs. query), but is currently
    a NO-OP: the live path is OpenRouter's OpenAI-compatible endpoint,
    which has no `task_type` param. See module docstring for why this
    isn't silently implemented via a different client/model.
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
                    # extra_headers={
                    #    "HTTP-Referer": "https://concurso-datos-ia.vercel.app",
                    #    "X-OpenRouter-Title": "Manglar - Asistente IA Datos Colombia",
                    # },
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
def embed_text(text: str, task_type: str | None = None) -> list[float]:
    """Convenience: embed a single string (cached).

    `task_type` is a passthrough no-op today — see `embed_texts` docstring.
    """
    return embed_texts([text], task_type=task_type)[0]
