import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class TouchedNode(BaseModel):
    node_id: str
    action: Literal["created", "updated", "deleted"]


class TouchedEdge(BaseModel):
    edge_id: str
    action: Literal["created", "updated", "deleted"]


class EdgeSnapshot(BaseModel):
    """Full edge state captured before a mutation, for rollback."""
    id: str
    from_node_id: str
    to_node_id: str
    label: str


class NodeSnapshot(BaseModel):
    """Full node state captured before a mutation, for rollback."""
    id: str
    name: str
    aliases: list[str]
    summary: str
    log: list[str]  # raw JSON strings as stored in FalkorDB
    total_log_count: int
    edges: list[EdgeSnapshot] = []  # populated for delete_node ops only


class MutationOp(BaseModel):
    """Single reversible operation recorded during a harness run."""
    op: Literal[
        "create_node", "update_node", "delete_node",
        "create_edge", "update_edge", "delete_edge",
    ]
    node_id: str | None = None
    edge_id: str | None = None
    node_before: NodeSnapshot | None = None  # set for update_node, delete_node
    edge_before: EdgeSnapshot | None = None  # set for update_edge, delete_edge


class ToolCall(BaseModel):
    tool_name: str
    args: dict[str, Any]
    result: str | None = None
    error: str | None = None
    called_at: datetime


class TurnUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0


class Turn(BaseModel):
    turn_number: int
    input_messages: list[dict[str, Any]] = []
    reasoning_content: str | None = None
    text_content: str | None = None
    tool_calls: list[ToolCall] = []
    usage: TurnUsage = Field(default_factory=TurnUsage)
    timestamp: datetime


def graph_delta(
    touched_nodes: list["TouchedNode"],
    touched_edges: list["TouchedEdge"],
) -> dict[str, int]:
    """Summarise write activity as action-count pairs, e.g. nodes_created=3."""
    delta: dict[str, int] = {}
    for action in ("created", "updated", "deleted"):
        nc = sum(1 for n in touched_nodes if n.action == action)
        ec = sum(1 for e in touched_edges if e.action == action)
        if nc:
            delta[f"nodes_{action}"] = nc
        if ec:
            delta[f"edges_{action}"] = ec
    return delta


class RunTrace(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    mode: Literal["ingestion", "query", "theme"]
    started_at: datetime
    ended_at: datetime | None = None
    input_summary: str
    turns: list[Turn] = []
    total_usage: TurnUsage = Field(default_factory=TurnUsage)
    completion_payload: dict[str, Any] | None = None
    touched_nodes: list[TouchedNode] = []
    touched_edges: list[TouchedEdge] = []
    mutation_ops: list[MutationOp] = []
    status: Literal["running", "completed", "failed"] = "running"
    error: str | None = None
    conversation: list[dict] | None = None
