"""
Eval runner — executes scenarios through the real harness and logs results to Langfuse.

Each scenario run is linked to its Langfuse dataset item so results are visible
in the Langfuse Experiments UI. Scores are posted separately via judges.py.
"""

from weavy.evals.scenarios import EvalItem, load_dataset
from weavy.models.traces import TouchedEdge, TouchedNode


def _run_eval_item(item: EvalItem):
    from weavy.modes import ingestion as ingestion_mode
    from weavy.modes import query as query_mode
    from weavy.modes import theme as theme_mode

    if item.mode == "ingestion":
        return ingestion_mode.run_ingestion(item.input["transcript_id"])
    if item.mode == "query":
        return query_mode.run_query(item.input["question"])
    return theme_mode.run_theme_update(
        item.input["summary"],
        [
            node if isinstance(node, TouchedNode) else TouchedNode(**node)
            for node in item.input.get("touched_nodes", [])
        ],
        [
            edge if isinstance(edge, TouchedEdge) else TouchedEdge(**edge)
            for edge in item.input.get("touched_edges", [])
        ],
    )


def run_scenario(item: EvalItem, run_name: str) -> dict:
    """Run one eval item through the harness. Returns a result dict with trace_id and status.

    The trace is linked to the Langfuse dataset item via item.link(), making it
    visible in the Langfuse Experiments UI under the given run_name.
    """
    trace = _run_eval_item(item)

    if item.dataset_item is not None:
        item.dataset_item.link(
            trace_or_observation=None,
            run_name=run_name,
            run_metadata={"mode": item.mode},
            trace_id=trace.run_id,
        )

    return {
        "item_id": item.item_id,
        "trace_id": trace.run_id,
        "status": trace.status,
        "completion_payload": trace.completion_payload,
        "error": trace.error,
    }


def run_suite(dataset_name: str, run_name: str) -> list[dict]:
    """Run all items in a Langfuse dataset. Returns list of result dicts."""
    return [run_scenario(item, run_name) for item in load_dataset(dataset_name)]
