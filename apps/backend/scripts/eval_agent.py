"""Offline agent eval: runs the agent on each hero question.

Reports SoQL-success rate + a simple faithfulness heuristic.

SoQL-success: ``query_result.error`` is None AND ``len(rows) > 0``.
  - Exception: if a hero has ``expect_refusal: true``, success is defined as
    ``dataset_id is None`` (agent correctly refused to answer).
Faithfulness:
  - If ``answer_shape == "number"``: answer must contain at least one digit
    sequence, otherwise fail with reason ``no_number_in_answer``.
  - Otherwise: the first source's dataset name must appear in the answer.
  - Exception: if a hero has ``expect_refusal: true``, success is defined as
    ``dataset_id is None`` (agent correctly refused to answer).

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


def _faithfulness_check(state: dict[str, Any], answer_shape: str) -> tuple[bool, str]:
    """Return (pass, reason). Reason is empty on pass."""
    # If the query failed, faithfulness cannot be established.
    if not _soql_success(state):
        return False, "no_data_soql_failed"

    answer = state.get("answer") or ""
    shape = (answer_shape or "").strip().lower()

    if shape.startswith("number"):
        qr = state.get("query_result") or {}
        rows = qr.get("rows") or []

        expected_numbers: list[float] = []
        if len(rows) == 1 and rows[0]:
            expected_numbers = [
                n for n in (_coerce_number(v) for v in rows[0].values()) if n is not None
            ]
        elif rows:
            expected_numbers = [float(len(rows))]

        if expected_numbers:
            answer_digits = _digits_only(answer)
            for val in expected_numbers:
                int_part = int(round(val))
                variants = {
                    str(val),
                    f"{int_part:,}",
                    f"{int_part:,}".replace(",", "."),
                }
                if isinstance(val, float):
                    variants.add(str(int_part))
                for variant in variants:
                    variant_digits = _digits_only(variant)
                    if variant_digits and variant_digits in answer_digits:
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
    header = f"{'id':<3}  {'question':<42}  {'dataset':<12}  {'soql':<5}  {'faith':<5}  reason"
    print(header)
    print("-" * len(header) + "-" * 20)
    for r in rows:
        print(
            f"{r['id']:<3}  {_truncate(r['question'], 42):<42}  "
            f"{(r['dataset_id'] or '-'):<12}  "
            f"{'OK' if r['soql_succ'] else 'FAIL':<5}  "
            f"{'OK' if r['faith'] else 'FAIL':<5}  "
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
    faith_hits = 0
    total = 0

    for hero in heroes:
        qid = hero.get("id")
        question = hero.get("question", "")
        answer_shape = hero.get("answer_shape", "")

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
                    "soql_succ": False,
                    "faith": False,
                    "reason": f"exception:{type(exc).__name__}",
                }
            )
            continue

        did = state.get("dataset_id")
        if hero.get("expect_refusal"):
            refused = did is None
            soql_ok = refused
            faith_ok = refused
            reason = "" if refused else "expected_refusal_but_answered"
        else:
            soql_ok = _soql_success(state)
            faith_ok, reason = _faithfulness_check(state, answer_shape)

        if soql_ok:
            soql_hits += 1
        if faith_ok:
            faith_hits += 1
        total += 1

        rows.append(
            {
                "id": qid,
                "question": question,
                "dataset_id": did,
                "soql_succ": soql_ok,
                "faith": faith_ok,
                "reason": reason,
            }
        )
        print(
            f"  -> dataset={did}  soql={'OK' if soql_ok else 'FAIL'}  "
            f"faith={'OK' if faith_ok else 'FAIL'}  "
            f"({elapsed:.1f}s)"
        )

    print()
    _print_table(rows)

    print()
    print("= Agregado =")
    if total:
        print(f"  soql_success_rate  = {soql_hits}/{total} = {soql_hits / total:.3f}")
        print(f"  faithfulness_rate  = {faith_hits}/{total} = {faith_hits / total:.3f}")
    else:
        print("  (sin preguntas evaluadas)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
