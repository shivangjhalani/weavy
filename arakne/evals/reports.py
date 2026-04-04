"""
Regression reports — compare eval results across prompt/model/tool versions.
Implemented in Phase 9.
"""


def compare_runs(baseline: list[dict], candidate: list[dict]) -> dict:
    """Diff two eval result sets. Returns summary of regressions and improvements."""
    raise NotImplementedError


def render_report(comparison: dict) -> str:
    raise NotImplementedError
