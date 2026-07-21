"""Evaluation utilities shared between the B2 eval harness and tests.

The canonical ``compute_recall_at_k`` lives here so both the retrieval eval
(``scripts/eval_retrieval.py``) and unit tests can import from a single location
without creating a dependency on the scripts package.
"""

from __future__ import annotations


def compute_recall_at_k(
    returned_ids: list[str],
    truth_ids: list[str],
    k: int,
) -> float:
    """Fraction of ground-truth dataset ids that appear in the top-k results.

    - ``returned_ids`` is ordered by rank (index 0 = top result).
    - ``truth_ids`` is the hero's ``datasets`` list.
    - Returns 0.0 when ``truth_ids`` is empty, when ``k <= 0``, or when nothing
      matches. Duplicates in either input are de-duplicated before computing.
    - Raises ``ValueError`` on negative ``k`` so callers catch misuse early.
    """
    if k < 0:
        raise ValueError(f"k must be >= 0, got {k}")
    if k == 0 or not truth_ids:
        return 0.0

    truth_set = {tid for tid in truth_ids if tid}
    if not truth_set:
        return 0.0

    seen: set[str] = set()
    unique_top_k: list[str] = []
    for rid in returned_ids[:k]:
        if rid and rid not in seen:
            seen.add(rid)
            unique_top_k.append(rid)

    hits = sum(1 for rid in unique_top_k if rid in truth_set)
    return hits / len(truth_set)
