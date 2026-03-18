"""
Scalar metric extraction from structured judge output.
"""
from __future__ import annotations


def compute_metric(judge_results: list[dict]) -> float:
    """Mean judge score across all days. The ONE metric for optimization."""
    scores = [r["score"] for r in judge_results if isinstance(r, dict) and r.get("score")]
    if not scores:
        return 0.0
    return sum(scores) / len(scores)
