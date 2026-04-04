"""
Theme mode — delta-driven theme map maintenance.
Implemented in Phase 6.
"""

from arakne.config import settings
from arakne.harness import registry as reg
from arakne.harness.runner import run
from arakne.harness.tracing import save_trace
from arakne.models.traces import RunTrace, TouchedEdge, TouchedNode
from arakne.store import system as store_system
from arakne.store import themes as store_themes
from arakne.store.client import get_graph

_THEME_SYSTEM_PROMPT_TEMPLATE = """\
You are maintaining a theme map for a personal journaling memory system.

Themes are lightweight orientation documents — each has a name, a 1-2 sentence state \
summary, status labels (deep | active | emerging | dormant), and anchor node IDs that \
link into the semantic graph.

{theme_map}

You will receive a delta from the preceding session (what just changed in the semantic \
graph). Your job is narrow: given what just changed, update only what needs updating. \
Do not rewrite themes that were not touched.

Decision flow:
1. Check if touched nodes belong to existing themes (match against anchor lists). \
If yes — read those nodes, update the theme state if needed.
2. Check if newly created nodes do not belong to any theme. If yes — read their \
neighborhoods and decide: new theme or extend an existing theme's anchors?
3. Check if any status labels feel wrong given the update. Adjust.
4. Decide the new priority order for ALL themes (most important / most recently active first).

Rules:
- Make targeted updates only. If only one theme was affected, only change that theme.
- When creating a theme, pick a short kebab-case name (e.g. "career-direction").
- Anchors are node IDs (e.g. node:4) — direct entry points into the semantic graph.
- Status is your editorial judgment — not mechanical. Consider depth, recency, and maturity.
- Status values: deep | active | emerging | dormant (1-2 values per theme).

End with complete_theme_update(updated_themes, priority_order) where priority_order is \
the COMPLETE ordered list of all active theme names.\
"""


def _render_full_theme_map(themes: list, priority_order: list[str]) -> str:
    if not themes:
        return "CURRENT THEME MAP: (empty — no themes yet)\n"

    lines = ["CURRENT THEME MAP:\n"]
    for theme in themes:
        status_str = ", ".join(theme.status)
        anchors_str = ", ".join(theme.anchors) if theme.anchors else "none"
        lines.append(f"{theme.name} [{status_str}]\n{theme.state}\n\u2192 {anchors_str}\n")
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
    system_prompt = _THEME_SYSTEM_PROMPT_TEMPLATE.format(theme_map=theme_map_text)

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

    save_trace(trace, "runs")
    return trace
