"""
Unified session mode — ingestion, queries, and interactive chat.
All paths share the same agent loop; mode selects system prompt and behavior.
"""

from weavy.application import session_runs
from weavy.harness.tracing import ChatSessionTracer
run_session = session_runs.run_session
run_add = session_runs.run_add
run_ingest = session_runs.run_ingest
run_query = session_runs.run_query


def run_chat_repl() -> None:
    """Interactive REPL: each turn runs the query agent with full session history."""
    session_id = session_runs.create_session("")

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
        trace = session_runs.run_session(
            session_id, "query", question, parent_observation=session_tracer.root
        )

        if trace.status == "failed":
            print(f"[error] {trace.error}\n")
        else:
            answer = (trace.completion_payload or {}).get("answer", "")
            print(f"\nWeavy: {answer}\n")

    session_tracer.finalize(message_count)
