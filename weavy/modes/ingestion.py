"""
Ingestion mode — transcript-first memory construction.
"""

from weavy.config import settings
from weavy.harness.actions import INGESTION_ACTIONS
from weavy.harness.runner import run
from weavy.models.traces import RunTrace
from weavy.services.workflow import build_themed_system_prompt, finalize_ingestion
from weavy.store import canonical as store_canonical
from weavy.store import system as store_system
from weavy.store.client import get_graph
from weavy.timefmt import format_agent_timestamp


def run_ingestion(transcript_id: str) -> RunTrace:
    """Load transcript and run ingestion harness."""
    graph = get_graph(settings.GRAPH_NAME)

    state = store_canonical.get_ingestion_state(graph, transcript_id)
    if state in {"running", "completed"}:
        raise ValueError(f"Transcript '{transcript_id}' is already {state}.")

    transcript = store_canonical.get_transcript(graph, transcript_id)
    system_state = store_system.get_system(graph)

    store_canonical.set_ingestion_state(graph, transcript_id, "running")

    system_prompt = build_themed_system_prompt(
        "weavy-ingestion",
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
            allowed_actions=INGESTION_ACTIONS,
            run_context={"input_summary": f"Ingesting {transcript_id}"},
            graph=graph,
            session_id=transcript_id,
        )
    except Exception:
        store_canonical.set_ingestion_state(graph, transcript_id, "failed")
        raise

    return finalize_ingestion(graph, transcript_id, trace)
