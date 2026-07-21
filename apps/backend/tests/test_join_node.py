"""Tests for the cross-dataset join flow (Hero #3).

Covers:
- ``_detect_join_question`` — keyword regex for Spanish join cues.
- ``_resolve_secop_pair`` — SECOP-Sancionados + SECOP-II-Contratos lookup.
- ``route_after_search`` — routing decision after search.
- ``join_query_node`` — end-to-end merge with mocked LLM + mocked tools.
"""

from __future__ import annotations

from unittest.mock import patch

from app.agents.graph import (
    _detect_join_question,
    _resolve_secop_pair,
    join_query_node,
    route_after_search,
)


# --- _detect_join_question -------------------------------------------------


def test_detect_join_question_ademas() -> None:
    assert (
        _detect_join_question(
            "empresas sancionadas que además tienen contratos en salud en Antioquia"
        )
        is True
    )


def test_detect_join_question_sancionadas_contratos() -> None:
    assert _detect_join_question("sancionadas con contratos en salud") is True


def test_detect_join_question_contratos_sancionados() -> None:
    assert _detect_join_question("contratos de empresas sancionadas") is True


def test_detect_join_question_cuentan_con() -> None:
    assert _detect_join_question("empresas que cuentan con sanciones") is True


def test_detect_join_question_negative_simple() -> None:
    assert _detect_join_question("¿Cuántos medicamentos hay?") is False


def test_detect_join_question_negative_covid() -> None:
    assert _detect_join_question("casos de covid en Bogotá") is False


def test_detect_join_question_negative_trm() -> None:
    assert _detect_join_question("TRM promedio del último mes") is False


# --- _resolve_secop_pair ---------------------------------------------------


def test_resolve_secop_pair_hero3_question() -> None:
    pair = _resolve_secop_pair(
        "empresas sancionadas que además tienen contratos en salud en Antioquia"
    )
    assert pair == ("4n4q-k399", "jbjy-vk9h")


def test_resolve_secop_pair_reverse_order() -> None:
    pair = _resolve_secop_pair("contratos en salud de empresas sancionadas en SECOP")
    assert pair == ("4n4q-k399", "jbjy-vk9h")


def test_resolve_secop_pair_non_join_question() -> None:
    assert _resolve_secop_pair("¿Cuántos medicamentos hay?") is None


def test_resolve_secop_pair_unrelated_join() -> None:
    assert _resolve_secop_pair("empresas que además exportan") is None


# --- route_after_search ----------------------------------------------------


def test_route_after_search_join_question() -> None:
    state = {
        "is_join_question": True,
        "join_partner_id": "jbjy-vk9h",
    }
    assert route_after_search(state) == "join_generate"


def test_route_after_search_normal_question() -> None:
    state = {
        "is_join_question": False,
        "join_partner_id": None,
    }
    assert route_after_search(state) == "schema"


def test_route_after_search_join_without_partner() -> None:
    state = {
        "is_join_question": True,
        "join_partner_id": None,
    }
    assert route_after_search(state) == "schema"


# --- join_query_node -------------------------------------------------------


def _build_state_for_join() -> dict:
    return {
        "question": "empresas sancionadas que además tienen contratos en salud",
        "datasets": [],
        "dataset_id": "4n4q-k399",
        "schema": None,
        "soql": None,
        "query_result": None,
        "retry_count": 0,
        "answer": None,
        "chart": None,
        "sources": [],
        "step": "search",
        "is_join_question": True,
        "join_partner_id": "jbjy-vk9h",
        "join_key_primary": None,
        "join_key_partner": None,
        "partner_schema": None,
        "partner_soql": None,
        "partner_query_result": None,
    }


def test_join_query_node_merges_on_shared_key() -> None:
    """Merged rows are partner rows whose join key appears in the primary set."""
    import json

    primary_schema = {
        "id": "4n4q-k399",
        "name": "SECOP Sancionados",
        "permalink": "https://datos.gov.co/d/4n4q-k399",
        "columns": [
            {"name": "Documento", "field_name": "documento_contratista", "datatype": "text"},
            {"name": "Valor Sanción", "field_name": "valor_sancion", "datatype": "number"},
        ],
    }
    partner_schema = {
        "id": "jbjy-vk9h",
        "name": "SECOP II Contratos",
        "permalink": "https://datos.gov.co/d/jbjy-vk9h",
        "columns": [
            {
                "name": "Documento Proveedor",
                "field_name": "documento_proveedor",
                "datatype": "text",
            },
            {"name": "Nombre", "field_name": "nombre_proveedor", "datatype": "text"},
            {"name": "Valor Contrato", "field_name": "valor_contrato", "datatype": "number"},
            {"name": "Sector", "field_name": "sector", "datatype": "text"},
        ],
    }

    primary_rows = [
        {"documento_contratista": "900.123.456-7", "valor_sancion": 1000},
        {"documento_contratista": "800.999.000-1", "valor_sancion": 2000},
    ]
    partner_rows = [
        {
            "documento_proveedor": "9001234567",
            "nombre_proveedor": "ACME S.A.S",
            "valor_contrato": 50000,
            "sector": "Salud",
        },
        {
            "documento_proveedor": "7005551112",
            "nombre_proveedor": "Otro S.A.",
            "valor_contrato": 30000,
            "sector": "Salud",
        },
    ]

    llm_response = json.dumps(
        {
            "primary_soql": "$select=documento_contratista,valor_sancion&$limit=1000",
            "partner_soql": "$select=documento_proveedor,nombre_proveedor,valor_contrato,sector&$limit=1000",
            "join_key_primary": "documento_contratista",
            "join_key_partner": "documento_proveedor",
        }
    )

    state = _build_state_for_join()

    with (
        patch("app.agents.graph.T.get_schema") as mock_schema,
        patch("app.agents.graph.T.query_dataset") as mock_query,
        patch("app.agents.graph.llm_complete_small", return_value=llm_response),
    ):
        mock_schema.side_effect = lambda did: (
            primary_schema if did == "4n4q-k399" else partner_schema
        )
        mock_query.side_effect = lambda did, soql: (
            {"rows": primary_rows, "count": len(primary_rows), "error": None}
            if did == "4n4q-k399"
            else {"rows": partner_rows, "count": len(partner_rows), "error": None}
        )

        result = join_query_node(state)

    merged = result["query_result"]["rows"]
    assert result["query_result"]["error"] is None

    assert len(merged) == 1
    assert merged[0]["nombre_proveedor"] == "ACME S.A.S"
    assert merged[0]["valor_contrato"] == 50000


def test_join_query_node_handles_primary_query_failure() -> None:
    """If the primary query fails, the node captures the error and bails."""
    import json

    llm_response = json.dumps(
        {
            "primary_soql": "$select=documento_contratista&$limit=1000",
            "partner_soql": "$select=documento_proveedor&$limit=1000",
            "join_key_primary": "documento_contratista",
            "join_key_partner": "documento_proveedor",
        }
    )
    state = _build_state_for_join()

    with (
        patch("app.agents.graph.T.get_schema") as mock_schema,
        patch("app.agents.graph.T.query_dataset") as mock_query,
        patch("app.agents.graph.llm_complete_small", return_value=llm_response),
    ):
        mock_schema.side_effect = lambda did: {
            "id": did,
            "name": did,
            "permalink": f"https://datos.gov.co/d/{did}",
            "columns": [],
        }
        mock_query.side_effect = lambda did, soql: (
            {"rows": [], "count": 0, "error": "HTTP 500"}
            if did == "4n4q-k399"
            else {"rows": [], "count": 0, "error": None}
        )

        result = join_query_node(state)

    assert result["query_result"]["error"] is not None


def test_join_query_node_handles_llm_parse_failure() -> None:
    """If the LLM returns garbage, the node bails gracefully."""
    state = _build_state_for_join()

    with (
        patch("app.agents.graph.T.get_schema") as mock_schema,
        patch("app.agents.graph.llm_complete_small", return_value="not valid json at all"),
    ):
        mock_schema.side_effect = lambda did: {
            "id": did,
            "name": did,
            "permalink": f"https://datos.gov.co/d/{did}",
            "columns": [],
        }

        result = join_query_node(state)

    assert result["query_result"]["error"] == "join_llm_parse_failed"
