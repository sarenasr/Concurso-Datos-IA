"""Unit tests for the eval harness recall@k helper.

Uses a small fixed list of fake hero dicts (no YAML) to verify the pure
``compute_recall_at_k`` function behaves correctly across edge cases.
"""

from __future__ import annotations

import pytest

from app.rag.eval_utils import compute_recall_at_k
from scripts.eval_agent import _dataset_selection_check, _faithfulness_check


def test_recall_at_1_hit() -> None:
    assert compute_recall_at_k(["a", "b", "c"], ["a"], 1) == 1.0


def test_recall_at_1_miss() -> None:
    assert compute_recall_at_k(["b", "c", "d"], ["a"], 1) == 0.0


def test_recall_at_3_partial() -> None:
    # 1 of 2 truth ids in top-3 -> 0.5
    assert compute_recall_at_k(["a", "x", "y"], ["a", "b"], 3) == 0.5


def test_recall_at_3_full() -> None:
    assert compute_recall_at_k(["a", "b", "c"], ["a", "b"], 3) == 1.0


def test_recall_at_5_more_truth_than_k() -> None:
    # 2 of 4 truth ids in top-5 -> 0.5
    assert compute_recall_at_k(["a", "b", "x", "y", "z"], ["a", "b", "c", "d"], 5) == 0.5


def test_recall_at_k_empty_truth_returns_zero() -> None:
    # No ground-truth datasets -> recall is undefined; return 0.0 so the
    # aggregate mean is not polluted.
    assert compute_recall_at_k(["a", "b"], [], 3) == 0.0


def test_recall_at_k_empty_results() -> None:
    assert compute_recall_at_k([], ["a", "b"], 3) == 0.0


def test_recall_at_k_n_larger_than_results() -> None:
    # k=10 but only 3 results returned; truth of 1 hit -> 1.0
    assert compute_recall_at_k(["a", "b", "c"], ["a"], 10) == 1.0


def test_recall_at_k_n_zero() -> None:
    # k=0 is degenerate; no results considered -> 0.0
    assert compute_recall_at_k(["a", "b"], ["a"], 0) == 0.0


def test_recall_at_k_dedups_truth() -> None:
    # Duplicate truth ids should not inflate the denominator.
    assert compute_recall_at_k(["a", "b"], ["a", "a"], 2) == 1.0


def test_recall_at_k_dedups_results() -> None:
    # Duplicate returned ids should not inflate the numerator beyond truth size.
    assert compute_recall_at_k(["a", "a", "a"], ["a"], 3) == 1.0


def test_recall_at_k_case_sensitive() -> None:
    # IDs are case-sensitive (Socrata dataset ids are lower-case but be safe).
    assert compute_recall_at_k(["A"], ["a"], 1) == 0.0


def test_recall_at_k_real_hero_shape() -> None:
    # Hero 3 shape: truth = ["4n4q-k399", "jbjy-vk9h"], top-10 returns both.
    returned = [
        "jbjy-vk9h",
        "xxxx-yyyy",
        "4n4q-k399",
        "aaaa-bbbb",
        "cccc-dddd",
    ]
    truth = ["4n4q-k399", "jbjy-vk9h"]
    assert compute_recall_at_k(returned, truth, 3) == 1.0
    assert compute_recall_at_k(returned, truth, 1) == 0.5


def test_compute_recall_at_k_rejects_negative_k() -> None:
    with pytest.raises(ValueError):
        compute_recall_at_k(["a"], ["a"], -1)


# --- _faithfulness_check: stringified Socrata numbers -----------------------


def test_faithfulness_check_grounds_stringified_count_colombian_format() -> None:
    # Socrata returns count(*) as a string; answer uses Colombian thousands
    # separator ("10.005") — the digit-only comparison must still match.
    state = {
        "query_result": {"rows": [{"total": "10005"}], "error": None},
        "answer": "Se encontraron 10.005 registros en total.",
    }
    assert _faithfulness_check(state, "number") == (True, "")


def test_faithfulness_check_fails_on_wrong_number() -> None:
    state = {
        "query_result": {"rows": [{"total": "10005"}], "error": None},
        "answer": "Se encontraron 999 registros en total.",
    }
    assert _faithfulness_check(state, "number") == (False, "expected_number_not_in_answer")


def test_faithfulness_check_multirow_uses_result_values_not_row_count() -> None:
    state = {
        "query_result": {
            "rows": [
                {"mes": "2026-06-01T00:00:00.000", "promedio": "4211.35"},
                {"mes": "2025-06-01T00:00:00.000", "promedio": "4102.80"},
            ],
            "error": None,
        },
        "answer": "La TRM promedio fue 4.211,35 frente a 4.102,80.",
    }

    assert _faithfulness_check(state, "number + line_chart", min_numeric_matches=2) == (
        True,
        "",
    )


def test_faithfulness_check_multirow_does_not_accept_only_row_count() -> None:
    state = {
        "query_result": {
            "rows": [
                {"mes": "2026-06-01T00:00:00.000", "promedio": "4211.35"},
                {"mes": "2025-06-01T00:00:00.000", "promedio": "4102.80"},
            ],
            "error": None,
        },
        "answer": "La consulta devolviÃ³ 2 filas.",
    }

    assert _faithfulness_check(state, "number + line_chart") == (
        False,
        "expected_number_not_in_answer",
    )


def test_faithfulness_check_single_row_requires_all_numeric_outputs() -> None:
    state = {
        "query_result": {
            "rows": [{"vigentes": "120", "cardiovasculares": "35"}],
            "error": None,
        },
        "answer": "Hay 120 medicamentos vigentes.",
    }

    assert _faithfulness_check(state, "number") == (
        False,
        "expected_number_not_in_answer",
    )


def test_dataset_selection_check_requires_all_join_datasets() -> None:
    state = {"dataset_id": "4n4q-k399", "join_partner_id": "jbjy-vk9h"}
    assert _dataset_selection_check(state, ["4n4q-k399", "jbjy-vk9h"]) is True
    assert _dataset_selection_check(state, ["4n4q-k399", "missing-id"]) is False


def test_dataset_selection_check_is_unscored_without_expected_ids() -> None:
    assert _dataset_selection_check({"dataset_id": "anything"}, []) is None
