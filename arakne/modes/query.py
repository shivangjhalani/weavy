"""
Query/chat mode — grounded retrieval and conversational graph mutation.
"""

from datetime import datetime, timezone

from arakne.config import settings
from arakne.harness import registry as reg
from arakne.harness.runner import run
from arakne.models.canonical import ChatSession
from arakne.models.traces import RunTrace
from arakne.modes._common import (
    build_themed_system_prompt,
    conversation_to_chat_messages,
    run_post_trace_hooks,
)
from arakne.store import canonical as store_canonical
from arakne.store import system as store_system
from arakne.store.client import get_graph


def run_query(
    question: str,
    prior_messages: list[dict] | None = None,
    chat_id: str | None = None,
    persist_chat: bool = True,
) -> RunTrace:
    """Run a query/chat session. Returns the completed RunTrace."""
    graph = get_graph(settings.GRAPH_NAME)
    system_state = store_system.get_system(graph)

    if chat_id is None:
        chat_id = store_system.increment_counter(graph, "chat")

    system_prompt = build_themed_system_prompt(
        "arakne-query",
        graph,
        system_state,
        empty_themes_message="(No themes yet — start with search_graph or list_transcripts.)",
        variables={"chat_id": chat_id},
    )

    trace = run(
        mode="query",
        system_prompt=system_prompt,
        initial_messages=[
            *(prior_messages or []),
            {"role": "user", "content": question},
        ],
        allowed_tools=reg.QUERY_TOOLS,
        run_context={"input_summary": f"Query: {question[:80]}"},
        graph=graph,
        session_id=chat_id,
    )

    if persist_chat and trace.conversation:
        messages = conversation_to_chat_messages(trace.conversation)
        store_canonical.create_chat_session(
            graph,
            ChatSession(
                id=chat_id,
                timestamp=trace.started_at,
                messages=messages,
            ),
        )

    run_post_trace_hooks(
        trace,
        graph,
        system_state,
        completion_text=(trace.completion_payload or {}).get("answer", ""),
    )
    return trace


def run_chat_repl() -> None:
    """Interactive REPL: prompts user, runs query turns with full history.
    Persists a single ChatSession on exit."""
    graph = get_graph(settings.GRAPH_NAME)
    chat_id = store_system.increment_counter(graph, "chat")
    conversation: list[dict] = []

    print("Arakne chat — type 'exit' or Ctrl-D to quit.\n")
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

        trace = run_query(
            question,
            prior_messages=conversation if conversation else None,
            chat_id=chat_id,
            persist_chat=False,
        )

        if trace.status == "failed":
            print(f"[error] {trace.error}\n")
            continue

        answer = (trace.completion_payload or {}).get("answer", "")
        print(f"\nArakne: {answer}\n")

        if trace.conversation:
            conversation = trace.conversation

    if conversation:
        messages = conversation_to_chat_messages(conversation)
        if messages:
            store_canonical.create_chat_session(
                graph,
                ChatSession(
                    id=chat_id,
                    timestamp=datetime.now(tz=timezone.utc),
                    messages=messages,
                ),
            )
