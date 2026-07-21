"""Quick 3-question smoke test for Manglar agent."""

from __future__ import annotations

import time

from app.agents.graph import run_agent


QUESTIONS = [
    ("¿Cuántos medicamentos vigentes hay registrados?", "i7cb-raxc"),
    ("¿Cuántos contratos firmó Medellín en 2025?", "jbjy-vk9h"),
    ("¿Qué datos abiertos existen sobre vacunación?", None),
]

print("=" * 80)
print("Manglar Quick Smoke Test (3 questions)")
print("=" * 80)

for i, (q, expected) in enumerate(QUESTIONS, 1):
    print(f"\n[{i}] {q}")
    t0 = time.time()
    state = run_agent(q)
    elapsed = time.time() - t0

    actual = state.get("dataset_id")
    answer = (state.get("answer") or "")[:120]
    soql = state.get("soql") or ""
    error = (state.get("query_result") or {}).get("error")

    match = "PASS" if (expected is None or actual == expected) else "FAIL"
    print(f"  {match} | dataset={actual} expected={expected} | {elapsed:.1f}s")
    print(f"  answer: {answer}")
    print(f"  soql: {soql[:80]}")
    if error:
        print(f"  error: {error[:80]}")

print(f"\n{'=' * 80}")
