"""Cross-encoder dataset reranker via OpenRouter's hosted rerank endpoint.

After the hybrid retrieval (vector + keyword + priority boost) produces a
ranked list of candidate datasets, this module calls OpenRouter's hosted
cross-encoder rerank model (``cohere/rerank-v3.5`` by default) in ONE HTTP
call to rescore the top candidates against the Spanish query.

Candidates are reordered by the returned ``relevance_score`` (descending).
The chosen relevance is attached as ``rerank_score``.

On ANY failure — missing OpenRouter key, HTTP error, timeout, or malformed/
empty response — the reranker degrades gracefully: it returns the input
list (first ``top_k``, in existing fused-score order) unchanged. This ensures
the reranker is a pure improvement — it can never make things worse than
having no reranker at all, and it never raises.

Reuses the project's existing OpenRouter API key (``settings.openrouter_api_key``);
no separate API key or provider is introduced.
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

log = logging.getLogger("manglar.reranker")

_RERANK_URL = "https://openrouter.ai/api/v1/rerank"
_DOC_MAX_CHARS = 600
_DESC_MAX_CHARS = 400


def _build_document(candidate: dict) -> str:
    """Build a compact "name — description — domain_category" doc string."""
    name = (candidate.get("name") or "").strip()
    desc = (candidate.get("description") or "").strip()[:_DESC_MAX_CHARS]
    category = (candidate.get("domain_category") or "").strip()
    doc = " — ".join(part for part in (name, desc, category) if part)
    return doc[:_DOC_MAX_CHARS]


def _call_rerank_api(query: str, documents: list[str], top_n: int) -> dict:
    """POST to the OpenRouter rerank endpoint. Raises on any error."""
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.rerank_model,
        "query": query,
        "documents": documents,
        "top_n": top_n,
    }
    resp = httpx.post(
        _RERANK_URL, headers=headers, json=payload, timeout=settings.rerank_timeout_s
    )
    resp.raise_for_status()
    return resp.json()


def rerank_datasets(
    query: str,
    candidates: list[dict],
    top_k: int = 5,
) -> list[dict]:
    """Rerank candidate datasets using OpenRouter's hosted cross-encoder.

    Only the top ``settings.rerank_max_candidates`` (by existing fused score)
    are sent to the rerank endpoint in one call. Candidates are reordered by
    the returned ``relevance_score`` (descending), and that score is attached
    as ``rerank_score``.

    On any error — missing OpenRouter key, HTTP failure, timeout, or malformed
    response — returns the input candidates (first ``top_k``, in their
    existing fused-score order) unchanged. Never raises.

    Returns the top ``top_k`` candidates.
    """
    if not candidates:
        return []

    max_candidates = settings.rerank_max_candidates
    scored = sorted(candidates, key=lambda c: float(c.get("score", 0.0)), reverse=True)
    truncated = scored[:max_candidates]
    if len(scored) > max_candidates:
        log.warning(
            "rerank_datasets: truncated %d candidates to %d",
            len(scored),
            max_candidates,
        )

    if not settings.openrouter_api_key:
        log.warning("reranker: no OpenRouter API key configured, skipping rerank")
        return truncated[:top_k]

    documents = [_build_document(c) for c in truncated]
    try:
        data = _call_rerank_api(query, documents, top_k)
    except httpx.TimeoutException as exc:
        log.warning("reranker: OpenRouter rerank call timed out: %s", exc)
        return truncated[:top_k]
    except Exception as exc:  # noqa: BLE001
        log.warning("reranker: OpenRouter rerank call failed: %s", exc)
        return truncated[:top_k]

    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list) or not results:
        log.warning("reranker: malformed or empty results from OpenRouter rerank")
        return truncated[:top_k]

    reranked: list[dict] = []
    for entry in results:
        if not isinstance(entry, dict):
            continue
        try:
            idx = int(entry["index"])
            relevance = float(entry["relevance_score"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= idx < len(truncated):
            c = truncated[idx]
            c["rerank_score"] = relevance
            reranked.append(c)

    if not reranked:
        log.warning("reranker: no usable entries in OpenRouter rerank results")
        return truncated[:top_k]

    reranked.sort(key=lambda c: c["rerank_score"], reverse=True)
    return reranked[:top_k]
