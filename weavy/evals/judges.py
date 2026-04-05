"""
LLM judge scoring — post evaluation scores to Langfuse traces.

Scores are attached to traces by trace_id and appear in the Langfuse UI
under the Scores tab. Use named scores consistently across runs so the
Experiments view can compare them across dataset runs.
"""


def score_trace(
    trace_id: str,
    name: str,
    value: float,
    comment: str = "",
) -> None:
    """Post a numeric score to a Langfuse trace.

    Args:
        trace_id: The Langfuse trace ID (RunTrace.run_id).
        name: Score dimension name, e.g. "answer_grounding", "node_precision".
        value: Numeric score, typically 0.0–1.0.
        comment: Optional explanation for the score.
    """
    from weavy.langfuse_client import get_langfuse

    get_langfuse().create_score(
        trace_id=trace_id,
        name=name,
        value=value,
        comment=comment or None,
    )


def score_boolean(trace_id: str, name: str, passed: bool, comment: str = "") -> None:
    """Post a boolean score (1.0 = pass, 0.0 = fail) to a Langfuse trace."""
    score_trace(trace_id, name, 1.0 if passed else 0.0, comment)
