from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from falkordb import Graph

from weavy.application.prompts import build_themed_system_prompt
from weavy.harness.actions import SESSION_ACTIONS
from weavy.harness.runner import run
from weavy.models.canonical import ChatMessage, Session
from weavy.models.traces import RunTrace, graph_changes as _graph_changes
from weavy.store import canonical as store_canonical
from weavy.store import system as store_system
from weavy.store.client import get_graph


def create_session(
    text: str,
    timestamp: datetime | None = None,
    *,
    graph: Graph | None = None,
) -> str:
    active_graph = graph or get_graph()
    session_id = store_system.increment_counter(active_graph, "session")
    ts = timestamp or datetime.now(tz=timezone.utc)
    messages = [ChatMessage(role="user", content=text)] if text else []
    store_canonical.create_session(
        active_graph, Session(id=session_id, timestamp=ts, messages=messages)
    )
    return session_id


def _merge_graph_changes(existing: dict, new: dict) -> dict:
    merged = dict(existing)
    for key, ids in new.items():
        merged[key] = list(dict.fromkeys([*merged.get(key, []), *ids]))
    return merged


def finalize_session(
    graph: Graph,
    session_id: str,
    trace: RunTrace,
) -> RunTrace:
    if trace.status != "completed":
        return trace

    if trace.conversation is not None:
        store_canonical.update_messages(graph, session_id, trace.conversation)

    summary = (trace.completion_payload or {}).get("summary", "")
    completed_at = datetime.now(tz=timezone.utc).isoformat()
    new_changes = _graph_changes(trace.touched_nodes, trace.touched_edges)
    existing_changes = store_canonical.get_session_graph_changes(graph, session_id)
    merged_changes = _merge_graph_changes(existing_changes, new_changes)
    store_canonical.persist_session_outcomes(
        graph, session_id, summary, merged_changes, completed_at
    )
    return trace


def run_session(
    session_id: str,
    mode: Literal["ingestion", "query"],
    append_message: str | None = None,
    parent_observation: Any = None,
    caller_context: str | None = None,
) -> RunTrace:
    graph = get_graph()
    if mode == "ingestion":
        store_canonical.get_session(graph, session_id, check_completed=True)
    system_state = store_system.get_system(graph)

    initial_messages = store_canonical.load_messages(graph, session_id)
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
    return finalize_session(graph, session_id, trace)


def run_add(
    text: str,
    timestamp: datetime | None = None,
    context: str | None = None,
) -> RunTrace:
    graph = get_graph()
    session_id = create_session(text, timestamp, graph=graph)
    return run_session(session_id, "ingestion", caller_context=context)


def run_ingest(session_id: str) -> RunTrace:
    return run_session(session_id, "ingestion")


def run_query(question: str, context: str | None = None) -> RunTrace:
    graph = get_graph()
    session_id = create_session("", graph=graph)
    return run_session(session_id, "query", question, caller_context=context)
