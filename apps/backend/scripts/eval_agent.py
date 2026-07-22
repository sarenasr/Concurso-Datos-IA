"""Offline agent eval: runs the agent on each hero question.

Reports end-to-end outcome, dataset selection, SoQL success, and a deterministic
answer-grounding heuristic without spending an additional grader-LLM call.

SoQL-success: ``query_result.error`` is None AND ``len(rows) > 0``.
  - Exception: if a hero has ``expect_refusal: true``, success is defined as
    ``dataset_id is None`` (agent correctly refused to answer).
Faithfulness:
  - If ``answer_shape`` starts with ``number``: numeric values in the answer
    must match values returned by Socrata (never the arbitrary row count).
  - Otherwise: the first source's dataset name must appear in the answer.
  - Refusal and clarification heroes are scored as separate outcomes and are
    excluded from query/faithfulness denominators.

Prints a per-question table + aggregates.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from typing import Any

from app.agents.tools import _coerce_number

_DIGIT_RE = re.compile(r"\d")
_NUMBER_TOKEN_RE = re.compile(r"(?<![\w])[-+]?\d[\d.,]*(?![\w])")


def _digits_only(s: str) -> str:
    return re.sub(r"[^0-9]", "", s)


def _load_hero_questions() -> list[dict]:
    from app.agents.graph import _load_hero_questions as _graph_load

    return _graph_load()


def _truncate(text: str | None, max_len: int = 40) -> str:
    if not text:
        return ""
    text = str(text).replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _soql_success(state: dict[str, Any]) -> bool:
    qr = state.get("query_result") or {}
    if qr.get("error"):
        return False
    rows = qr.get("rows") or []
    return len(rows) > 0


def _number_variants(value: object) -> set[str]:
    """Normalize a Socrata numeric value to digit strings used in Spanish text."""
    coerced = _coerce_number(value)
    if coerced is None:
        return set()
    variants = {_digits_only(str(value))}
    if coerced.is_integer():
        variants.add(str(int(coerced)))
    return {variant for variant in variants if variant}


def _answer_number_tokens(answer: str) -> set[str]:
    return {_digits_only(token) for token in _NUMBER_TOKEN_RE.findall(answer)}


def _dataset_selection_check(state: dict[str, Any], expected_ids: list[str]) -> bool | None:
    """Require all expected dataset IDs; return ``None`` when the hero is unscored."""
    if not expected_ids:
        return None
    selected = {state.get("dataset_id"), state.get("join_partner_id")}
    selected.discard(None)
    return set(expected_ids).issubset(selected)


def _faithfulness_check(
    state: dict[str, Any],
    answer_shape: str,
    *,
    min_numeric_matches: int | None = None,
) -> tuple[bool, str]:
    """Return (pass, reason). Reason is empty on pass."""
    # If the query failed, faithfulness cannot be established.
    if not _soql_success(state):
        return False, "no_data_soql_failed"

    answer = state.get("answer") or ""
    shape = (answer_shape or "").strip().lower()

    if shape.startswith("number"):
        qr = state.get("query_result") or {}
        rows = qr.get("rows") or []

        expected_numbers: list[object] = []
        for row in rows:
            expected_numbers.extend(v for v in row.values() if _coerce_number(v) is not None)

        if expected_numbers:
            answer_tokens = _answer_number_tokens(answer)
            unique_expected: list[set[str]] = []
            seen_variants: set[frozenset[str]] = set()
            for value in expected_numbers:
                variants = _number_variants(value)
                frozen = frozenset(variants)
                if variants and frozen not in seen_variants:
                    seen_variants.add(frozen)
                    unique_expected.append(variants)

            matches = sum(bool(variants & answer_tokens) for variants in unique_expected)
            required = min_numeric_matches
            if required is None:
                required = len(unique_expected) if len(rows) == 1 else 1
            if matches >= min(required, len(unique_expected)):
                return True, ""
            return False, "expected_number_not_in_answer"

        # No computable expected number (no rows) — fall back to the weak check.
        if not _DIGIT_RE.search(answer):
            return False, "no_number_in_answer"
        return True, ""

    sources = state.get("sources") or []
    if not sources:
        return False, "no_sources"
    ds_name = (sources[0].get("name") or "").strip()
    if not ds_name:
        return False, "no_dataset_name"
    if ds_name.lower() not in answer.lower():
        return False, "dataset_name_not_in_answer"
    return True, ""


def _run_one(question: str) -> tuple[dict[str, Any], float]:
    """Invoke run_agent, clearing the in-memory cache so we always execute."""
    from app.agents.graph import _question_cache, run_agent

    _question_cache.clear()
    t0 = time.time()
    state = run_agent(question)
    elapsed = time.time() - t0
    return state, elapsed


def _print_table(rows: list[dict]) -> None:
    header = (
        f"{'id':<3}  {'question':<42}  {'dataset':<12}  {'select':<6}  "
        f"{'soql':<5}  {'faith':<5}  {'result':<6}  reason"
    )
    print(header)
    print("-" * len(header) + "-" * 20)
    for r in rows:

        def _flag(value: bool | None) -> str:
            return "N/A" if value is None else ("OK" if value else "FAIL")

        print(
            f"{r['id']:<3}  {_truncate(r['question'], 42):<42}  "
            f"{(r['dataset_id'] or '-'):<12}  "
            f"{_flag(r['dataset_match']):<6}  "
            f"{_flag(r['soql_succ']):<5}  "
            f"{_flag(r['faith']):<5}  "
            f"{_flag(r['outcome_ok']):<6}  "
            f"{r['reason']}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline agent eval: SoQL-success + faithfulness on hero questions."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Evaluate only the first N hero questions (0 = all)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm that you accept the LLM cost of running the agent",
    )
    args = parser.parse_args(argv)

    if not args.yes:
        print(
            "ADVERTENCIA: cada pregunta hace llamadas al LLM (costo real).\n"
            "Ejecuta con --yes para confirmar.",
            file=sys.stderr,
        )
        return 0

    heroes = _load_hero_questions()
    if not heroes:
        print("ERROR: hero_questions.yaml está vacío o no existe", file=sys.stderr)
        return 1

    if args.limit > 0:
        heroes = heroes[: args.limit]

    print(f"= Eval agente — {len(heroes)} preguntas (LLM real) =")
    print()

    rows: list[dict] = []
    soql_hits = 0
    soql_scored = 0
    faith_hits = 0
    faith_scored = 0
    dataset_hits = 0
    dataset_scored = 0
    outcome_hits = 0
    total = 0

    for hero in heroes:
        qid = hero.get("id")
        question = hero.get("question", "")
        answer_shape = hero.get("answer_shape", "")
        total += 1

        print(f"[{qid}] {question[:70]}…", flush=True)
        try:
            state, elapsed = _run_one(question)
        except Exception as exc:
            print(f"  EXCEPTION: {exc}", file=sys.stderr)
            rows.append(
                {
                    "id": qid,
                    "question": question,
                    "dataset_id": None,
                    "dataset_match": False if hero.get("datasets") else None,
                    "soql_succ": None,
                    "faith": None,
                    "outcome_ok": False,
                    "reason": f"exception:{type(exc).__name__}",
                }
            )
            continue

        did = state.get("dataset_id")
        dataset_match = _dataset_selection_check(state, hero.get("datasets") or [])
        if hero.get("expect_clarification"):
            clarified = bool(state.get("needs_clarification")) and not did
            soql_ok = None
            faith_ok = None
            dataset_match = None
            outcome_ok = clarified
            reason = "" if clarified else "expected_clarification_but_continued"
        elif hero.get("expect_refusal"):
            refused = did is None
            soql_ok = None
            faith_ok = None
            dataset_match = None
            outcome_ok = refused
            reason = "" if refused else "expected_refusal_but_answered"
        else:
            soql_ok = _soql_success(state)
            faith_ok, reason = _faithfulness_check(
                state,
                answer_shape,
                min_numeric_matches=hero.get("min_grounded_numbers"),
            )
            outcome_ok = bool(soql_ok and faith_ok and dataset_match is not False)

        if soql_ok is not None:
            soql_scored += 1
            soql_hits += int(soql_ok)
        if faith_ok is not None:
            faith_scored += 1
            faith_hits += int(faith_ok)
        if dataset_match is not None:
            dataset_scored += 1
            dataset_hits += int(dataset_match)
        outcome_hits += int(outcome_ok)

        rows.append(
            {
                "id": qid,
                "question": question,
                "dataset_id": did,
                "dataset_match": dataset_match,
                "soql_succ": soql_ok,
                "faith": faith_ok,
                "outcome_ok": outcome_ok,
                "reason": reason,
            }
        )
        print(f"  -> dataset={did}  outcome={'OK' if outcome_ok else 'FAIL'}  ({elapsed:.1f}s)")

    print()
    _print_table(rows)

    print()
    print("= Agregado =")
    if total:
        print(f"  outcome_success_rate = {outcome_hits}/{total} = {outcome_hits / total:.3f}")
        if dataset_scored:
            print(
                f"  dataset_selection    = {dataset_hits}/{dataset_scored} "
                f"= {dataset_hits / dataset_scored:.3f}"
            )
        if soql_scored:
            print(
                f"  soql_success_rate    = {soql_hits}/{soql_scored} "
                f"= {soql_hits / soql_scored:.3f}"
            )
        if faith_scored:
            print(
                f"  faithfulness_rate    = {faith_hits}/{faith_scored} "
                f"= {faith_hits / faith_scored:.3f}"
            )
    else:
        print("  (sin preguntas evaluadas)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
