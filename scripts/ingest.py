"""LifeOS Ingestion — transcribe audio and build semantic graph.

Usage: devenv shell -- uv run python scripts/ingest.py <audio_file> [--verbose]

--verbose enables full-fidelity JSONL tracing to ./traces/.
"""

import argparse
import logging
import uuid

logging.basicConfig(level=logging.WARNING)
from datetime import datetime, timezone
from pathlib import Path

from lifeos.agent.compress import run_compression_pass
from lifeos.agent.harness import AgentHarness
from lifeos.agent.tools import build_tools
from lifeos.core.config import get_config
from lifeos.core.transcribe import transcribe_file
from lifeos.memory.graph import init_graph
from lifeos.memory.models import Transcript
from lifeos.memory.store import TranscriptStore


def get_recording_timestamp(audio_path: Path) -> datetime:
    """Extract recording timestamp from file mtime.

    Per D-21: read from filesystem metadata.
    Per Pitfall 7: Linux has no st_birthtime — use st_mtime.
    """
    mtime = audio_path.stat().st_mtime
    return datetime.fromtimestamp(mtime, tz=timezone.utc)


def load_prompt(path: str) -> str:
    """Load a prompt file from disk."""
    return Path(path).read_text(encoding="utf-8")


def tracking_wrapper(tools_dict: dict) -> tuple[dict, list, list]:
    """Wrap tool callables to track which node/edge IDs were created or updated."""
    modified_node_ids: list[str] = []
    modified_edge_ids: list[str] = []

    wrapped: dict = {}
    for name, fn in tools_dict.items():
        if name in ("create_node", "update_node"):

            def make_node_wrapper(original, id_list):
                def wrapper(**kwargs):
                    result = original(**kwargs)
                    if isinstance(result, dict) and "node_id" in result:
                        id_list.append(result["node_id"])
                    return result

                return wrapper

            wrapped[name] = make_node_wrapper(fn, modified_node_ids)
        elif name in ("create_edge", "update_edge"):

            def make_edge_wrapper(original, id_list):
                def wrapper(**kwargs):
                    result = original(**kwargs)
                    if isinstance(result, dict) and "edge_id" in result:
                        id_list.append(result["edge_id"])
                    return result

                return wrapper

            wrapped[name] = make_edge_wrapper(fn, modified_edge_ids)
        else:
            wrapped[name] = fn

    return wrapped, modified_node_ids, modified_edge_ids


def main():
    parser = argparse.ArgumentParser(
        prog="ingest.py",
        description="LifeOS Ingestion — transcribe audio and build semantic graph.",
    )
    parser.add_argument(
        "audio_file",
        type=Path,
        help="Path to the audio file to transcribe and ingest.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help=(
            "Enable full-fidelity JSONL tracing to ./traces/. "
            "Useful for debugging agent decisions."
        ),
    )
    args = parser.parse_args()

    audio_path: Path = args.audio_file
    if not audio_path.exists():
        parser.error(f"file not found: {audio_path}")

    # Initialize config and services
    config = get_config()
    graph = init_graph(config.falkordb_host, config.falkordb_port, config.graph_name)
    store = TranscriptStore(config.transcript_dir)

    # Set up optional tracer (--verbose only controls tracing)
    tracer = None
    if args.verbose:
        from lifeos.agent.tracer import JsonlTracer

        tracer = JsonlTracer()
        print(f"[ingest] Verbose mode: tracing to {tracer.trace_file}")

    # Step 1 — Transcribe
    print(f"[ingest] Transcribing {audio_path.name}...")
    raw = transcribe_file(audio_path, config)

    # Step 2 — Store transcript
    transcript_id = str(uuid.uuid4())
    recorded_at = get_recording_timestamp(audio_path)
    transcript = Transcript(
        id=transcript_id,
        recorded_at=recorded_at,
        text=raw.get("text", ""),
        segments=raw.get("segments", []),
    )
    store.save(transcript_id, transcript.model_dump(mode="json"))
    print(f"[ingest] Transcript stored: {transcript_id}")

    # Step 3 — Run ingestion agent
    tools, declarations = build_tools(graph, store, recording_timestamp=recorded_at)
    wrapped_tools, modified_node_ids, modified_edge_ids = tracking_wrapper(tools)

    # NOTE: AgentHarness will be fully migrated to litellm in plan 02.
    # For now, harness construction stays compatible with current harness.py signature.
    harness = AgentHarness(
        model=config.gemini_model,
        tools=wrapped_tools,
        declarations=declarations,
        tracer=tracer,
    )

    system_prompt = load_prompt("prompts/ingest.md")
    user_message = (
        f"Transcript ID: {transcript_id}\n"
        f"Recording from {recorded_at.strftime('%Y-%m-%d %H:%M')}:\n\n{transcript.text}"
    )

    harness.run(system_prompt=system_prompt, user_message=user_message)
    print("[ingest] Agent processing complete.")

    # Step 4 — Compression pass
    compressed = run_compression_pass(
        graph, modified_node_ids, modified_edge_ids, model=config.gemini_model
    )
    print(f"[ingest] Compressed {compressed} log(s).")

    # Step 5 — Print summary
    # Reload transcript to get episode spans (agent may have written them)
    episode_spans = store.load(transcript_id).get("episode_spans", [])
    span_count = len(episode_spans)

    print("[ingest] === Ingestion Summary ===")
    print(f"[ingest] Transcript: {transcript_id}")
    print(f"[ingest] Recording: {recorded_at.strftime('%Y-%m-%d %H:%M')}")
    print(f"[ingest] Nodes touched: {len(set(modified_node_ids))}")
    print(f"[ingest] Edges touched: {len(set(modified_edge_ids))}")
    print(f"[ingest] Episode spans: {span_count}")
    print(f"[ingest] Logs compressed: {compressed}")


if __name__ == "__main__":
    main()
