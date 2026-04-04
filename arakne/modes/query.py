"""
Query/chat mode — grounded retrieval and conversational graph mutation.
Implemented in Phase 7.
"""

from datetime import datetime, timezone

from arakne.config import settings
from arakne.harness import registry as reg
from arakne.harness.runner import run
from arakne.harness.tracing import save_trace
from arakne.models.canonical import ChatMessage, ChatSession
from arakne.models.traces import RunTrace
from arakne.modes import theme as theme_mode
from arakne.store import canonical as store_canonical
from arakne.store import graph as store_graph
from arakne.store import system as store_system
from arakne.store import themes as store_themes
from arakne.store.client import get_graph

_QUERY_SYSTEM_PROMPT_TEMPLATE = """\
You are a query agent retrieving grounded answers from a personal memory graph.

Current time: {current_time}
Your chat session ID for this run: {chat_id}

{themes_context}

Your task:
1. ORIENT — the hot themes above are your starting map. Start there before searching.
2. NAVIGATE — use search_graph, get_node_neighborhood, get_node to explore the semantic graph.
3. GROUND — trace back to canonical sources via get_transcript_span or get_chat to retrieve \
exact evidence. Do not answer from graph summaries alone.
4. RESPOND — call deliver_response with your answer, the canonical source spans that ground it, \
and the node ids you consulted.

If the user provides corrections or new context during this conversation, you may update the \
graph using the write tools. All graph writes must use provenance source_id: {chat_id}.

Rules:
- cited_sources in deliver_response must reference rec:N or chat:N spans, not graph node ids.
- For transcript citations, provide start_offset and end_offset as seconds into the recording.
- For chat citations, provide start_offset as the message index and end_offset as null.
- If you are uncertain, say so clearly. Do not fabricate citations.
- Terminate only via deliver_response — do not stop without calling it.\
"""


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

    all_themes = store_themes.list_all_themes(graph)
    try:
        hot_block, cold_names = store_themes.render_hot_themes(
            all_themes,
            system_state.theme_priority_order,
            system_state.hot_theme_token_budget,
        )
    except ValueError:
        hot_block = ""
        cold_names = [t.name for t in all_themes]

    if hot_block:
        cold_index = ("\n\nOther themes: " + ", ".join(cold_names)) if cold_names else ""
        themes_context = hot_block + cold_index
    elif cold_names:
        themes_context = "Themes (no hot set rendered): " + ", ".join(cold_names)
    else:
        themes_context = "(No themes yet — start with search_graph or list_transcripts.)"

    current_time = datetime.now(tz=timezone.utc).strftime("%A %d %b %Y, %I:%M %p UTC")
    system_prompt = _QUERY_SYSTEM_PROMPT_TEMPLATE.format(
        current_time=current_time,
        chat_id=chat_id,
        themes_context=themes_context,
    )

    trace = run(
        mode="query",
        system_prompt=system_prompt,
        initial_messages=[
            *(prior_messages or []),
            {"role": "user", "content": question},
        ],
        allowed_tools=reg.QUERY_TOOLS,
        completion_tool="deliver_response",
        run_context={"input_summary": f"Query: {question[:80]}"},
        graph=graph,
    )

    # Persist canonical ChatSession with the conversation from this run
    if persist_chat and trace.conversation:
        messages = [
            ChatMessage(role=m["role"], content=m.get("content") or "")
            for m in trace.conversation
            if m["role"] in ("user", "assistant") and m.get("content")
        ]
        store_canonical.create_chat_session(
            graph,
            ChatSession(
                id=chat_id,
                timestamp=trace.started_at,
                messages=messages,
            ),
        )

    save_trace(trace, "runs")

    # Post-run: fence checks + theme update (only when graph writes occurred)
    if trace.status == "completed" and trace.touched_nodes:
        live_node_ids = [n.node_id for n in trace.touched_nodes if n.action != "deleted"]
        if live_node_ids:
            store_graph.run_fence_checks(
                graph,
                live_node_ids,
                system_state.log_token_budget,
                settings.GEMINI_MODEL,
            )

        answer = (trace.completion_payload or {}).get("answer", "")
        theme_mode.run_theme_update(answer, trace.touched_nodes, trace.touched_edges)

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
        messages = [
            ChatMessage(role=m["role"], content=m.get("content") or "")
            for m in conversation
            if m["role"] in ("user", "assistant") and m.get("content")
        ]
        if messages:
            store_canonical.create_chat_session(
                graph,
                ChatSession(
                    id=chat_id,
                    timestamp=datetime.now(tz=timezone.utc),
                    messages=messages,
                ),
            )
