"""Tests for the OpenRouter hosted cross-encoder reranker.

The reranker sends the top candidates to OpenRouter's hosted rerank endpoint
(``POST https://openrouter.ai/api/v1/rerank``) in ONE HTTP call. These tests
mock ``httpx.post`` to verify the reordering logic, graceful degradation
paths (missing key / HTTP error, timeout, malformed response), empty input,
and truncation behaviour. No real network calls are made.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from app.rag.reranker import rerank_datasets


def _candidate(id_: str, score: float, name: str = "", description: str = "") -> dict:
    return {
        "id": id_,
        "name": name or f"Dataset {id_}",
        "description": description or f"Description for {id_}",
        "domain_category": "General",
        "score": score,
    }


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


def test_reranker_promotes_high_relevance_to_top() -> None:
    """When the API ranks the second candidate first, it wins."""
    candidates = [
        _candidate("a", 0.50),
        _candidate("b", 0.48),
        _candidate("c", 0.45),
    ]
    api_response = {
        "results": [
            {"index": 0, "relevance_score": 0.10},
            {"index": 1, "relevance_score": 0.95},
            {"index": 2, "relevance_score": 0.05},
        ]
    }

    with (
        patch("app.rag.reranker.settings.openrouter_api_key", "test-key"),
        patch(
            "app.rag.reranker.httpx.post", return_value=_mock_response(api_response)
        ) as mock_post,
    ):
        result = rerank_datasets("cuantos contratos hay", candidates, top_k=3)

    assert result[0]["id"] == "b"
    assert result[0]["rerank_score"] == 0.95
    assert len(result) == 3
    mock_post.assert_called_once()


def test_reranker_returns_input_unchanged_when_no_api_key() -> None:
    """With no OpenRouter key, the reranker short-circuits without an HTTP call."""
    candidates = [
        _candidate("x", 0.9),
        _candidate("y", 0.7),
        _candidate("z", 0.5),
    ]

    with (
        patch("app.rag.reranker.settings.openrouter_api_key", ""),
        patch("app.rag.reranker.httpx.post") as mock_post,
    ):
        result = rerank_datasets("test query", candidates, top_k=3)

    assert [r["id"] for r in result] == ["x", "y", "z"]
    assert result[0]["score"] == 0.9
    mock_post.assert_not_called()


def test_reranker_returns_input_unchanged_on_http_error() -> None:
    """On an HTTP error status, the reranker no-ops and returns input order."""
    candidates = [
        _candidate("x", 0.9),
        _candidate("y", 0.7),
        _candidate("z", 0.5),
    ]

    with (
        patch("app.rag.reranker.settings.openrouter_api_key", "test-key"),
        patch(
            "app.rag.reranker.httpx.post",
            return_value=_mock_response({}, status_code=500),
        ),
    ):
        result = rerank_datasets("test query", candidates, top_k=3)

    assert [r["id"] for r in result] == ["x", "y", "z"]
    assert result[0]["score"] == 0.9


def test_reranker_returns_input_unchanged_on_timeout() -> None:
    """On timeout the reranker returns input sorted by existing score."""
    candidates = [
        _candidate("a", 0.8),
        _candidate("b", 0.6),
    ]

    with (
        patch("app.rag.reranker.settings.openrouter_api_key", "test-key"),
        patch(
            "app.rag.reranker.httpx.post",
            side_effect=httpx.TimeoutException("timed out"),
        ),
    ):
        result = rerank_datasets("query", candidates, top_k=2)

    assert [r["id"] for r in result] == ["a", "b"]
    assert result[0]["score"] == 0.8


def test_reranker_handles_malformed_results() -> None:
    """When the response has no usable results, falls back to input order."""
    candidates = [
        _candidate("a", 0.8),
        _candidate("b", 0.6),
    ]

    with (
        patch("app.rag.reranker.settings.openrouter_api_key", "test-key"),
        patch(
            "app.rag.reranker.httpx.post",
            return_value=_mock_response({"not_results": []}),
        ),
    ):
        result = rerank_datasets("test query", candidates, top_k=2)

    assert [r["id"] for r in result] == ["a", "b"]
    assert result[0]["score"] == 0.8


def test_reranker_handles_empty_results_array() -> None:
    """An empty results array falls back to input order."""
    candidates = [
        _candidate("a", 0.8),
        _candidate("b", 0.6),
    ]

    with (
        patch("app.rag.reranker.settings.openrouter_api_key", "test-key"),
        patch(
            "app.rag.reranker.httpx.post",
            return_value=_mock_response({"results": []}),
        ),
    ):
        result = rerank_datasets("test query", candidates, top_k=2)

    assert [r["id"] for r in result] == ["a", "b"]
    assert result[0]["score"] == 0.8


def test_reranker_empty_candidates() -> None:
    """Empty input returns empty output without calling the API."""
    with patch("app.rag.reranker.httpx.post") as mock_post:
        result = rerank_datasets("query", [], top_k=5)

    assert result == []
    mock_post.assert_not_called()


def test_reranker_truncates_to_max_candidates() -> None:
    """Only the top rerank_max_candidates (by fused score) are sent to the API."""
    candidates = [_candidate(f"d{i}", 1.0 - i * 0.01) for i in range(30)]

    def _fake_post(url, headers=None, json=None, timeout=None):
        assert len(json["documents"]) == 5
        return _mock_response({"results": [{"index": 0, "relevance_score": 0.5}]})

    with (
        patch("app.rag.reranker.settings.openrouter_api_key", "test-key"),
        patch("app.rag.reranker.settings.rerank_max_candidates", 5),
        patch("app.rag.reranker.httpx.post", side_effect=_fake_post),
    ):
        rerank_datasets("query", candidates, top_k=1)


def test_reranker_respects_top_k() -> None:
    """Returns at most top_k results even if the API scores more."""
    candidates = [_candidate(f"d{i}", 1.0 - i * 0.1) for i in range(5)]
    api_response = {"results": [{"index": i, "relevance_score": 1.0 - i * 0.1} for i in range(5)]}

    with (
        patch("app.rag.reranker.settings.openrouter_api_key", "test-key"),
        patch("app.rag.reranker.httpx.post", return_value=_mock_response(api_response)),
    ):
        result = rerank_datasets("query", candidates, top_k=2)

    assert len(result) == 2
