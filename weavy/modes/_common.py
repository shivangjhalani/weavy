"""
Shared helpers for mode orchestration.
"""

from datetime import datetime, timezone

from falkordb import Graph

from weavy.config import settings
from weavy.models.canonical import ChatMessage
from weavy.models.traces import RunTrace
from weavy.store import graph as store_graph
from weavy.store.system import SystemState
from weavy.store.themes import build_themes_context
from weavy.timefmt import format_agent_timestamp


def _unique_live_node_ids(trace: RunTrace) -> list[str]:
    seen: set[str] = set()
    live_node_ids: list[str] = []
    for node in trace.touched_nodes:
        if node.action == "deleted" or node.node_id in seen:
            continue
        seen.add(node.node_id)
        live_node_ids.append(node.node_id)
    return live_node_ids


def fetch_prompt(name: str, variables: dict) -> str:
    """Fetch a versioned prompt from Langfuse and compile it with the given variables.

    Raises on any failure — no silent fallback. Langfuse must be running.
    """
    from weavy.langfuse_client import get_langfuse

    prompt = get_langfuse().get_prompt(name, label="production")
    return prompt.compile(**variables)


def build_themed_system_prompt(
    prompt_name: str,
    graph: Graph,
    system_state: SystemState,
    empty_themes_message: str,
    variables: dict | None = None,
) -> str:
    """Build a prompt with the shared time and hot-themes context."""
    prompt_variables = dict(variables or {})
    prompt_variables.update(
        current_time=format_agent_timestamp(
            datetime.now(tz=timezone.utc),
            include_relative=False,
        ),
        themes_context=build_themes_context(
            graph,
            system_state.theme_priority_order,
            system_state.hot_theme_token_budget,
            empty_msg=empty_themes_message,
        ),
    )
    return fetch_prompt(prompt_name, prompt_variables)


def conversation_to_chat_messages(conversation: list[dict]) -> list[ChatMessage]:
    """Convert stored harness messages into persisted chat messages."""
    return [
        ChatMessage(role=message["role"], content=message.get("content") or "")
        for message in conversation
        if message["role"] in ("user", "assistant") and message.get("content")
    ]


def run_post_trace_hooks(
    trace: RunTrace,
    graph: Graph,
    system_state: SystemState,
    completion_text: str,
) -> None:
    """Run fence checks and trigger a theme update after a completed session."""
    if not (trace.status == "completed" and trace.touched_nodes):
        return

    live_node_ids = _unique_live_node_ids(trace)
    if live_node_ids:
        store_graph.run_fence_checks(
            graph, live_node_ids, system_state.log_token_budget, settings.GEMINI_MODEL
        )

    from weavy.modes import theme as theme_mode  # local import avoids circular dep

    theme_mode.run_theme_update(completion_text, trace.touched_nodes, trace.touched_edges)
