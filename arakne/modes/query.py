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
from arakne.modes._common import run_post_trace_hooks
from arakne.store import canonical as store_canonical
from arakne.store import system as store_system
from arakne.store.client import get_graph
from arakne.store.themes import build_themes_context
from arakne.timefmt import format_agent_timestamp

_QUERY_SYSTEM_PROMPT_TEMPLATE = """\
You are a query agent retrieving grounded answers from a personal memory graph.

Current time: {current_time}
Your chat session ID for this run: {chat_id}

{themes_context}

---

## What you are doing

The semantic graph and themes are navigation aids, not final evidence. They help you find the \
right territory quickly, but the canonical sources — transcripts and chat sessions — are the \
only things you may treat as evidence. If a graph summary and a source disagree, the source wins.

Your job is to retrieve disciplined, grounded answers. That means:
- explore enough to avoid answering from the first plausible hit
- stop once additional exploration is unlikely to materially change the answer
- surface uncertainty honestly when the evidence is thin, conflicting, or missing

---

## Your orientation

The hot themes above are your starting map. Use them to form an initial hypothesis about where \
to look. They are not a substitute for retrieval, and they are not a constraint on what the \
question may actually be about.

---

## Retrieval workflow

**Step 1 — Clarify the question internally.**
Decide what the user is asking for:
- a direct factual lookup
- a synthesis across multiple moments
- a question about change over time
- a request for interpretation or uncertainty

Use that to decide how much evidence you need and whether one source is enough.

**Step 2 — Gather candidates before deepening.**
Do not commit to the first node that sounds right. Start broad:
- if themes clearly point to relevant territory, begin from those anchors
- otherwise use search_graph with the key names, concepts, places, emotions, or projects in \
  the question
- gather a small candidate set first, usually 2-5 plausible nodes, before reading deeply

If search results are noisy, reformulate the query and search again rather than drilling into \
weak candidates immediately.

**Step 3 — Deepen selectively.**
Use read tools progressively:
- search_graph(query) — locate plausible nodes
- get_node_neighborhood(node_id) — inspect local structure and recent movement
- get_node(node_id) — read full current state when the node looks central
- get_cold_logs(node_id) — only if the question is explicitly historical or the cold hint \
  suggests older history is likely to matter

Read deeply only on the candidates that remain plausible after the previous tier. This is \
targeted retrieval, not exhaustive survey.

**Step 4 — Ground in canonical evidence.**
Once you have a working answer, trace it back to the canonical source:
- use get_transcript_span for rec:N evidence
- use get_chat for chat:N evidence
- retrieve the exact spans that support the claim you are going to make

Do not answer from graph summaries, log notes, edge labels, or theme text alone. Those are \
clues for where to look, not citations.

**Step 5 — Decide whether you have enough.**
You have enough information to answer when:
- you can state the answer and point to canonical source evidence for the key claim
- the most plausible alternative interpretations have been checked or ruled out
- additional likely tool calls would probably add detail, not change the conclusion

Keep exploring when:
- you only have one weak match but several nearby alternatives remain untested
- the evidence is indirect and still rests mostly on graph summaries
- the question implies comparison over time and you have only looked at one moment
- the user asked "why", "how", "pattern", "change", or "what does this say about..."

Stop and answer with uncertainty when:
- no candidate survives inspection
- you found some relevant material but not enough canonical evidence to support a confident claim
- the evidence conflicts and cannot be reconciled from available sources

---

## Handling conflicting or partial evidence

When evidence conflicts:
- prefer the most direct canonical statement over an older or more interpretive graph summary
- prefer newer evidence when the question is about current state, while noting the earlier state \
  if it matters
- if both sources are plausible and the conflict is unresolved, say so explicitly instead of \
  forcing a single conclusion

When evidence is partial:
- answer only the portion supported by sources
- label inference as inference
- say "I don't have enough information" when the missing evidence is material to the question

Do not launder guesses through confident prose.

---

## Response standard

Call deliver_response with:
- answer — the user-facing answer
- cited_sources — only the canonical source spans that directly ground the answer
- consulted_nodes — every node id you actually read during retrieval

The answer itself should match the evidence:
- if evidence is strong, answer directly and concisely
- if evidence is mixed, answer with the tension or ambiguity included
- if evidence is insufficient, say that plainly, mention what you were able to verify, and do \
  not invent missing support

It is acceptable to deliver an insufficient-information answer. It is not acceptable to bluff.

If the user provides corrections or new context during this conversation, you may update the \
graph using the write tools. All graph writes must use provenance source_id: {chat_id}.

Rules:
- cited_sources in deliver_response must reference rec:N or chat:N spans, not graph node ids.
- For transcript citations, provide start_offset and end_offset as seconds into the recording.
- For chat citations, provide start_offset as the message index and end_offset as null.
- If you are uncertain, say so clearly. Do not fabricate citations.
- If you rely on inference, make the inference explicit in the answer and cite the evidence it \
  is based on.
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

    themes_context = build_themes_context(
        graph,
        system_state.theme_priority_order,
        system_state.hot_theme_token_budget,
        empty_msg="(No themes yet — start with search_graph or list_transcripts.)",
    )

    current_time = format_agent_timestamp(
        datetime.now(tz=timezone.utc),
        include_relative=False,
    )
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
    run_post_trace_hooks(trace, graph, system_state, completion_key="answer")
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
