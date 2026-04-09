"""
Theme mode — self-discovering theme map maintenance.
"""

from weavy.harness.actions import THEME_ACTIONS
from weavy.harness.runner import run
from weavy.models.traces import RunTrace
from weavy.services.workflow import fetch_prompt, finalize_theme
from weavy.store import canonical as store_canonical
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


def _render_journal(sessions: list) -> str:
    lines = [f"Sessions since your last run ({len(sessions)}):\n"]
    for i, s in enumerate(sessions, 1):
        changes = s.graph_changes
        change_parts = []
        for action in ("created", "updated", "deleted"):
            node_ids = changes.get(f"nodes_{action}", [])
            edge_ids = changes.get(f"edges_{action}", [])
            if node_ids:
                change_parts.append(f"{action} {', '.join(node_ids)}")
            if edge_ids:
                change_parts.append(f"{action} edges {', '.join(edge_ids)}")
        change_text = "; ".join(change_parts) if change_parts else "no graph changes"
        lines.append(f'{i}. {s.id}: "{s.summary}" — {change_text}')
    return "\n".join(lines)


def run_theme_update() -> RunTrace:
    """Update themes. Self-discovers what changed since last run."""
    graph = get_graph()
    system_state = store_system.get_system(graph)
    all_themes = store_themes.list_all_themes(graph)

    theme_map_text = _render_full_theme_map(
        all_themes, system_state.theme_priority_order
    )
    system_prompt = fetch_prompt(
        "weavy-theme",
        {
            "theme_map": theme_map_text,
            "preface": system_state.preface or "(not set)",
        },
    )

    sessions = store_canonical.get_sessions_since(graph, system_state.last_theme_run_at)

    if sessions:
        user_content = _render_journal(sessions)
    else:
        user_content = (
            "No new sessions since your last run. "
            "Review existing themes for coherence and priority."
        )

    trace = run(
        mode="theme",
        system_prompt=system_prompt,
        initial_messages=[{"role": "user", "content": user_content}],
        allowed_actions=THEME_ACTIONS,
        run_context={"input_summary": f"Theme update ({len(sessions)} sessions)"},
        graph=graph,
    )
    return finalize_theme(graph, trace)
