"""
System node — singleton node in FalkorDB that holds global counters and config.
This is the only store module fully implemented in Phase 1.
"""

import json
from typing import Literal

from falkordb import Graph
from pydantic import BaseModel

from arakne.config import settings

CounterName = Literal["node", "edge", "rec", "chat"]

_COUNTER_FIELD: dict[CounterName, str] = {
    "node": "next_node_id",
    "edge": "next_edge_id",
    "rec": "next_rec_id",
    "chat": "next_chat_id",
}


class SystemState(BaseModel):
    next_node_id: int
    next_edge_id: int
    next_rec_id: int
    next_chat_id: int
    theme_priority_order: list[str]
    log_token_budget: int
    hot_theme_token_budget: int


def _row_to_state(props: dict) -> SystemState:
    # theme_priority_order may be stored as JSON string if FalkorDB serialised it
    priority = props.get("theme_priority_order", [])
    if isinstance(priority, str):
        priority = json.loads(priority)
    return SystemState(
        next_node_id=props["next_node_id"],
        next_edge_id=props["next_edge_id"],
        next_rec_id=props["next_rec_id"],
        next_chat_id=props["next_chat_id"],
        theme_priority_order=priority,
        log_token_budget=props["log_token_budget"],
        hot_theme_token_budget=props["hot_theme_token_budget"],
    )


def _ensure_vector_index(graph: Graph) -> None:
    try:
        graph.query(
            "CREATE VECTOR INDEX FOR (n:SemanticNode) ON (n.embedding) "
            "OPTIONS {dimension:3072, similarityFunction:'cosine'}"
        )
    except Exception:
        pass  # Index already exists


def init_system(graph: Graph) -> SystemState:
    """Create the System node if it does not exist; return current state."""
    result = graph.query(
        """
        MERGE (s:System)
        ON CREATE SET
            s.name = 'System',
            s.next_node_id = 1,
            s.next_edge_id = 1,
            s.next_rec_id  = 1,
            s.next_chat_id = 1,
            s.theme_priority_order  = [],
            s.log_token_budget      = $log_budget,
            s.hot_theme_token_budget = $hot_budget
        RETURN s
        """,
        {
            "log_budget": settings.LOG_TOKEN_BUDGET,
            "hot_budget": settings.HOT_THEME_TOKEN_BUDGET,
        },
    )
    _ensure_vector_index(graph)
    node = result.result_set[0][0]
    return _row_to_state(node.properties)


def get_system(graph: Graph) -> SystemState:
    """Read the System node. Raises RuntimeError if it does not exist."""
    result = graph.query("MATCH (s:System) RETURN s")
    if not result.result_set:
        raise RuntimeError(
            "System node not found. Run init_system() or `python -m arakne.cli init-system` first."
        )
    node = result.result_set[0][0]
    return _row_to_state(node.properties)


def update_theme_priority_order(graph: Graph, priority_order: list[str]) -> None:
    """Persist a new theme_priority_order on the System node."""
    result = graph.query(
        "MATCH (s:System) SET s.theme_priority_order = $order RETURN s",
        {"order": priority_order},
    )
    if not result.result_set:
        raise RuntimeError(
            "System node not found. Cannot update theme_priority_order."
        )


def increment_counter(graph: Graph, counter: CounterName) -> str:
    """
    Atomically increment the named counter and return the minted token.

    Returns e.g. "node:1" on the first call for counter="node".
    The counter field is left pointing at the next available value.
    """
    field = _COUNTER_FIELD[counter]
    prefix = counter
    result = graph.query(
        f"""
        MATCH (s:System)
        SET s.{field} = s.{field} + 1
        RETURN s.{field} - 1
        """
    )
    if not result.result_set:
        raise RuntimeError(
            "System node not found. Cannot mint token — run init_system() first."
        )
    minted_id: int = result.result_set[0][0]
    return f"{prefix}:{minted_id}"
