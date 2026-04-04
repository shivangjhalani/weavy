"""
Shared helpers for mode orchestration.
"""

from falkordb import Graph

from arakne.config import settings
from arakne.models.traces import RunTrace
from arakne.store import graph as store_graph
from arakne.store.system import SystemState


def run_post_trace_hooks(
    trace: RunTrace,
    graph: Graph,
    system_state: SystemState,
    completion_key: str,
) -> None:
    """Run fence checks and trigger a theme update after a completed session."""
    if not (trace.status == "completed" and trace.touched_nodes):
        return

    live_node_ids = [n.node_id for n in trace.touched_nodes if n.action != "deleted"]
    if live_node_ids:
        store_graph.run_fence_checks(
            graph, live_node_ids, system_state.log_token_budget, settings.GEMINI_MODEL
        )

    from arakne.modes import theme as theme_mode  # local import avoids circular dep

    payload_text = (trace.completion_payload or {}).get(completion_key, "")
    theme_mode.run_theme_update(payload_text, trace.touched_nodes, trace.touched_edges)
