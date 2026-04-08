from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from falkordb import Graph

from weavy.models.canonical import ChatMessage, ChatSession
from weavy.models.traces import RunTrace
from weavy.store import canonical as store_canonical
from weavy.store import system as store_system
from weavy.store.themes import build_themes_context
from weavy.timefmt import format_agent_timestamp


def fetch_prompt(name: str, variables: dict[str, object]) -> str:
    prompt_path = Path(__file__).parent.parent / "prompts" / f"{name}.txt"
    template = prompt_path.read_text()
    for key, value in variables.items():
        template = template.replace("{{" + key + "}}", str(value))
    return template


def build_themed_system_prompt(
    prompt_name: str,
    graph: Graph,
    system_state: store_system.SystemState,
    empty_themes_message: str,
    variables: dict[str, object] | None = None,
) -> str:
    prompt_variables = dict(variables or {})
    prompt_variables["current_time"] = format_agent_timestamp(
        datetime.now(tz=timezone.utc),
        include_relative=False,
    )
    prompt_variables["themes_context"] = build_themes_context(
        graph,
        system_state.theme_priority_order,
        system_state.hot_theme_token_budget,
        empty_msg=empty_themes_message,
    )
    return fetch_prompt(prompt_name, prompt_variables)


def conversation_to_chat_messages(conversation: list[dict]) -> list[ChatMessage]:
    return [
        ChatMessage(role=message["role"], content=message["content"])
        for message in conversation
        if message["role"] in ("user", "assistant") and message.get("content")
    ]


def run_theme_update_if_needed(graph: Graph, trace: RunTrace, completion_text: str) -> None:
    if trace.status != "completed":
        return
    if not trace.touched_nodes and not trace.touched_edges:
        return

    from weavy.modes.theme import run_theme_update

    run_theme_update(completion_text, trace.touched_nodes, trace.touched_edges)


def finalize_ingestion(graph: Graph, transcript_id: str, trace: RunTrace) -> RunTrace:
    if trace.status == "completed":
        store_canonical.set_ingestion_state(graph, transcript_id, "completed")
        run_theme_update_if_needed(
            graph,
            trace,
            (trace.completion_payload or {}).get("summary", ""),
        )
        return trace

    store_canonical.set_ingestion_state(graph, transcript_id, "failed")
    return trace


def finalize_query(
    graph: Graph,
    chat_id: str,
    trace: RunTrace,
    *,
    persist_chat: bool,
) -> RunTrace:
    if persist_chat and trace.conversation:
        messages = conversation_to_chat_messages(trace.conversation)
        if messages:
            store_canonical.create_chat_session(
                graph,
                ChatSession(
                    id=chat_id,
                    timestamp=trace.started_at,
                    messages=messages,
                ),
            )

    run_theme_update_if_needed(
        graph,
        trace,
        (trace.completion_payload or {}).get("answer", ""),
    )
    return trace


def finalize_theme(graph: Graph, trace: RunTrace) -> RunTrace:
    if trace.status != "completed":
        return trace

    priority_order = (trace.completion_payload or {}).get("priority_order")
    if priority_order is not None:
        store_system.update_theme_priority_order(graph, priority_order)
    return trace
