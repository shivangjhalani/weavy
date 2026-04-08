"""
Weavy CLI — entry point for operational commands.
Run as: python -m weavy.cli <command>
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from weavy.models.canonical import ChatMessage, ChatSession, Transcript
from weavy.models.tools import ListChatsInput, ListTranscriptsInput
from weavy.store.canonical import (
    create_chat_session,
    create_transcript,
    list_chats,
    list_transcripts,
)
from weavy.store.client import get_graph
from weavy.store.system import SystemState, get_system, increment_counter, init_system


def _print_system_state(header: str, state: SystemState) -> None:
    print(f"{header}:")
    print(f"  next_node_id          = {state.next_node_id}")
    print(f"  next_edge_id          = {state.next_edge_id}")
    print(f"  next_rec_id           = {state.next_rec_id}")
    print(f"  next_chat_id          = {state.next_chat_id}")
    print(f"  hot_theme_token_budget = {state.hot_theme_token_budget}")
    print(f"  theme_priority_order  = {state.theme_priority_order}")


def cmd_init_system(_args: argparse.Namespace) -> None:
    graph = get_graph()
    state = init_system(graph)
    _print_system_state("System node initialised", state)


def cmd_status(_args: argparse.Namespace) -> None:
    graph = get_graph()
    state = get_system(graph)
    _print_system_state("System state", state)


def cmd_create_transcript(args: argparse.Namespace) -> None:
    text_path = Path(args.text_file)
    text = text_path.read_text()
    graph = get_graph()
    get_system(graph)  # ensures System node exists
    rec_id = increment_counter(graph, "rec")
    transcript = Transcript(
        id=rec_id,
        audio_path=args.audio_path,
        timestamp=datetime.now(tz=timezone.utc),
        text=text,
    )
    create_transcript(graph, transcript)
    print(f"Created transcript {rec_id}")


def cmd_list_transcripts(args: argparse.Namespace) -> None:
    graph = get_graph()
    output = list_transcripts(graph, ListTranscriptsInput(limit=args.limit))
    if not output.transcripts:
        print("No transcripts found.")
        return
    for t in output.transcripts:
        print(f"  {t.id}  {t.timestamp.isoformat()}  {t.audio_path}")


def cmd_create_chat(args: argparse.Namespace) -> None:
    messages_path = Path(args.messages_file)
    raw = json.loads(messages_path.read_text())
    messages = [ChatMessage(**m) for m in raw]
    graph = get_graph()
    get_system(graph)  # ensures System node exists
    chat_id = increment_counter(graph, "chat")
    session = ChatSession(
        id=chat_id,
        timestamp=datetime.now(tz=timezone.utc),
        messages=messages,
    )
    create_chat_session(graph, session)
    print(f"Created chat session {chat_id}")


def cmd_list_chats(args: argparse.Namespace) -> None:
    graph = get_graph()
    output = list_chats(graph, ListChatsInput(limit=args.limit))
    if not output.chats:
        print("No chat sessions found.")
        return
    for c in output.chats:
        print(f"  {c.id}  {c.timestamp.isoformat()}")


def cmd_ingest(args: argparse.Namespace) -> None:
    from weavy.modes.ingestion import run_ingestion

    trace = run_ingestion(args.transcript_id)
    print(f"Status: {trace.status}")
    if trace.error:
        print(f"Error: {trace.error}", file=sys.stderr)
    else:
        touched = [n.node_id for n in trace.touched_nodes]
        summary = (trace.completion_payload or {}).get("summary", "")
        print(f"Touched nodes: {touched}")
        print(f"Summary: {summary}")


def cmd_transcribe(args: argparse.Namespace) -> None:
    from weavy.transcribe import transcribe_audio

    print(f"Transcribing {args.audio_path} ...")
    text = transcribe_audio(args.audio_path)

    graph = get_graph()
    get_system(graph)  # ensure System node exists
    rec_id = increment_counter(graph, "rec")
    transcript = Transcript(
        id=rec_id,
        audio_path=args.audio_path,
        timestamp=datetime.now(tz=timezone.utc),
        text=text,
    )
    create_transcript(graph, transcript)

    print(f"Stored as {rec_id}\n")
    print(text)


def cmd_update_themes(args: argparse.Namespace) -> None:
    from weavy.modes.theme import run_theme_update

    trace = run_theme_update()
    print(f"Status: {trace.status}")
    if trace.error:
        print(f"Error: {trace.error}", file=sys.stderr)
    else:
        print("Theme update complete.")


def cmd_query(args: argparse.Namespace) -> None:
    if args.question is None:
        from weavy.modes.query import run_chat_repl
        run_chat_repl()
        return

    from weavy.modes.query import run_query

    trace = run_query(args.question)
    print(f"Status: {trace.status}")
    if trace.error:
        print(f"Error: {trace.error}", file=sys.stderr)
    else:
        answer = (trace.completion_payload or {}).get("answer", "")
        print(f"\n{answer}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="weavy", description="Weavy CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-system", help="Initialise the System node in FalkorDB")
    subparsers.add_parser("status", help="Print current System node state")

    p = subparsers.add_parser("create-transcript", help="Store a transcript from a text file")
    p.add_argument("--audio-path", required=True, help="Path to the audio file artifact")
    p.add_argument("--text-file", required=True, help="Path to the transcript text file")

    p = subparsers.add_parser("list-transcripts", help="List stored transcripts")
    p.add_argument("--limit", type=int, default=20)

    p = subparsers.add_parser("create-chat", help="Store a chat session from a JSON messages file")
    p.add_argument(
        "--messages-file",
        required=True,
        help='Path to JSON file: [{"role": "user", "content": "..."}, ...]',
    )

    p = subparsers.add_parser("list-chats", help="List stored chat sessions")
    p.add_argument("--limit", type=int, default=20)

    p = subparsers.add_parser(
        "transcribe", help="Transcribe an audio file and store it as a transcript"
    )
    p.add_argument("audio_path", help="Path to the audio file (.mp3, .m4a, .wav, etc.)")

    p = subparsers.add_parser("ingest", help="Run ingestion for a stored transcript")
    p.add_argument("transcript_id", help="Transcript id to ingest (e.g. rec:1)")

    subparsers.add_parser("update-themes", help="Manually run the theme agent over the current graph")

    p = subparsers.add_parser("query", help="Ask a question against the memory graph")
    p.add_argument(
        "question",
        nargs="?",
        default=None,
        help='Question to ask. Omit to enter interactive chat.',
    )

    args = parser.parse_args()
    dispatch = {
        "init-system": cmd_init_system,
        "status": cmd_status,
        "create-transcript": cmd_create_transcript,
        "list-transcripts": cmd_list_transcripts,
        "create-chat": cmd_create_chat,
        "list-chats": cmd_list_chats,
        "transcribe": cmd_transcribe,
        "ingest": cmd_ingest,
        "update-themes": cmd_update_themes,
        "query": cmd_query,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
