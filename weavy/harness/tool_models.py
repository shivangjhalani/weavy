"""
Agent tool input contracts.

These schemas belong to the harness boundary only. They define what the model is
allowed to call, not the general application contract for lower layers.
"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from weavy.models.graph import ProvenanceInput
from weavy.models.themes import ThemeStatus

NodeId = Annotated[str, StringConstraints(pattern=r"^node:\d+$")]
EdgeId = Annotated[str, StringConstraints(pattern=r"^edge:\d+$")]


# Resolved event/valid time of this fact — when it became true in the world (not when
# it was discussed). Optional; defaults to the episode time when no temporal cue exists.
HappenedAt = datetime | None


class CreateNodeInput(BaseModel):
    aliases: list[str]
    summary: str
    note: str
    provenance: ProvenanceInput
    happened_at: HappenedAt = None


class UpdateNodeInput(BaseModel):
    node_id: NodeId
    note: str
    new_summary: str | None = None
    new_aliases: list[str] | None = None
    provenance: ProvenanceInput
    happened_at: HappenedAt = None


class CreateEdgeInput(BaseModel):
    from_node_id: NodeId
    to_node_id: NodeId
    label: str  # short directional relationship type, e.g. "works at"
    fact: str  # natural-language statement of the relationship; searchable
    note: str  # why this edge is being written now (logged)
    happened_at: HappenedAt = None


class UpdateEdgeInput(BaseModel):
    edge_id: EdgeId
    note: str  # why this edge is changing (logged)
    new_label: str | None = None
    new_fact: str | None = None
    happened_at: HappenedAt = None


class DeleteNodeInput(BaseModel):
    node_id: NodeId
    reason: str


class DeleteEdgeInput(BaseModel):
    edge_id: EdgeId
    reason: str


class SearchGraphInput(BaseModel):
    query: str
    limit: int = 10
    time_range: list[datetime] | None = (
        None  # [start, end] — filter by happened_at (valid time), falling back to record time
    )


class GetNodeNeighborhoodInput(BaseModel):
    node_id: NodeId


class GetNodeInput(BaseModel):
    node_ids: list[NodeId]


class GetEdgeInput(BaseModel):
    edge_id: EdgeId


class GetSessionInput(BaseModel):
    session_id: Annotated[str, StringConstraints(pattern=r"^s:\d+$")]


class ListSessionsInput(BaseModel):
    date_range: list[datetime] | None = (
        None  # [start, end] — list avoids Gemini prefixItems rejection
    )
    limit: int = 20


class GetThemeInput(BaseModel):
    name: str


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


class CompleteInput(BaseModel):
    summary: str
    answer: str | None = None
    cited_sources: list[str] = Field(default_factory=list)
    consulted_nodes: list[str] = Field(default_factory=list)


class CompleteThemeUpdateInput(BaseModel):
    updated_themes: list[str]
    priority_order: list[str]
