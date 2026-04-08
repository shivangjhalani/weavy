"""
Query/chat mode — grounded retrieval and conversational graph mutation.
"""

from weavy.config import settings
from weavy.harness.actions import QUERY_ACTIONS
from weavy.harness.runner import run
from weavy.harness.tracing import ChatSessionTracer
from weavy.models.traces import RunTrace
from weavy.services.workflow import build_themed_system_prompt, finalize_query
from weavy.store import system as store_system
from weavy.store.client import get_graph


def run_query(
    question: str,
    prior_messages: list[dict] | None = None,
    chat_id: str | None = None,
    persist_chat: bool = True,
    parent_observation: object | None = None,
) -> RunTrace:
    """Run a query/chat session. Returns the completed RunTrace."""
    graph = get_graph(settings.GRAPH_NAME)
    system_state = store_system.get_system(graph)

    if chat_id is None:
        chat_id = store_system.increment_counter(graph, "chat")

    system_prompt = build_themed_system_prompt(
        "weavy-query",
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
        allowed_actions=QUERY_ACTIONS,
        run_context={"input_summary": f"Query: {question[:80]}"},
        graph=graph,
        session_id=chat_id,
        parent_observation=parent_observation,
    )

    return finalize_query(graph, chat_id, trace, persist_chat=persist_chat)


def run_chat_repl() -> None:
    """Interactive REPL: prompts user, runs query turns with full history.
    Persists a single ChatSession on exit."""
    graph = get_graph(settings.GRAPH_NAME)
    chat_id = store_system.increment_counter(graph, "chat")
    conversation: list[dict] = []
    session_tracer = ChatSessionTracer(chat_id)
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
        trace = run_query(
            question,
            prior_messages=conversation if conversation else None,
            chat_id=chat_id,
            persist_chat=False,
            parent_observation=session_tracer.root,
        )

        if trace.status == "failed":
            print(f"[error] {trace.error}\n")
            continue

        answer = (trace.completion_payload or {}).get("answer", "")
        print(f"\nWeavy: {answer}\n")

        if trace.conversation:
            conversation = trace.conversation

    session_tracer.finalize(message_count)
