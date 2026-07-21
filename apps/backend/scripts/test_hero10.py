"""Run all 10 Hero questions through the agent and report results.

Usage:
    uv run python -m scripts.test_hero10

Prints a table with: question, expected dataset_id, actual dataset_id,
match (pass/fail), answer preview, soql, error, and elapsed time.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import yaml


def _load_hero_questions() -> list[dict]:
    """Load hero questions from the YAML file."""
    yaml_path = Path(__file__).resolve().parent.parent / "data" / "hero_questions.yaml"
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    return data.get("hero_questions", [])


def _truncate(text: str | None, max_len: int = 100) -> str:
    """Truncate a string to max_len chars, adding '...' if needed."""
    if not text:
        return ""
    text = str(text).replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def main() -> None:
    """Run all hero questions and print a summary table."""
    print("=" * 100)
    print("Manglar Hero-10 Test Suite")
    print("=" * 100)

    # Import here so module-level errors show before timing starts
    from app.agents.graph import run_agent

    questions = _load_hero_questions()
    if not questions:
        print("ERROR: No hero questions found in data/hero_questions.yaml")
        sys.exit(1)

    print(f"\nRunning {len(questions)} hero questions...\n")

    results: list[dict] = []
    total_start = time.time()

    for i, q in enumerate(questions, 1):
        qid = q.get("id", i)
        question = q.get("question", "")
        expected_datasets = q.get("datasets", [])
        expected_id = expected_datasets[0] if expected_datasets else None

        print(f"[{qid}/{len(questions)}] {question[:70]}...")
        t0 = time.time()
        error_msg = None
        state = None

        try:
            state = run_agent(question)
        except Exception as exc:
            error_msg = str(exc)
            print(f"  EXCEPTION: {exc}")

        elapsed = time.time() - t0

        actual_id = state.get("dataset_id") if state else None
        answer = state.get("answer") if state else None
        soql = state.get("soql") if state else None
        query_result = state.get("query_result") if state else None
        if query_result and isinstance(query_result, dict) and query_result.get("error"):
            error_msg = query_result["error"]

        # Check match: actual dataset should be in expected list
        match = False
        if actual_id and expected_datasets:
            match = actual_id in expected_datasets
        elif actual_id == expected_id:
            match = True

        status = "PASS" if match else "FAIL"
        print(f"  -> {status} | dataset={actual_id} | expected={expected_id} | {elapsed:.1f}s")

        results.append(
            {
                "id": qid,
                "question": question,
                "expected": expected_id or "(none)",
                "actual": actual_id or "(none)",
                "match": status,
                "answer": _truncate(answer),
                "soql": _truncate(soql, 80),
                "error": _truncate(error_msg, 80) if error_msg else "",
                "time": f"{elapsed:.1f}s",
            }
        )

    total_elapsed = time.time() - total_start

    # Print summary table
    print("\n" + "=" * 100)
    print("SUMMARY TABLE")
    print("=" * 100)

    # Header
    header = f"{'#':<3} {'Match':<6} {'Expected':<16} {'Actual':<16} {'Time':<8} {'Question'}"
    print(header)
    print("-" * 100)

    passes = 0
    for r in results:
        match_str = r["match"]
        if match_str == "PASS":
            passes += 1
        line = (
            f"{r['id']:<3} {match_str:<6} {r['expected']:<16} {r['actual']:<16} "
            f"{r['time']:<8} {_truncate(r['question'], 50)}"
        )
        print(line)

    print("-" * 100)
    print(f"\nTotal: {passes}/{len(results)} passed | Time: {total_elapsed:.1f}s")

    # Detailed results
    print("\n" + "=" * 100)
    print("DETAILED RESULTS")
    print("=" * 100)
    for r in results:
        print(f"\n--- Q{r['id']}: {r['match']} ---")
        print(f"  Question: {r['question']}")
        print(f"  Expected: {r['expected']}")
        print(f"  Actual:   {r['actual']}")
        print(f"  Answer:   {r['answer']}")
        print(f"  SoQL:     {r['soql']}")
        if r["error"]:
            print(f"  Error:    {r['error']}")
        print(f"  Time:     {r['time']}")

    # Exit with non-zero if any failures
    if passes < len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
