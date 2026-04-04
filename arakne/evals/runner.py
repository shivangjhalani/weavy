"""
Eval runner — executes scenarios through the real harness and logs results to Langfuse.

Each scenario run is linked to its Langfuse dataset item so results are visible
in the Langfuse Experiments UI. Scores are posted separately via judges.py.
"""

from arakne.evals.scenarios import EvalItem, load_dataset


def run_scenario(item: EvalItem, run_name: str) -> dict:
    """Run one eval item through the harness. Returns a result dict with trace_id and status.

    The trace is linked to the Langfuse dataset item via item.link(), making it
    visible in the Langfuse Experiments UI under the given run_name.
    """
    from arakne.modes import ingestion as ingestion_mode
    from arakne.modes import query as query_mode

    if item.mode == "ingestion":
        transcript_id = item.input["transcript_id"]
        trace = ingestion_mode.run_ingestion(transcript_id)
    elif item.mode == "query":
        question = item.input["question"]
        trace = query_mode.run_query(question)
    else:
        raise ValueError(f"Unsupported eval mode: {item.mode}")

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
    items = load_dataset(dataset_name)
    results = []
    for item in items:
        result = run_scenario(item, run_name)
        results.append(result)
    return results
