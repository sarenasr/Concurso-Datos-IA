"""LLM-based dataset reranker (batched).

After the hybrid retrieval (vector + keyword + priority boost) produces a ranked
list of candidate datasets, this module asks a small LLM to score ALL candidates
in ONE call, returning a JSON object ``{id: score}`` with relevance on a 0-1 scale.
The final score blends the existing fused score with the LLM relevance::

    final = 0.5 * (base_fused_score / max_base) + 0.5 * llm_relevance_score

On any LLM error, parse failure, or timeout the reranker degrades gracefully:
it returns the input list ranked by the existing fused score. This ensures the
reranker is a pure improvement — it can never make things worse than having no
reranker at all.

A delta-skip optimisation skips the LLM call entirely when the top-2 candidates'
existing scores differ by more than ``RERANK_DELTA`` — i.e. when the result is
already unambiguous.
"""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor

from app.config import settings

log = logging.getLogger("manglar.reranker")

RERANK_DELTA = 0.05

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)
_FENCE_RE = re.compile(r"^```(?:json)?|```$", re.MULTILINE)


def _build_batch_prompt(query: str, candidates: list[dict]) -> list[dict]:
    """Build ONE prompt listing every candidate and asking for a JSON score map."""
    rows = []
    for c in candidates:
        cid = c.get("id", "")
        name = (c.get("name") or "").replace("|", "–")
        desc = (c.get("description") or "")[:120].replace("|", "–").replace("\n", " ")
        rows.append(f"- {cid} | {name} | {desc}")
    body = "\n".join(rows)
    content = (
        "Eres un juez de pertinencia. Califica cada dataset según qué tan bien "
        "responde la pregunta del usuario. Devuelve SOLO JSON con la forma "
        '{"<id>": <score 0-1>, ...} sin texto extra, sin markdown.\n\n'
        f"Pregunta: {query}\n\nCandidatos:\n{body}\n\nJSON:"
    )
    return [{"role": "user", "content": content}]


def _parse_scores(raw: str) -> dict[str, float] | None:
    """Extract ``{id: score}`` from LLM output. Returns ``None`` on failure."""
    text = raw.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        cleaned = _FENCE_RE.sub("", text).strip()
        m = _JSON_BLOCK_RE.search(cleaned)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    out: dict[str, float] = {}
    for k, v in data.items():
        try:
            score = float(v)
        except (TypeError, ValueError):
            continue
        out[str(k)] = max(0.0, min(1.0, score))
    return out or None


def _call_llm_with_timeout(messages: list[dict]) -> str:
    """Call ``llm_complete_small`` bounded by ``settings.rerank_timeout_s``.

    Raises whatever the underlying call raises on failure, or ``TimeoutError``
    if the call exceeds the budget.
    """
    from app.agents.llm import llm_complete_small

    # NOTE: do NOT use `with ThreadPoolExecutor(...)`. The context manager calls
    # shutdown(wait=True) on exit, so on a TimeoutError it would block until the
    # slow LLM call finishes anyway — defeating the timeout. Shut down without
    # waiting so a slow call is truly abandoned in the background.
    ex = ThreadPoolExecutor(max_workers=1)
    try:
        fut = ex.submit(llm_complete_small, messages, 0)
        return fut.result(timeout=settings.rerank_timeout_s)
    finally:
        ex.shutdown(wait=False, cancel_futures=True)


def rerank_datasets(
    query: str,
    candidates: list[dict],
    top_k: int = 5,
) -> list[dict]:
    """Rerank candidate datasets using a single batched LLM call.

    Skips the LLM entirely when the top-2 candidates' existing scores differ by
    more than ``RERANK_DELTA`` (the result is already unambiguous). On any LLM
    error, parse failure, or timeout, returns the input ranked by existing score.

    Returns the top ``top_k`` candidates sorted by final score descending.
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

    if len(truncated) >= 2:
        gap = float(truncated[0].get("score", 0.0)) - float(truncated[1].get("score", 0.0))
        if gap > RERANK_DELTA:
            return truncated[:top_k]

    messages = _build_batch_prompt(query, truncated)
    try:
        raw = _call_llm_with_timeout(messages)
    except TimeoutError:
        log.warning("reranker: LLM call timed out after %.1fs", settings.rerank_timeout_s)
        return truncated[:top_k]
    except Exception as exc:
        log.warning("reranker: LLM call failed: %s", exc)
        return truncated[:top_k]

    parsed = _parse_scores(raw)
    if parsed is None:
        log.warning("reranker: could not parse LLM scores from response")
        return truncated[:top_k]

    max_base = max(float(c.get("score", 0.0)) for c in truncated) or 1.0
    for c in truncated:
        cid = c.get("id", "")
        base = float(c.get("score", 0.0))
        llm_score = parsed.get(cid, 0.0)
        c["score"] = 0.5 * (base / max_base) + 0.5 * llm_score

    truncated.sort(key=lambda c: c["score"], reverse=True)
    return truncated[:top_k]
