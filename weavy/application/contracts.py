from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from weavy.models.graph import SemanticEdge, SemanticNode
from weavy.models.themes import Theme


class OperationResult(BaseModel):
    ok: bool
    id: str | None = None
    message: str | None = None


class SearchResult(BaseModel):
    """A single hit in the unified ranked search.

    ``kind="node"`` rows describe an entity (``id`` is ``node:N``, ``text`` is
    the entity's summary line). ``kind="edge"`` rows describe a relationship fact
    (``id`` is ``edge:N``, ``text`` is the fact, and ``endpoints`` names the two
    nodes it connects so the agent can traverse from a fact to its entities).
    ``kind="episode"`` rows are verbatim excerpts from an original episode
    (``id`` is ``s:N``, ``text`` is the excerpt) — ground truth behind the
    semantic layer, readable in full via ``get_session``.
    """

    kind: Literal["node", "edge", "episode"]
    id: str
    label: str  # node: canonical alias; edge: relationship label; episode: date
    text: str  # node: summary line; edge: the fact; episode: verbatim excerpt
    score: (
        float | None
    )  # vector distance (lower = closer); None = keyword-only hit, no real distance
    edge_count: int | None = None  # node only: degree, for hub identification
    endpoints: list[str] | None = None  # edge only: [from_node_id, to_node_id]


class SearchGraphOutput(BaseModel):
    results: list[SearchResult]


class NeighborSummary(BaseModel):
    edge_id: str
    edge_label: str
    edge_fact: str | None = None
    node_id: str
    canonical_alias: str
    summary_line: str


class GetNodeNeighborhoodOutput(BaseModel):
    node: SemanticNode
    neighbors: list[NeighborSummary]


class GetNodeResult(BaseModel):
    node: SemanticNode
    edges: list[SemanticEdge] = Field(default_factory=list)
    mentioned_by: list[str] = Field(
        default_factory=list
    )  # s:N episodes that touched this node


class GetSessionOutput(BaseModel):
    id: str
    timestamp: datetime
    text: str  # raw episode content (concatenated user messages)
    summary: str | None = None


class GetNodeOutput(BaseModel):
    results: list[GetNodeResult]
    not_found: list[str] = Field(default_factory=list)


class SessionSummary(BaseModel):
    id: str
    timestamp: datetime
    summary: str | None = None


class ListSessionsOutput(BaseModel):
    sessions: list[SessionSummary]


class GetThemeOutput(BaseModel):
    theme: Theme


class CompletedSessionRow(BaseModel):
    id: str
    summary: str
    graph_changes: dict
    completed_at: str
