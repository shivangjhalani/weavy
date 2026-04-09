"""
Tool input and output contracts. Every tool function accepts one *Input model
and returns one *Output model. Pydantic validates both boundaries.
"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from weavy.models.canonical import Session
from weavy.models.graph import ProvenanceInput, SemanticEdge, SemanticNode
from weavy.models.themes import Theme, ThemeStatus

# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------


NodeId = Annotated[str, StringConstraints(pattern=r"^node:\d+$")]
EdgeId = Annotated[str, StringConstraints(pattern=r"^edge:\d+$")]


class OperationResult(BaseModel):
    ok: bool
    id: str | None = None
    message: str | None = None


# ---------------------------------------------------------------------------
# Write tool inputs
# ---------------------------------------------------------------------------


class CreateNodeInput(BaseModel):
    aliases: list[str]
    summary: str
    note: str
    provenance: ProvenanceInput


class UpdateNodeInput(BaseModel):
    node_id: NodeId
    note: str
    new_summary: str | None = None
    new_aliases: list[str] | None = None
    provenance: ProvenanceInput


class CreateEdgeInput(BaseModel):
    from_node_id: NodeId
    to_node_id: NodeId
    label: str
    note: str


class UpdateEdgeInput(BaseModel):
    edge_id: EdgeId
    new_label: str


class DeleteNodeInput(BaseModel):
    node_id: NodeId
    reason: str


class DeleteEdgeInput(BaseModel):
    edge_id: EdgeId
    reason: str


# ---------------------------------------------------------------------------
# Read tool inputs
# ---------------------------------------------------------------------------


class SearchGraphInput(BaseModel):
    query: str
    limit: int = 10


class GetNodeNeighborhoodInput(BaseModel):
    node_id: NodeId


class GetNodeInput(BaseModel):
    node_ids: list[NodeId]  # one or more, e.g. ["node:1"] or ["node:1", "node:2"]


class ListSessionsInput(BaseModel):
    date_range: list[datetime] | None = (
        None  # [start, end] — list avoids Gemini prefixItems rejection
    )
    limit: int = 20


class GetSessionInput(BaseModel):
    session_id: str
    start_index: int | None = None
    end_index: int | None = None
    max_chars: int = 6000  # total content limit; increase if you need more context


class GetThemeInput(BaseModel):
    name: str


# ---------------------------------------------------------------------------
# Theme tool inputs
# ---------------------------------------------------------------------------


class CreateThemeInput(BaseModel):
    name: str
    state: str
    anchors: list[NodeId]
    status: list[ThemeStatus]


class UpdateThemeInput(BaseModel):
    name: str
    new_state: str | None = None
    new_anchors: list[NodeId] | None = None
    new_status: list[ThemeStatus] | None = None


class RetireThemeInput(BaseModel):
    name: str


class SetPrefaceInput(BaseModel):
    preface: str


# ---------------------------------------------------------------------------
# Completion tool inputs
# ---------------------------------------------------------------------------


class CompleteInput(BaseModel):
    summary: str
    answer: str | None = None
    cited_sources: list[str] = Field(default_factory=list)
    consulted_nodes: list[str] = Field(default_factory=list)


class CompleteThemeUpdateInput(BaseModel):
    updated_themes: list[str]
    priority_order: list[str]


# ---------------------------------------------------------------------------
# Read tool outputs
# ---------------------------------------------------------------------------


class SearchResult(BaseModel):
    id: str
    canonical_alias: str
    summary_line: str
    edge_count: int


class SearchGraphOutput(BaseModel):
    results: list[SearchResult]


class NeighborSummary(BaseModel):
    edge_id: str
    edge_label: str
    edge_note: str | None = None
    node_id: str
    canonical_alias: str
    summary_line: str


class GetNodeNeighborhoodOutput(BaseModel):
    node: SemanticNode
    neighbors: list[NeighborSummary]


class GetNodeResult(BaseModel):
    node: SemanticNode
    edges: list[SemanticEdge] = Field(default_factory=list)


class GetNodeOutput(BaseModel):
    results: list[GetNodeResult]
    not_found: list[str] = Field(default_factory=list)


class SessionSummary(BaseModel):
    id: str
    timestamp: datetime
    summary: str | None = None


class ListSessionsOutput(BaseModel):
    sessions: list[SessionSummary]


class GetSessionOutput(BaseModel):
    session: Session


class GetThemeOutput(BaseModel):
    theme: Theme
