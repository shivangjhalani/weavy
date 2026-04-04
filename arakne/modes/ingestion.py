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
    """Load transcript, run ingestion harness, trigger post-run theme pass."""
    graph = get_graph(settings.GRAPH_NAME)

    transcript = store_canonical.get_transcript(graph, transcript_id)
    system_state = store_system.get_system(graph)

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

    trace = run(
        mode="ingestion",
        system_prompt=system_prompt,
        initial_messages=[{"role": "user", "content": transcript_message}],
        allowed_tools=reg.INGESTION_TOOLS,
        run_context={"input_summary": f"Ingesting {transcript_id}"},
        graph=graph,
        session_id=transcript_id,
    )

    run_post_trace_hooks(
        trace,
        graph,
        system_state,
        completion_text=(trace.completion_payload or {}).get("summary", ""),
    )
    return trace
