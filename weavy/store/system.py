"""
System node — singleton node in FalkorDB that holds global counters and config.
This is the only store module fully implemented in Phase 1.
"""

import json
from typing import Any, Literal

from falkordb import Graph
from pydantic import BaseModel, field_validator

CounterName = Literal["node", "edge", "rec", "chat"]

_COUNTER_FIELD: dict[str, str] = {
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
    hot_theme_token_budget: int

    @field_validator("theme_priority_order", mode="before")
    @classmethod
    def parse_json_string(cls, v: Any) -> list:
        if isinstance(v, str):
            return json.loads(v)
        return list(v) if v else []


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
            s.hot_theme_token_budget = 250
        RETURN s
        """
    )
    return SystemState(**result.result_set[0][0].properties)


def get_system(graph: Graph) -> SystemState:
    """Read the System node. Raises RuntimeError if it does not exist."""
    result = graph.query("MATCH (s:System) RETURN s")
    if not result.result_set:
        raise RuntimeError(
            "System node not found. Run init_system() or `python -m weavy.cli init-system` first."
        )
    return SystemState(**result.result_set[0][0].properties)


def update_theme_priority_order(graph: Graph, priority_order: list[str]) -> None:
    """Persist a new theme_priority_order on the System node."""
    result = graph.query(
        "MATCH (s:System) SET s.theme_priority_order = $order RETURN s",
        {"order": priority_order},
    )
    if not result.result_set:
        raise RuntimeError("System node not found. Cannot update theme_priority_order.")


def increment_counter(graph: Graph, counter: CounterName) -> str:
    """
    Atomically increment the named counter and return the minted token.

    Returns e.g. "node:1" on the first call for counter="node".
    The counter field is left pointing at the next available value.
    """
    field = _COUNTER_FIELD[counter]
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
    return f"{counter}:{minted_id}"
