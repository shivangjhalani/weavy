from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from falkordb import Graph

from weavy.models.canonical import ChatMessage
from weavy.models.traces import RunTrace, graph_changes as _graph_changes
from weavy.store import canonical as store_canonical
from weavy.store import system as store_system
from weavy.store.themes import build_themes_context


@lru_cache(maxsize=None)
def _load_prompt_template(name: str) -> str:
    prompts_dir = Path(__file__).parent.parent / "prompts"
    for suffix in (".md", ".txt"):
        path = prompts_dir / f"{name}{suffix}"
        try:
            return path.read_text()
        except (FileNotFoundError, OSError):
            continue
    raise FileNotFoundError(
        f"No prompt template {name!r} (.md or .txt) in {prompts_dir}"
    )


def fetch_prompt(name: str, variables: dict[str, object]) -> str:
    template = _load_prompt_template(name)
    for key, value in variables.items():
        template = template.replace("{{" + key + "}}", str(value))
    return template


def build_themed_system_prompt(
    prompt_name: str,
    graph: Graph,
    system_state: store_system.SystemState,
    empty_themes_message: str,
    variables: dict[str, object] | None = None,
    current_time: str | None = None,
    caller_context: str | None = None,
) -> str:
    prompt_variables = dict(variables or {})
    prompt_variables["current_time"] = (
        current_time or datetime.now(tz=timezone.utc).isoformat()
    )
    prompt_variables["preface"] = (
        system_state.preface or "(not set — call set_preface to describe this graph)"
    )
    prompt_variables["themes_context"] = build_themes_context(
        graph,
        system_state.theme_priority_order,
        system_state.hot_theme_token_budget,
        empty_msg=empty_themes_message,
    )
    prompt_variables["caller_context"] = (
        f"- **Caller context:** {caller_context}" if caller_context else ""
    )
    return fetch_prompt(prompt_name, prompt_variables)


def _merge_graph_changes(existing: dict, new: dict) -> dict:
    """Accumulate graph changes across multiple runs on the same session."""
    merged = dict(existing)
    for key, ids in new.items():
        if key in merged:
            seen = set(merged[key])
            merged[key] = merged[key] + [i for i in ids if i not in seen]
        else:
            merged[key] = list(ids)
    return merged


def finalize_session(
    graph: Graph,
    session_id: str,
    trace: RunTrace,
    messages: list[ChatMessage] | None = None,
) -> RunTrace:
    """Write session outcomes after a completed agent run."""
    if trace.status != "completed":
        return trace

    if messages:
        store_canonical.update_session_messages(graph, session_id, messages)

    if trace.conversation_raw:
        store_canonical.update_session_raw_messages(graph, session_id, trace.conversation_raw)

    summary = (trace.completion_payload or {}).get("summary", "")
    completed_at = datetime.now(tz=timezone.utc).isoformat()
    new_changes = _graph_changes(trace.touched_nodes, trace.touched_edges)
    existing_changes = store_canonical.get_session_graph_changes(graph, session_id)
    merged_changes = _merge_graph_changes(existing_changes, new_changes)
    store_canonical.persist_session_outcomes(
        graph, session_id, summary, merged_changes, completed_at
    )
    return trace


def finalize_theme(graph: Graph, trace: RunTrace) -> RunTrace:
    if trace.status != "completed":
        return trace

    priority_order = (trace.completion_payload or {}).get("priority_order")
    if priority_order is not None:
        store_system.update_theme_priority_order(graph, priority_order)

    store_system.update_last_theme_run_at(
        graph, datetime.now(tz=timezone.utc).isoformat()
    )
    return trace
