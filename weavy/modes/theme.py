"""
Theme mode — delta-driven theme map maintenance.
"""

from weavy.config import settings
from weavy.harness import registry as reg
from weavy.harness.runner import run
from weavy.models.traces import RunTrace, TouchedEdge, TouchedNode
from weavy.modes._common import fetch_prompt
from weavy.store import system as store_system
from weavy.store import themes as store_themes
from weavy.store.client import get_graph


def _render_full_theme_map(themes: list, priority_order: list[str]) -> str:
    if not themes:
        return "CURRENT THEME MAP: (empty — no themes yet)\n"

    lines = ["CURRENT THEME MAP:\n"]
    for theme in themes:
        lines.append(f"{theme.render_block()}\n")
    lines.append(f"\nCurrent priority order: {priority_order}")
    return "\n".join(lines)


def run_theme_update(
    summary: str,
    touched_nodes: list[TouchedNode],
    touched_edges: list[TouchedEdge],
) -> RunTrace:
    """Update themes from a session delta. Triggered after ingestion or chat writes."""
    graph = get_graph(settings.GRAPH_NAME)
    all_themes = store_themes.list_all_themes(graph)
    system_state = store_system.get_system(graph)

    theme_map_text = _render_full_theme_map(all_themes, system_state.theme_priority_order)
    system_prompt = fetch_prompt("weavy-theme", {"theme_map": theme_map_text})

    touched_nodes_text = (
        "\n".join(f"  - {n.node_id} ({n.action})" for n in touched_nodes)
        if touched_nodes
        else "  (none)"
    )
    touched_edges_text = (
        "\n".join(f"  - {e.edge_id} ({e.action})" for e in touched_edges)
        if touched_edges
        else "  (none)"
    )
    delta_content = (
        f"Session summary: {summary}\n\n"
        f"Touched nodes:\n{touched_nodes_text}\n\n"
        f"Touched edges:\n{touched_edges_text}"
    )

    trace = run(
        mode="theme",
        system_prompt=system_prompt,
        initial_messages=[{"role": "user", "content": delta_content}],
        allowed_tools=reg.THEME_MODE_TOOLS,
        run_context={"input_summary": f"Theme update after: {summary[:80]}"},
        graph=graph,
    )

    if trace.status == "completed" and trace.completion_payload:
        priority_order = trace.completion_payload.get("priority_order", [])
        if priority_order is not None:
            store_system.update_theme_priority_order(graph, priority_order)

    return trace
