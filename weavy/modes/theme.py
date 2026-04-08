"""
Theme mode — delta-driven theme map maintenance.
"""

from weavy.config import settings
from weavy.harness.actions import THEME_ACTIONS
from weavy.harness.runner import run
from weavy.models.traces import RunTrace, TouchedEdge, TouchedNode
from weavy.services.workflow import fetch_prompt, finalize_theme
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
    summary: str = "",
    touched_nodes: list[TouchedNode] | None = None,
    touched_edges: list[TouchedEdge] | None = None,
) -> RunTrace:
    """Update themes. Can be triggered manually or after any session that writes nodes."""
    if touched_nodes is None:
        touched_nodes = []
    if touched_edges is None:
        touched_edges = []
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
        allowed_actions=THEME_ACTIONS,
        run_context={"input_summary": f"Theme update after: {summary[:80]}"},
        graph=graph,
    )
    return finalize_theme(graph, trace)
