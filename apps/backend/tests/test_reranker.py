"""Tests for the batched LLM reranker.

The reranker now asks a small LLM to score ALL candidate datasets in ONE call,
returning a JSON map ``{id: score}``. These tests mock ``llm_complete_small`` to
verify the blending logic, graceful degradation paths, and the delta-skip
optimisation.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from app.rag.reranker import rerank_datasets


def _candidate(id_: str, score: float, name: str = "", description: str = "") -> dict:
    return {
        "id": id_,
        "name": name or f"Dataset {id_}",
        "description": description or f"Description for {id_}",
        "score": score,
    }


def _patch_llm(side_effect=None, return_value=None):
    kwargs = (
        {"side_effect": side_effect} if side_effect is not None else {"return_value": return_value}
    )
    return patch("app.agents.llm.llm_complete_small", **kwargs)


def test_reranker_promotes_high_llm_score_to_top() -> None:
    """When LLM gives 0.9 to the second candidate and 0.1 to the rest, it wins."""
    candidates = [
        _candidate("a", 0.50),
        _candidate("b", 0.48),
        _candidate("c", 0.45),
    ]
    payload = '{"a": 0.1, "b": 0.9, "c": 0.1}'

    with _patch_llm(return_value=payload):
        result = rerank_datasets("cuantos contratos hay", candidates, top_k=3)

    assert result[0]["id"] == "b"
    assert len(result) == 3


def test_reranker_returns_input_unchanged_on_llm_exception() -> None:
    """On any LLM error the reranker degrades gracefully to input order."""
    candidates = [
        _candidate("x", 0.9),
        _candidate("y", 0.7),
        _candidate("z", 0.5),
    ]

    with _patch_llm(side_effect=RuntimeError("LLM unavailable")):
        result = rerank_datasets("test query", candidates, top_k=3)

    assert [r["id"] for r in result] == ["x", "y", "z"]
    assert result[0]["score"] == 0.9


def test_reranker_handles_unparseable_llm_output() -> None:
    """When the LLM returns garbage, the reranker returns input sorted by existing score."""
    candidates = [
        _candidate("a", 0.8),
        _candidate("b", 0.6),
    ]

    with _patch_llm(return_value="sorry, no scores today"):
        result = rerank_datasets("test query", candidates, top_k=2)

    assert [r["id"] for r in result] == ["a", "b"]
    assert result[0]["score"] == 0.8


def test_reranker_empty_candidates() -> None:
    """Empty input returns empty output without calling the LLM."""
    with _patch_llm(return_value="{}") as mock_llm:
        result = rerank_datasets("query", [], top_k=5)

    assert result == []
    mock_llm.assert_not_called()


def test_reranker_timeout_path() -> None:
    """On timeout the reranker returns input sorted by existing score."""
    candidates = [
        _candidate("a", 0.8),
        _candidate("b", 0.6),
    ]

    def _raise_timeout(*args, **kwargs):
        raise TimeoutError("took too long")

    with _patch_llm(side_effect=_raise_timeout):
        result = rerank_datasets("query", candidates, top_k=2)

    assert [r["id"] for r in result] == ["a", "b"]
    assert result[0]["score"] == 0.8


def test_reranker_delta_skip_avoids_llm_call() -> None:
    """When top-2 scores differ by more than RERANK_DELTA, LLM is not called."""
    candidates = [
        _candidate("clear_winner", 0.95),
        _candidate("far_behind", 0.30),
        _candidate("also_behind", 0.25),
    ]

    with _patch_llm(return_value='{"clear_winner": 0.0, "far_behind": 1.0}') as mock_llm:
        result = rerank_datasets("query", candidates, top_k=3)

    mock_llm.assert_not_called()
    assert result[0]["id"] == "clear_winner"
    assert result[0]["score"] == 0.95


def test_reranker_makes_at_most_one_llm_call() -> None:
    """Latency spec: the reranker must make AT MOST 1 LLM call regardless of N."""
    candidates = [_candidate(f"d{i}", 0.5 - i * 0.01) for i in range(10)]

    payload = {f"d{i}": 0.5 for i in range(10)}

    with _patch_llm(return_value=json.dumps(payload)) as mock_llm:
        rerank_datasets("query", candidates, top_k=5)

    assert mock_llm.call_count <= 1


def test_reranker_missing_id_defaults_to_zero_not_dropped() -> None:
    """An id missing from the parsed JSON gets llm_score=0.0, it is NOT dropped."""
    candidates = [
        _candidate("present", 0.5),
        _candidate("missing", 0.5),
    ]
    with _patch_llm(return_value='{"present": 0.9}'):
        result = rerank_datasets("query", candidates, top_k=2)

    ids = {r["id"] for r in result}
    assert ids == {"present", "missing"}
    present = next(r for r in result if r["id"] == "present")
    missing = next(r for r in result if r["id"] == "missing")
    assert present["score"] > missing["score"]


def test_reranker_strips_markdown_fences() -> None:
    """LLM responses wrapped in ```json ... ``` are parsed correctly."""
    candidates = [
        _candidate("a", 0.5),
        _candidate("b", 0.5),
    ]
    payload = '```json\n{"a": 0.9, "b": 0.1}\n```'
    with _patch_llm(return_value=payload):
        result = rerank_datasets("query", candidates, top_k=2)

    assert result[0]["id"] == "a"
