"""
Unified session mode — ingestion, queries, and interactive chat.
All paths share the same agent loop; mode selects system prompt and behavior.
"""

from datetime import datetime, timezone
from typing import Any, Literal

from weavy.harness.actions import SESSION_ACTIONS
from weavy.harness.runner import run
from weavy.harness.tracing import ChatSessionTracer
from weavy.models.canonical import ChatMessage, Session
from weavy.models.traces import RunTrace
from weavy.services.workflow import build_themed_system_prompt, finalize_session
from weavy.store import canonical as store_canonical
from weavy.store import system as store_system
from weavy.store.client import get_graph


def run_session(
    session_id: str,
    mode: Literal["ingestion", "query"],
    append_message: str | None = None,
    parent_observation: Any = None,
    caller_context: str | None = None,
) -> RunTrace:
    """Run one agent turn on an existing session.

    For ingestion: session already contains the content; leave append_message=None.
    For query: pass the user's question as append_message (or None to use existing messages).
    caller_context is optional steering injected into the system prompt.
    """
    graph = get_graph()
    session = store_canonical.get_session(
        graph, session_id, check_completed=(mode == "ingestion")
    )
    system_state = store_system.get_system(graph)

    # Use full raw messages (with tool calls) if available — enables true chat continuity.
    # Fall back to text-only messages for new sessions.
    raw = store_canonical.get_session_raw_messages(graph, session_id)
    initial_messages: list = raw if raw is not None else [m.model_dump() for m in session.messages]
    if append_message:
        initial_messages.append({"role": "user", "content": append_message})

    system_prompt = build_themed_system_prompt(
        "weavy-ingestion" if mode == "ingestion" else "weavy-query",
        graph,
        system_state,
        empty_themes_message="(No themes yet — start with search_graph or list_sessions.)",
        variables={"session_id": session_id},
        caller_context=caller_context,
    )

    trace = run(
        mode=mode,
        system_prompt=system_prompt,
        initial_messages=initial_messages,
        allowed_actions=SESSION_ACTIONS,
        run_context={"input_summary": f"{mode}: {session_id}"},
        graph=graph,
        session_id=session_id,
        parent_observation=parent_observation,
    )

    messages = (
        [ChatMessage(**m) for m in trace.conversation] if trace.conversation else None
    )
    return finalize_session(graph, session_id, trace, messages)


def _create_session(
    graph, text: str, timestamp: datetime | None = None
) -> str:
    session_id = store_system.increment_counter(graph, "session")
    ts = timestamp or datetime.now(tz=timezone.utc)
    messages = [ChatMessage(role="user", content=text)] if text else []
    store_canonical.create_session(
        graph, Session(id=session_id, timestamp=ts, messages=messages)
    )
    return session_id


def run_add(
    text: str,
    timestamp: datetime | None = None,
    context: str | None = None,
) -> RunTrace:
    """Add new information to the memory layer.

    Creates a session with text as the first user message, runs the
    ingestion agent, and returns the trace.
    """
    graph = get_graph()
    session_id = _create_session(graph, text, timestamp)
    return run_session(session_id, "ingestion", caller_context=context)


def run_ingest(session_id: str) -> RunTrace:
    """Process an existing session through the ingestion agent."""
    return run_session(session_id, "ingestion")


def run_query(question: str, context: str | None = None) -> RunTrace:
    """Create a new query session and run the query agent."""
    graph = get_graph()
    session_id = _create_session(graph, "", None)
    return run_session(session_id, "query", question, caller_context=context)


def run_chat_repl() -> None:
    """Interactive REPL: each turn runs the query agent with full session history."""
    graph = get_graph()
    session_id = _create_session(graph, "", None)

    session_tracer = ChatSessionTracer(session_id)
    message_count = 0

    print("Weavy chat — type 'exit' or Ctrl-D to quit.\n")
    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question:
            continue
        if question.lower() in ("exit", "quit"):
            break

        message_count += 1
        trace = run_session(
            session_id, "query", question, parent_observation=session_tracer.root
        )

        if trace.status == "failed":
            print(f"[error] {trace.error}\n")
        else:
            answer = (trace.completion_payload or {}).get("answer", "")
            print(f"\nWeavy: {answer}\n")

    session_tracer.finalize(message_count)
