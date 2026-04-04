"""
LLM judge scoring — semantic quality checks over harness run outputs.
Implemented in Phase 9.
"""

from arakne.models.traces import RunTrace


def score_run(trace: RunTrace, rubrics: list[dict]) -> dict[str, float]:
    """Score a run trace against a list of judge rubrics. Returns dimension -> score."""
    raise NotImplementedError
