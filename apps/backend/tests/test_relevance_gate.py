"""Tests for ``relevance_gate_node`` in ``app.agents.graph``.

The score-based selection in ``search_node`` cannot tell a topically-adjacent
but wrong dataset apart from a correct one (e.g. a COVID-19 dataset scoring
above the confidence floor for a *dengue* question). ``relevance_gate_node``
adds a small-LLM subject-match check: on a confident "not relevant" it clears
``dataset_id`` so the downstream honest "no relevant dataset" fallback fires
instead of reporting a cross-topic number.

The gate must be conservative — any LLM/parse failure, or genuine doubt, keeps
the dataset in place so a valid data question is never wrongly refused.

``llm_complete_small`` is patched (as ``app.agents.graph.llm_complete_small``,
matching how ``graph.py`` imports it) so these tests make no network/LLM calls.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from app.agents.graph import relevance_gate_node

_LLM_TARGET = "app.agents.graph.llm_complete_small"

_COVID_SCHEMA = {
    "name": "Casos positivos de COVID-19 en Colombia",
    "columns": [
        {"field_name": "fecha_de_diagnostico", "datatype": "text", "name": "Fecha de diagnóstico"},
        {"field_name": "edad", "datatype": "number", "name": "Edad"},
    ],
}


def _base_state(question: str, dataset_id: str | None, schema: dict | None) -> dict:
    return {
        "question": question,
        "dataset_id": dataset_id,
        "schema": schema,
    }


def test_off_topic_dataset_is_rejected() -> None:
    """A dengue question routed to the COVID dataset clears dataset_id."""
    state = _base_state("¿Cuántos casos de dengue se reportaron en 2023?", "gt2j-8ykr", _COVID_SCHEMA)
    resp = json.dumps({"relevant": False, "reason": "El dataset es de COVID-19, no de dengue."})
    with patch(_LLM_TARGET, return_value=resp) as mock_llm:
        result = relevance_gate_node(state)

    assert result["dataset_id"] is None
    mock_llm.assert_called_once()


def test_on_topic_dataset_is_kept() -> None:
    """A COVID question against the COVID dataset keeps dataset_id."""
    state = _base_state("¿Cuántos casos de COVID hubo en 2021?", "gt2j-8ykr", _COVID_SCHEMA)
    resp = json.dumps({"relevant": True, "reason": "El dataset es de COVID-19."})
    with patch(_LLM_TARGET, return_value=resp):
        result = relevance_gate_node(state)

    assert result["dataset_id"] == "gt2j-8ykr"


def test_llm_failure_keeps_dataset() -> None:
    """A raised LLM exception must not refuse — dataset stays in place."""
    state = _base_state("¿Cuántos casos de COVID hubo?", "gt2j-8ykr", _COVID_SCHEMA)
    with patch(_LLM_TARGET, side_effect=RuntimeError("timeout")):
        result = relevance_gate_node(state)

    assert result["dataset_id"] == "gt2j-8ykr"


def test_unparsable_response_keeps_dataset() -> None:
    """A non-JSON response is treated as doubt — dataset stays in place."""
    state = _base_state("¿Cuántos casos de COVID hubo?", "gt2j-8ykr", _COVID_SCHEMA)
    with patch(_LLM_TARGET, return_value="no lo sé"):
        result = relevance_gate_node(state)

    assert result["dataset_id"] == "gt2j-8ykr"


def test_no_dataset_or_schema_is_noop() -> None:
    """With no dataset chosen the gate must not call the LLM at all."""
    state = _base_state("cualquier cosa", None, None)
    with patch(_LLM_TARGET) as mock_llm:
        result = relevance_gate_node(state)

    assert result["dataset_id"] is None
    mock_llm.assert_not_called()
