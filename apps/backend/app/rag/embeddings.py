"""Local multilingual embeddings via sentence-transformers.

Uses `paraphrase-multilingual-mpnet-base-v2` (768-dim, ~1.1GB download on first use).
No API key, no rate limits, runs fully offline after first download.
Strong multilingual support (Spanish, English, etc.).
"""

from __future__ import annotations

from typing import Iterable

EMBEDDING_MODEL = "paraphrase-multilingual-mpnet-base-v2"
EMBEDDING_DIM = 768
BATCH_SIZE = 64

_model = None


class EmbeddingError(Exception):
    pass


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        print(
            f"  loading embedding model '{EMBEDDING_MODEL}' (first run downloads ~1.1GB)...",
            flush=True,
        )
        _model = SentenceTransformer(EMBEDDING_MODEL)
        print("  model loaded", flush=True)
    return _model


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    """Embed an iterable of strings (768-dim, multilingual).

    Batches at BATCH_SIZE. Returns a list aligned 1:1 with the input order.
    """
    texts = list(texts)
    if not texts:
        return []
    model = _get_model()
    vectors = model.encode(
        texts, batch_size=BATCH_SIZE, show_progress_bar=False, convert_to_numpy=True
    )
    return [list(map(float, v)) for v in vectors]


def embed_text(text: str) -> list[float]:
    """Convenience: embed a single string."""
    return embed_texts([text])[0]
