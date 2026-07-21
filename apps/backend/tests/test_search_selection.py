"""Tests for dataset selection in ``search_node``.

Covers the two bugs fixed around the priority-override / low-confidence
thresholds:

- Bug 1: the priority-keyword override used to fire on ``chosen_score < 0.5``,
  which is ALWAYS true because fused RRF scores top out around ~0.045-0.05.
  This let a keyword-matched priority dataset hijack a genuinely relevant top
  vector hit. Fixed with ``_PRIORITY_OVERRIDE_MAX_SCORE`` (0.03).
- Bug 2: when even the best candidate is a weak match, the agent used to
  commit to it anyway and produce a misleading answer. Fixed with
  ``_MIN_CONFIDENT_SCORE`` (0.02): below that floor (and with no priority
  override, and not a join question) ``dataset_id`` is left ``None`` so
  ``answer_node`` takes its existing honest "no relevant dataset" fallback.

``search_catalog`` is mocked (patched as ``app.agents.graph.T.search_catalog``,
matching how ``graph.py`` imports ``app.agents.tools`` as ``T``) so these
tests make no network/LLM calls.
"""

from __future__ import annotations

from unittest.mock import patch

from app.agents.graph import search_node

_SEARCH_TARGET = "app.agents.graph.T.search_catalog"
_OVERRIDE_TARGET = "app.agents.graph._find_priority_keyword_override"


def _base_state(question: str) -> dict:
    return {
        "question": question,
        "datasets": [],
        "dataset_id": None,
        "is_join_question": False,
        "join_partner_id": None,
    }


def test_high_score_top_result_is_selected_and_not_overridden() -> None:
    results = [
        {"id": "rjh5-tyrd", "name": "Déficit Habitacional en Bogotá", "score": 0.045},
        {"id": "tq4m-hmg2", "name": "Población BDUA afiliados", "score": 0.02},
    ]
    state = _base_state("¿Cuál es el déficit de viviendas en Bogotá?")
    with (
        patch(_SEARCH_TARGET, return_value=results),
        patch(_OVERRIDE_TARGET, return_value=None) as mock_override,
    ):
        result = search_node(state)

    assert result["dataset_id"] == "rjh5-tyrd"
    assert result["datasets"] == results
    # Score is above _PRIORITY_OVERRIDE_MAX_SCORE, so the override lookup must
    # never even be attempted.
    mock_override.assert_not_called()


def test_very_low_score_top_result_leaves_dataset_id_none() -> None:
    results = [
        {"id": "qrmy-eswf", "name": "Número de Empleados Empresas Registradas", "score": 0.015},
    ]
    state = _base_state(
        "Verificá este tweet: 'El gobierno contrató más en 2025 que en 2024'"
    )
    with (
        patch(_SEARCH_TARGET, return_value=results),
        patch(_OVERRIDE_TARGET, return_value=None),
    ):
        result = search_node(state)

    assert result["dataset_id"] is None
    # The candidate list must still be populated so answer_node can render
    # "maybe you mean X" suggestions from state["datasets"].
    assert result["datasets"] == results
