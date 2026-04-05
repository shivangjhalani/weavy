"""
Ingestion mode — transcript-first memory construction.
"""

from arakne.config import settings
from arakne.harness import registry as reg
from arakne.harness.runner import run
from arakne.models.traces import RunTrace
from arakne.modes._common import build_themed_system_prompt, run_post_trace_hooks
from arakne.store import canonical as store_canonical
from arakne.store import system as store_system
from arakne.store.client import get_graph
from arakne.timefmt import format_agent_timestamp


def run_ingestion(transcript_id: str) -> RunTrace:
    """Load transcript, run ingestion harness, trigger post-run theme pass.

    Raises ValueError if the transcript has already been ingested.
    Call rollback_ingestion(transcript_id) first to undo before re-ingesting.
    """
    graph = get_graph(settings.GRAPH_NAME)

    if store_canonical.get_ingestion_status(graph, transcript_id) == 1:
        raise ValueError(
            f"Transcript '{transcript_id}' has already been ingested. "
            "Call rollback_ingestion() first to undo before re-ingesting."
        )

    transcript = store_canonical.get_transcript(graph, transcript_id)
    system_state = store_system.get_system(graph)

    # Mark in-progress — blocks any concurrent or accidental re-run.
    store_canonical.set_ingestion_status(graph, transcript_id, 1)

    system_prompt = build_themed_system_prompt(
        "arakne-ingestion",
        graph,
        system_state,
        empty_themes_message="(No themes yet — this may be the first ingestion.)",
    )

    transcript_message = (
        f"Ingest this transcript.\n\n"
        f"ID: {transcript.id}\n"
        f"Recorded: {format_agent_timestamp(transcript.timestamp)}\n\n"
        f"{transcript.text}"
    )

    try:
        trace = run(
            mode="ingestion",
            system_prompt=system_prompt,
            initial_messages=[{"role": "user", "content": transcript_message}],
            allowed_tools=reg.INGESTION_TOOLS,
            run_context={"input_summary": f"Ingesting {transcript_id}"},
            graph=graph,
            session_id=transcript_id,
        )
    except Exception:
        store_canonical.set_ingestion_status(graph, transcript_id, 0)
        raise

    if trace.status != "completed":
        # Failed run — reset flag so the transcript can be re-ingested cleanly.
        store_canonical.set_ingestion_status(graph, transcript_id, 0)
        return trace

    run_post_trace_hooks(
        trace,
        graph,
        system_state,
        completion_text=(trace.completion_payload or {}).get("summary", ""),
    )

    # Persist the ordered mutation log on the transcript node.
    # Even an empty list is saved so the manifest can be queried.
    store_canonical.save_run_manifest(graph, transcript_id, trace.mutation_ops)

    return trace
