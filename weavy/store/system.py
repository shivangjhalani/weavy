"""
System node — singleton node in FalkorDB that holds global counters and config.
"""

import json
from typing import Any, Literal

from falkordb import Graph
from pydantic import BaseModel, field_validator

from weavy.config import settings

CounterName = Literal["node", "edge", "session"]

_COUNTER_FIELD: dict[str, str] = {
    "node": "next_node_id",
    "edge": "next_edge_id",
    "session": "next_session_id",
}


class SystemState(BaseModel):
    next_node_id: int
    next_edge_id: int
    next_session_id: int
    theme_priority_order: list[str]
    hot_theme_token_budget: int
    last_theme_run_at: str
    preface: str | None = None  # what this graph is about

    @field_validator("theme_priority_order", mode="before")
    @classmethod
    def parse_json_string(cls, v: Any) -> list:
        if isinstance(v, str):
            return json.loads(v)
        return list(v) if v else []


def init_system(
    graph: Graph,
    embedding_dim: int | None = None,
    hot_theme_token_budget: int | None = None,
) -> SystemState:
    """Create the System node if it does not exist; return current state.

    When *embedding_dim* is provided, a vector index is created (or verified)
    on SemanticNode.embedding for hybrid search.

    *hot_theme_token_budget* seeds the budget on first creation; it defaults to
    ``settings.HOT_THEME_TOKEN_BUDGET``. Once the node exists, the persisted
    value is the runtime source of truth (``MERGE`` only sets it ``ON CREATE``),
    so re-running init never overwrites a budget tuned per-graph.
    """
    budget = (
        hot_theme_token_budget
        if hot_theme_token_budget is not None
        else settings.HOT_THEME_TOKEN_BUDGET
    )
    result = graph.query(
        """
        MERGE (s:System)
        ON CREATE SET
            s.name = 'System',
            s.next_node_id = 1,
            s.next_edge_id = 1,
            s.next_session_id = 1,
            s.theme_priority_order  = [],
            s.hot_theme_token_budget = $budget,
            s.last_theme_run_at = '1970-01-01T00:00:00+00:00'
        RETURN s
        """,
        {"budget": budget},
    )

    if embedding_dim is not None:
        _ensure_vector_index(graph, embedding_dim)

    return SystemState(**result.result_set[0][0].properties)


def _ensure_vector_index(graph: Graph, dim: int) -> None:
    try:
        graph.query(
            f"CREATE VECTOR INDEX FOR (n:SemanticNode) ON (n.embedding) "
            f"OPTIONS {{dimension:{dim}, similarityFunction:'cosine'}}"
        )
    except Exception as e:
        msg = str(e).lower()
        if "already" in msg or "exists" in msg or "equivalent" in msg:
            return
        raise


def get_system(graph: Graph) -> SystemState:
    """Read the System node. Raises RuntimeError if it does not exist."""
    result = graph.query("MATCH (s:System) RETURN s")
    if not result.result_set:
        raise RuntimeError(
            "System node not found. Run init_system() or `python -m weavy.cli init-system` first."
        )
    return SystemState(**result.result_set[0][0].properties)


def update_theme_priority_order(graph: Graph, priority_order: list[str]) -> None:
    result = graph.query(
        "MATCH (s:System) SET s.theme_priority_order = $order RETURN s",
        {"order": priority_order},
    )
    if not result.result_set:
        raise RuntimeError("System node not found. Cannot update theme_priority_order.")


def set_preface(graph: Graph, preface: str) -> None:
    result = graph.query(
        "MATCH (s:System) SET s.preface = $preface RETURN s",
        {"preface": preface},
    )
    if not result.result_set:
        raise RuntimeError("System node not found. Cannot update preface.")


def update_last_theme_run_at(graph: Graph, iso_timestamp: str) -> None:
    result = graph.query(
        "MATCH (s:System) SET s.last_theme_run_at = $ts RETURN s",
        {"ts": iso_timestamp},
    )
    if not result.result_set:
        raise RuntimeError("System node not found. Cannot update last_theme_run_at.")


def increment_counter(graph: Graph, counter: CounterName) -> str:
    """
    Atomically increment the named counter and return the minted token.

    Returns e.g. "node:1" on the first call for counter="node".
    The counter field is left pointing at the next available value.
    """
    field = _COUNTER_FIELD[counter]
    prefix = "s" if counter == "session" else counter
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
