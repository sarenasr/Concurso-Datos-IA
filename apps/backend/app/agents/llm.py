"""LLM completion helpers extracted from ``app.agents.graph`` for reuse.

Both the main agent graph and the RAG reranker share the same LiteLLM-backed
completion pipeline.  Keeping these in a dedicated module avoids a circular
import between ``app.agents.graph`` (which imports from ``app.rag``) and
``app.rag.reranker`` (which needs the LLM helper).
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings

log = logging.getLogger("manglar.llm")


def _completion_kwargs(model_name: str = "") -> dict[str, Any]:
    """Build (model, kwargs) for a litellm.completion call from settings.

    Routes through the OpenAI-compatible LITELLM_API_BASE (OpenCode Go) when
    present, else uses OpenRouter if OPENROUTER_API_KEY is set, else uses the
    model as-is with the default LiteLLM routing.
    """
    model = model_name or settings.litellm_model
    kwargs: dict[str, Any] = {"timeout": settings.llm_timeout_s}
    if settings.litellm_api_base:
        if not model.startswith("openai/"):
            model = f"openai/{model}"
        kwargs["api_base"] = settings.litellm_api_base
        key = settings.litellm_api_key_resolved
        if key:
            kwargs["api_key"] = key
    elif settings.openrouter_api_key:
        if not model.startswith("openrouter/"):
            model = f"openrouter/{model}"
        kwargs["api_key"] = settings.openrouter_api_key
    else:
        key = settings.litellm_api_key_resolved
        if key:
            kwargs["api_key"] = key
    return {"model": model, **kwargs}


def _litellm_completion(model: str, **kwargs) -> Any:
    """Call litellm.completion with bounded retry/backoff for transient failures.

    Attempts and per-call timeout come from settings so interactive latency stays
    bounded against slow/flaky providers.
    """
    import time

    import litellm

    litellm.suppress_debug_info = True
    litellm.set_verbose = False

    attempts = max(1, settings.llm_max_attempts)
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            return litellm.completion(model=model, **kwargs)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if i == attempts - 1:
                break
            time.sleep(min(0.5 * (2**i), settings.llm_backoff_max_s))
    raise last_exc  # type: ignore[misc]


def _openrouter_kwargs(model_name: str) -> dict[str, Any]:
    """Build LiteLLM kwargs for a direct OpenRouter call."""
    if not settings.openrouter_api_key:
        raise RuntimeError("No OpenRouter API key configured")
    model = f"openrouter/{model_name}" if not model_name.startswith("openrouter/") else model_name
    return {
        "model": model,
        "api_key": settings.openrouter_api_key,
        "api_base": "https://openrouter.ai/api/v1",
        "timeout": settings.llm_timeout_s,
    }


def _call_with_fallback(model_setting: str, messages: list[dict], temperature: float) -> str:
    """Try OpenRouter first, fall back to OpenCode Go on failure."""
    if settings.openrouter_api_key:
        fw = _openrouter_kwargs(model_setting)
        model_fb = fw.pop("model")
        try:
            resp = _litellm_completion(
                model=model_fb, messages=messages, temperature=temperature, **fw
            )
            return resp["choices"][0]["message"]["content"]  # type: ignore[index]
        except Exception as exc:
            log.warning("OpenRouter failed: %s — falling back to OpenCode Go", exc)
    kw = _completion_kwargs(model_setting)
    model = kw.pop("model")
    resp = _litellm_completion(model=model, messages=messages, temperature=temperature, **kw)
    return resp["choices"][0]["message"]["content"]  # type: ignore[index]


def llm_complete(messages: list[dict], temperature: float = 0) -> str:
    """Provider-agnostic completion with OpenRouter fallback.

    Returns the assistant message content as a string.
    """
    return _call_with_fallback(settings.litellm_model, messages, temperature)


def llm_complete_small(messages: list[dict], temperature: float = 0) -> str:
    """Lightweight completion with OpenRouter fallback.

    Uses the small/fast model for structured tasks like SoQL generation.
    Falls back to :func:`llm_complete` when no small model is configured.
    """
    if not settings.litellm_small_model:
        return llm_complete(messages, temperature=temperature)
    return _call_with_fallback(settings.litellm_small_model, messages, temperature)
