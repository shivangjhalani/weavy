from datetime import datetime

from pydantic import BaseModel, Field

from weavy.models.canonical import Session
from weavy.models.graph import SemanticEdge, SemanticNode
from weavy.models.themes import Theme


class OperationResult(BaseModel):
    ok: bool
    id: str | None = None
    message: str | None = None


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


class CompletedSessionRow(BaseModel):
    id: str
    summary: str
    graph_changes: dict
    completed_at: str
