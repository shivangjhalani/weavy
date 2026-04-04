"""
Eval reports — Langfuse is the dashboard.

Results, scores, and comparisons across dataset runs are visible at:
    http://localhost:3100  →  Datasets  →  <dataset_name>  →  Experiments

This module provides helpers to print a summary of a local run_suite result
before viewing the full analysis in Langfuse.
"""


def print_suite_summary(results: list[dict]) -> None:
    """Print a brief summary of a run_suite result to stdout."""
    total = len(results)
    completed = sum(1 for r in results if r["status"] == "completed")
    failed = total - completed

    print(f"\nEval suite: {completed}/{total} completed, {failed} failed")
    for r in results:
        icon = "✓" if r["status"] == "completed" else "✗"
        print(f"  [{icon}] item={r['item_id']} trace={r['trace_id']}")
        if r.get("error"):
            print(f"       error: {r['error']}")

    print("\nFull results in Langfuse → Datasets → Experiments")
