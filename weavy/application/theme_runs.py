from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from falkordb import Graph

from weavy.application.prompts import (
    fetch_prompt,
    render_full_theme_map,
    render_session_journal,
)
from weavy.harness.actions import THEME_ACTIONS
from weavy.harness.runner import run
from weavy.models.traces import RunTrace
from weavy.store import canonical as store_canonical
from weavy.store import system as store_system
from weavy.store import themes as store_themes


def finalize_theme(graph: Graph, trace: RunTrace) -> RunTrace:
    if trace.status != "completed":
        return trace

    _reconcile_priority(graph, (trace.completion_payload or {}).get("priority_order"))

    store_system.update_last_theme_run_at(
        graph, datetime.now(tz=timezone.utc).isoformat()
    )
    return trace


def _reconcile_priority(graph: Graph, agent_order: list[str] | None) -> None:
    """Project the agent's salience hint onto the real theme set, then persist it.

    The agent's ``priority_order`` is a *hint*, not authoritative state: we keep only
    names that correspond to real themes (in the agent's order), then append any theme
    the agent omitted (stable by current rank, then name). The result is written as a
    rank on each theme, so the stored order can never reference a theme that does not
    exist. This is the single point where the LLM's output meets ground truth.
    """
    themes = store_themes.list_all_themes(graph)  # ground truth
    if not themes:
        return

    seen: set[str] = set()
    existing = {t.name for t in themes}
    ordered = [
        name
        for name in (agent_order or [])
        if name in existing and not (name in seen or seen.add(name))
    ]
    leftovers = sorted(
        (t for t in themes if t.name not in seen), key=lambda t: (t.priority, t.name)
    )
    store_themes.set_theme_priority(graph, ordered + [t.name for t in leftovers])


def run_theme_update(
    graph: Graph,
    parent_observation: Any = None,
) -> RunTrace:
    system_state = store_system.get_system(graph)
    all_themes = store_themes.list_all_themes(graph)

    system_prompt = fetch_prompt(
        "weavy-theme",
        {
            "theme_map": render_full_theme_map(all_themes),
            "preface": system_state.preface or "(not set)",
        },
    )

    sessions = store_canonical.get_sessions_since(graph, system_state.last_theme_run_at)
    if sessions:
        user_content = render_session_journal(sessions)
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
        parent_observation=parent_observation,
    )
    return finalize_theme(graph, trace)
