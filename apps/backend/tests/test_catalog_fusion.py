"""Tests for the hybrid retrieval fusion pipeline in ``app.rag.catalog``.

Covers:
- Reciprocal Rank Fusion scoring formula
- Priority boost as additive (not multiplicative)
- Query tokenization: stopword removal, synonym expansion
- Popularity prior as additive tie-breaker
- Keyword search delegation to per-token ilike queries
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.rag.catalog import (
    _RRF_K,
    _PRIORITY_BOOST_ADD,
    _PRIORITY_FALLBACK_SCORE,
    _apply_popularity_prior,
    _apply_priority_boost,
    _fuse_results,
    _keyword_search,
    _tokenize_query,
)


def _vec(id_: str, score: float = 0.0, **extra) -> dict:
    row = {"id": id_, "name": f"Dataset {id_}", "score": score, "page_views_last_month": 0}
    row.update(extra)
    return row


def _txt(id_: str, text_score: float = 0.0, **extra) -> dict:
    row = {
        "id": id_,
        "name": f"Dataset {id_}",
        "text_score": text_score,
        "page_views_last_month": 0,
    }
    row.update(extra)
    return row


def test_rrf_both_legs() -> None:
    """Item in both legs gets sum of 1/(K+rank) from each leg."""
    vector_rows = [_vec("a", 0.9), _vec("b", 0.8), _vec("c", 0.7)]
    text_rows = [_txt("b", 0.7), _txt("c", 0.5), _txt("d", 0.3)]

    fused = _fuse_results(vector_rows, text_rows)
    by_id = {r["id"]: r["score"] for r in fused}

    assert "a" in by_id
    assert "b" in by_id
    assert "c" in by_id
    assert "d" in by_id

    assert abs(by_id["a"] - 1.0 / (_RRF_K + 0)) < 1e-9
    assert abs(by_id["b"] - (1.0 / (_RRF_K + 1) + 1.0 / (_RRF_K + 0))) < 1e-9
    assert abs(by_id["c"] - (1.0 / (_RRF_K + 2) + 1.0 / (_RRF_K + 1))) < 1e-9
    assert abs(by_id["d"] - 1.0 / (_RRF_K + 2)) < 1e-9


def test_rrf_item_only_in_vector_leg() -> None:
    """Item absent from text leg gets only the vector-leg contribution."""
    vector_rows = [_vec("x", 0.95)]
    text_rows: list[dict] = []

    fused = _fuse_results(vector_rows, text_rows)
    assert len(fused) == 1
    assert abs(fused[0]["score"] - 1.0 / (_RRF_K + 0)) < 1e-9


def test_rrf_item_only_in_text_leg() -> None:
    """Item absent from vector leg gets only the text-leg contribution."""
    vector_rows: list[dict] = []
    text_rows = [_txt("y", 0.6)]

    fused = _fuse_results(vector_rows, text_rows)
    assert len(fused) == 1
    assert abs(fused[0]["score"] - 1.0 / (_RRF_K + 0)) < 1e-9


def test_rrf_empty_inputs() -> None:
    """Both legs empty returns empty."""
    assert _fuse_results([], []) == []


def test_rrf_sort_order() -> None:
    """Fused results are sorted by RRF score descending."""
    vector_rows = [_vec("a", 0.9), _vec("b", 0.8)]
    text_rows = [_txt("a", 0.7), _txt("c", 0.5)]

    fused = _fuse_results(vector_rows, text_rows)
    scores = [r["score"] for r in fused]
    assert scores == sorted(scores, reverse=True)


def test_priority_boost_adds_not_multiplies() -> None:
    """Priority boost adds _PRIORITY_BOOST_ADD (0.02) instead of multiplying."""
    rows = [{"id": "priority-1", "score": 0.01}, {"id": "other", "score": 0.01}]

    with patch("app.rag.catalog._priority_ids", return_value={"priority-1"}):
        result = _apply_priority_boost(rows)

    by_id = {r["id"]: r["score"] for r in result}
    assert abs(by_id["priority-1"] - (0.01 + _PRIORITY_BOOST_ADD)) < 1e-9
    assert abs(by_id["other"] - 0.01) < 1e-9


def test_priority_boost_noop_when_no_priority_ids() -> None:
    """No priority IDs means no score changes."""
    rows = [{"id": "a", "score": 0.015}]

    with patch("app.rag.catalog._priority_ids", return_value=set()):
        result = _apply_priority_boost(rows)

    assert abs(result[0]["score"] - 0.015) < 1e-9


def test_popularity_prior_is_additive() -> None:
    """Popularity prior adds a small nudge, not a multiplicative factor."""
    rows = [
        {"id": "a", "score": 0.01, "page_views_last_month": 1000},
        {"id": "b", "score": 0.01, "page_views_last_month": 0},
    ]

    result = _apply_popularity_prior(rows)
    by_id = {r["id"]: r["score"] for r in result}

    import math

    expected_a = 0.01 + math.log1p(1000) / 1000.0
    expected_b = 0.01 + math.log1p(0) / 1000.0
    assert abs(by_id["a"] - expected_a) < 1e-9
    assert abs(by_id["b"] - expected_b) < 1e-9
    assert by_id["a"] > by_id["b"]


def test_tokenize_query_basic() -> None:
    """Tokenizes a Spanish question, keeping content words."""
    tokens = _tokenize_query("¿Cuántos contratos públicos firmó Medellín en 2025?")
    assert "contratos" in tokens
    assert "públicos" in tokens
    assert "firmó" in tokens
    assert "medellín" in tokens


def test_tokenize_query_stopword_removal() -> None:
    """Spanish stopwords are removed from the token list."""
    tokens = _tokenize_query("los contratos de las empresas para el país")
    assert "los" not in tokens
    assert "las" not in tokens
    assert "para" not in tokens
    assert "contratos" in tokens
    assert "empresas" in tokens
    assert "país" in tokens


def test_tokenize_query_short_words_dropped() -> None:
    """Words shorter than 3 characters are dropped."""
    tokens = _tokenize_query("de en la ciudad")
    assert "de" not in tokens
    assert "en" not in tokens
    assert "la" not in tokens
    assert "ciudad" in tokens


def test_tokenize_query_synonym_expansion() -> None:
    """Synonym expansion adds 'secop' when query contains 'contratos'."""
    tokens = _tokenize_query("contratos públicos")
    assert "contratos" in tokens
    assert "secop" in tokens
    assert "contratacion" in tokens


def test_tokenize_query_deduplication() -> None:
    """No duplicate tokens even when synonyms overlap with original words."""
    tokens = _tokenize_query("contratos contrato")
    assert tokens.count("contratos") == 1
    assert tokens.count("contrato") == 1


def test_tokenize_query_empty() -> None:
    """Empty or stopword-only queries return an empty token list."""
    assert _tokenize_query("") == []
    assert _tokenize_query("de en la los las") == []


def test_keyword_search_uses_rpc_when_available() -> None:
    """_keyword_search calls the match_catalog_text RPC and ranks its rows."""
    sb = MagicMock()
    rpc_data = [
        {"id": "a", "name": "A", "page_views_last_month": 0},
        {"id": "b", "name": "B", "page_views_last_month": 0},
    ]
    sb.rpc.return_value.execute.return_value.data = rpc_data

    result = _keyword_search(sb, "contratos públicos", k=10)

    sb.rpc.assert_called_once_with("match_catalog_text", {"q": "contratos públicos", "k": 10})
    sb.table.assert_not_called()
    assert [r["id"] for r in result] == ["a", "b"]
    assert result[0]["text_score"] > result[1]["text_score"]


def test_keyword_search_falls_back_to_ilike_on_rpc_failure() -> None:
    """When the RPC raises (e.g. migration not applied), fall back to ilike
    over name OR description via the PostgREST ``.or_`` filter."""
    sb = MagicMock()
    sb.rpc.return_value.execute.side_effect = Exception("function does not exist")
    chain = sb.table.return_value.select.return_value.eq.return_value
    chain.or_.return_value.limit.return_value.execute.return_value.data = []

    _keyword_search(sb, "contratos públicos", k=10)

    or_calls = chain.or_.call_args_list
    assert len(or_calls) <= 5
    for call in or_calls:
        filter_str = call.args[0]
        assert "name.ilike." in filter_str
        assert "description.ilike." in filter_str


def test_keyword_search_best_rank_for_multi_token_match() -> None:
    """When a dataset matches multiple tokens, its text_score uses the best rank
    (ilike fallback path, since the RPC is unavailable)."""
    sb = MagicMock()
    sb.rpc.return_value.execute.side_effect = Exception("function does not exist")
    chain = sb.table.return_value.select.return_value.eq.return_value

    first_call_data = [
        {"id": "x", "name": "X", "page_views_last_month": 0},
        {"id": "y", "name": "Y", "page_views_last_month": 0},
    ]
    second_call_data = [
        {"id": "x", "name": "X", "page_views_last_month": 0},
    ]

    execute_mock = chain.or_.return_value.limit.return_value.execute
    execute_mock.side_effect = [
        MagicMock(data=first_call_data),
        MagicMock(data=second_call_data),
    ]

    result = _keyword_search(sb, "contratos públicos", k=10)

    x_entry = next(r for r in result if r["id"] == "x")
    y_entry = next(r for r in result if r["id"] == "y")
    assert x_entry["text_score"] > y_entry["text_score"]


def test_keyword_search_empty_query() -> None:
    """Empty query returns empty results without hitting Supabase."""
    sb = MagicMock()
    result = _keyword_search(sb, "", k=10)
    assert result == []
    sb.table.assert_not_called()
    sb.rpc.assert_not_called()


def test_priority_fallback_injects_with_rrf_scale_score() -> None:
    """Injected priority fallback uses _PRIORITY_FALLBACK_SCORE, not old 1.3."""
    from app.rag.catalog import _priority_fallback

    rows = [{"id": "other", "name": "Other", "score": 0.005}]
    fake_match = {"id": "prio-1", "name": "Priority", "sector": "salud"}
    vector_rows = [{"id": "prio-1", "score": 0.80}]

    with (
        patch("app.rag.catalog._priority_keyword_match", return_value=[fake_match]),
    ):
        result = _priority_fallback(rows, "query", k=5, vector_rows=vector_rows)

    assert result[0]["id"] == "prio-1"
    assert result[0]["score"] == _PRIORITY_FALLBACK_SCORE
    assert result[0]["reason"] == "priority_keyword_match"


def test_priority_fallback_requires_vector_support_to_force_rank() -> None:
    """Without a genuine vector-similarity hit, a keyword-only match is not
    force-ranked to #1 even though genuine competition is weak (top score
    0.005 < _GENUINE_CONFIDENT_SCORE) — it is still surfaced, but capped
    below whatever genuine competition exists rather than winning #1."""
    from app.rag.catalog import _priority_fallback

    rows = [{"id": "other", "name": "Other", "score": 0.005}]
    fake_match = {"id": "prio-1", "name": "Priority", "sector": "salud"}
    # prio-1 has weak vector support (below _PRIORITY_MIN_VECTOR_SIM = 0.65)
    vector_rows = [{"id": "prio-1", "score": 0.40}]

    with patch("app.rag.catalog._priority_keyword_match", return_value=[fake_match]):
        result = _priority_fallback(rows, "query", k=5, vector_rows=vector_rows)

    assert result[0]["id"] == "other"
    prio_row = next(r for r in result if r["id"] == "prio-1")
    assert prio_row["score"] < result[0]["score"]


def test_priority_fallback_absent_from_vector_rows_treated_as_no_support() -> None:
    """A priority match missing entirely from vector_rows is treated as
    having no vector support (same as a below-floor cosine score) — capped
    below genuine competition instead of force-ranked to #1."""
    from app.rag.catalog import _priority_fallback

    rows = [{"id": "other", "name": "Other", "score": 0.005}]
    fake_match = {"id": "prio-1", "name": "Priority", "sector": "salud"}
    vector_rows = [{"id": "unrelated", "score": 0.90}]

    with patch("app.rag.catalog._priority_keyword_match", return_value=[fake_match]):
        result = _priority_fallback(rows, "query", k=5, vector_rows=vector_rows)

    assert result[0]["id"] == "other"


def test_priority_fallback_no_vector_rows_defaults_to_no_support() -> None:
    """Calling without vector_rows at all (default None) never force-ranks."""
    from app.rag.catalog import _priority_fallback

    rows = [{"id": "other", "name": "Other", "score": 0.005}]
    fake_match = {"id": "prio-1", "name": "Priority", "sector": "salud"}

    with patch("app.rag.catalog._priority_keyword_match", return_value=[fake_match]):
        result = _priority_fallback(rows, "query", k=5)

    assert result[0]["id"] == "other"


def test_priority_fallback_no_vector_support_and_no_genuine_competition_omits() -> None:
    """No vector support AND no genuine competition (empty rows) at all: there
    is nothing safe to cap against, so the priority match is not added."""
    from app.rag.catalog import _priority_fallback

    rows: list[dict] = []
    fake_match = {"id": "prio-1", "name": "Priority", "sector": "salud"}
    vector_rows = [{"id": "prio-1", "score": 0.40}]

    with patch("app.rag.catalog._priority_keyword_match", return_value=[fake_match]):
        result = _priority_fallback(rows, "query", k=5, vector_rows=vector_rows)

    assert result == []


def test_priority_fallback_vector_support_but_confident_genuine_caps_below() -> None:
    """Vector support is present, but a confident genuine leader still blocks
    force-ranking to #1 — the priority match is surfaced capped below it."""
    from app.rag.catalog import _priority_fallback, _GENUINE_CONFIDENT_SCORE

    rows = [{"id": "other", "name": "Other", "score": _GENUINE_CONFIDENT_SCORE + 0.01}]
    fake_match = {"id": "prio-1", "name": "Priority", "sector": "salud"}
    vector_rows = [{"id": "prio-1", "score": 0.90}]

    with patch("app.rag.catalog._priority_keyword_match", return_value=[fake_match]):
        result = _priority_fallback(rows, "query", k=5, vector_rows=vector_rows)

    prio_row = next(r for r in result if r["id"] == "prio-1")
    other_row = next(r for r in result if r["id"] == "other")
    assert prio_row["score"] < other_row["score"]
