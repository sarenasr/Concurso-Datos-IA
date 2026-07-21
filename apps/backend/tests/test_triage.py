"""Tests for the LLM-based chitchat/meta triage fast-path.

Covers:
- ``triage_node`` — mocked ``llm_complete_small`` drives the classify+answer
  decision (chitchat vs. data), including the safe-default behavior on
  exceptions / unparsable responses.
- ``chitchat_answer_node`` — prefers the LLM-drafted answer, falls back to
  the canned ``CHITCHAT_ANSWER`` when empty.
- ``route_after_triage`` both branches.
- End-to-end: ``run_agent`` on a chitchat question must not touch the
  Socrata/SoQL tools at all (one small triage LLM call is expected).
"""

from __future__ import annotations

from unittest.mock import patch

from app.agents.graph import (
    CHITCHAT_ANSWER,
    chitchat_answer_node,
    route_after_triage,
    triage_node,
)

_PATCH_TARGET = "app.agents.graph.llm_complete_small"


# --- triage_node -------------------------------------------------------------


def test_triage_node_chitchat_uses_llm_answer() -> None:
    state = {"question": "hola"}
    with patch(
        _PATCH_TARGET,
        return_value='{"needs_data": false, "answer": "¡Hola! ¿En qué te ayudo?"}',
    ):
        result = triage_node(state)
    assert result["is_chitchat"] is True
    assert result["chitchat_answer_text"] == "¡Hola! ¿En qué te ayudo?"
    assert result["step"] == "triage"


def test_triage_node_data_question() -> None:
    state = {"question": "¿Cuántos contratos hay en Medellín?"}
    with patch(_PATCH_TARGET, return_value='{"needs_data": true, "answer": ""}'):
        result = triage_node(state)
    assert result["is_chitchat"] is False
    assert result["chitchat_answer_text"] == ""
    assert result["step"] == "triage"


def test_triage_node_llm_raises_defaults_to_data() -> None:
    state = {"question": "hola"}
    with patch(_PATCH_TARGET, side_effect=RuntimeError("boom")):
        result = triage_node(state)
    assert result["is_chitchat"] is False
    assert result["chitchat_answer_text"] == ""
    assert result["step"] == "triage"


def test_triage_node_llm_returns_garbage_defaults_to_data() -> None:
    state = {"question": "hola"}
    with patch(_PATCH_TARGET, return_value="not json at all"):
        result = triage_node(state)
    assert result["is_chitchat"] is False
    assert result["chitchat_answer_text"] == ""
    assert result["step"] == "triage"


def test_triage_node_llm_missing_needs_data_key_defaults_to_data() -> None:
    state = {"question": "hola"}
    with patch(_PATCH_TARGET, return_value='{"answer": "hola"}'):
        result = triage_node(state)
    assert result["is_chitchat"] is False
    assert result["chitchat_answer_text"] == ""
    assert result["step"] == "triage"


# --- route_after_triage --------------------------------------------------


def test_route_after_triage_chitchat() -> None:
    assert route_after_triage({"is_chitchat": True}) == "chitchat_answer"


def test_route_after_triage_data_question() -> None:
    assert route_after_triage({"is_chitchat": False}) == "search"


# --- chitchat_answer_node -----------------------------------------------


def test_chitchat_answer_node_uses_llm_answer_when_present() -> None:
    state: dict = {"chitchat_answer_text": "Respuesta generada por el LLM."}
    result = chitchat_answer_node(state)
    assert result["answer"] == "Respuesta generada por el LLM."
    assert result["sources"] == []
    assert result["chart"] is None
    assert result["step"] == "answer"


def test_chitchat_answer_node_falls_back_to_canned_when_empty() -> None:
    state: dict = {"chitchat_answer_text": ""}
    result = chitchat_answer_node(state)
    assert result["answer"] == CHITCHAT_ANSWER
    assert result["sources"] == []
    assert result["chart"] is None
    assert result["step"] == "answer"


def test_chitchat_answer_node_falls_back_to_canned_when_missing() -> None:
    state: dict = {}
    result = chitchat_answer_node(state)
    assert result["answer"] == CHITCHAT_ANSWER
    assert result["sources"] == []
    assert result["chart"] is None
    assert result["step"] == "answer"


# --- End-to-end: no data I/O on the chitchat fast path -----------------------


def test_run_agent_chitchat_fast_path_no_io() -> None:
    from app.agents import graph as graph_module

    graph_module._question_cache.clear()

    def _boom(*args, **kwargs):
        raise AssertionError("Socrata/SoQL tool should not be called on the chitchat fast path")

    with (
        patch.object(graph_module.T, "search_catalog", side_effect=_boom),
        patch.object(graph_module.T, "query_dataset", side_effect=_boom),
        patch(_PATCH_TARGET, return_value='{"needs_data": false, "answer": "Hola"}'),
    ):
        result = graph_module.run_agent("hola")

    assert result["answer"]
    assert result["sources"] == []
    assert result["chart"] is None
