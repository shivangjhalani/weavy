"""
Weavy CLI — entry point for operational commands.
Run as: python -m weavy.cli <command>
"""

import argparse
import sys
from datetime import datetime

from weavy.models.tools import ListSessionsInput
from weavy.store.canonical import list_sessions
from weavy.store.client import get_graph
from weavy.store.system import (
    SystemState,
    get_system,
    init_system,
    set_preface,
)


def _print_system_state(header: str, state: SystemState) -> None:
    print(f"{header}:")
    print(f"  preface               = {state.preface or '(not set)'}")
    print(f"  next_node_id          = {state.next_node_id}")
    print(f"  next_edge_id          = {state.next_edge_id}")
    print(f"  next_session_id       = {state.next_session_id}")
    print(f"  hot_theme_token_budget = {state.hot_theme_token_budget}")
    print(f"  theme_priority_order  = {state.theme_priority_order}")
    print(f"  last_theme_run_at     = {state.last_theme_run_at}")


def cmd_init_system(_args: argparse.Namespace) -> None:
    from weavy.services.embedding import get_dimension

    graph = get_graph()
    state = init_system(graph, embedding_dim=get_dimension())
    _print_system_state("System node initialised", state)


def cmd_status(_args: argparse.Namespace) -> None:
    graph = get_graph()
    state = get_system(graph)
    _print_system_state("System state", state)


def cmd_list_sessions(args: argparse.Namespace) -> None:
    graph = get_graph()
    output = list_sessions(graph, ListSessionsInput(limit=args.limit))
    if not output.sessions:
        print("No sessions found.")
        return
    for s in output.sessions:
        summary_line = f"  {s.summary}" if s.summary else "  (not yet ingested)"
        print(f"  {s.id}  {s.timestamp.isoformat()}{summary_line}")


def cmd_add(args: argparse.Namespace) -> None:
    from weavy.modes.session import run_add

    if args.source == "-":
        text = sys.stdin.read()
    else:
        with open(args.source) as f:
            text = f.read()

    if not text.strip():
        print("Error: empty input.", file=sys.stderr)
        sys.exit(1)

    timestamp = None
    if args.timestamp:
        timestamp = datetime.fromisoformat(args.timestamp)

    trace = run_add(text, timestamp=timestamp, context=args.context)
    print(f"Status: {trace.status}")
    if trace.error:
        print(f"Error: {trace.error}", file=sys.stderr)
    else:
        touched = list(dict.fromkeys(n.node_id for n in trace.touched_nodes))
        summary = (trace.completion_payload or {}).get("summary", "")
        print(f"Touched nodes: {touched}")
        print(f"Summary: {summary}")


def cmd_update_themes(_args: argparse.Namespace) -> None:
    from weavy.modes.theme import run_theme_update

    trace = run_theme_update()
    print(f"Status: {trace.status}")
    if trace.error:
        print(f"Error: {trace.error}", file=sys.stderr)
    else:
        print("Theme update complete.")


def cmd_set_preface(args: argparse.Namespace) -> None:
    graph = get_graph()
    set_preface(graph, args.preface)
    print(f"Preface set: {args.preface}")


def cmd_continue(args: argparse.Namespace) -> None:
    from weavy.modes.session import run_session

    trace = run_session(args.session_id, "query", args.question)
    print(f"Status: {trace.status}")
    if trace.error:
        print(f"Error: {trace.error}", file=sys.stderr)
    else:
        answer = (trace.completion_payload or {}).get("answer", "")
        print(f"\n{answer}")


def cmd_query(args: argparse.Namespace) -> None:
    if args.question is None:
        from weavy.modes.session import run_chat_repl

        run_chat_repl()
        return

    from weavy.modes.session import run_query

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

    p = subparsers.add_parser("list-sessions", help="List stored sessions")
    p.add_argument("--limit", type=int, default=20)

    p = subparsers.add_parser("add", help="Add text to the memory graph")
    p.add_argument(
        "source",
        help="Path to a text file, or '-' to read from stdin",
    )
    p.add_argument("--context", default=None, help="Caller context for the ingestion agent")
    p.add_argument("--timestamp", default=None, help="ISO timestamp for the session")

    subparsers.add_parser(
        "update-themes", help="Manually run the theme agent over the current graph"
    )

    p = subparsers.add_parser(
        "set-preface", help="Set the graph preface describing what this graph is about"
    )
    p.add_argument(
        "preface",
        help="Description of this graph (e.g. 'Personal memory graph for Shivang')",
    )

    p = subparsers.add_parser(
        "continue", help="Continue an existing session with a new question"
    )
    p.add_argument("session_id", help="Session to continue (e.g. s:1)")
    p.add_argument("question", help="Question to ask in the context of that session")

    p = subparsers.add_parser("query", help="Ask a question against the memory graph")
    p.add_argument(
        "question",
        nargs="?",
        default=None,
        help="Question to ask. Omit to enter interactive chat.",
    )

    args = parser.parse_args()
    dispatch = {
        "init-system": cmd_init_system,
        "status": cmd_status,
        "list-sessions": cmd_list_sessions,
        "add": cmd_add,
        "continue": cmd_continue,
        "update-themes": cmd_update_themes,
        "set-preface": cmd_set_preface,
        "query": cmd_query,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
