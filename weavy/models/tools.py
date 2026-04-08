"""
Tool input and output contracts. Every tool function accepts one *Input model
and returns one *Output model. Pydantic validates both boundaries.
"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from weavy.models.canonical import ChatSession
from weavy.models.graph import ProvenanceInput, SemanticEdge, SemanticNode
from weavy.models.themes import Theme, ThemeStatus
from weavy.timefmt import AgentTimestamp

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
    provenance: ProvenanceInput | None = None


class UpdateNodeInput(BaseModel):
    node_id: NodeId
    note: str
    new_summary: str | None = None
    new_aliases: list[str] | None = None
    provenance: ProvenanceInput | None = None


class CreateEdgeInput(BaseModel):
    from_node_id: NodeId
    to_node_id: NodeId
    label: str


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


class ListTranscriptsInput(BaseModel):
    date_range: list[datetime] | None = None  # [start, end] — list avoids Gemini prefixItems rejection
    limit: int = 20


class TranscriptSpanRequest(BaseModel):
    transcript_id: str
    start_offset: int
    end_offset: int


class GetTranscriptSpanInput(BaseModel):
    spans: list[TranscriptSpanRequest]  # one or more


class ListChatsInput(BaseModel):
    date_range: list[datetime] | None = None  # [start, end] — list avoids Gemini prefixItems rejection
    limit: int = 20


class GetChatInput(BaseModel):
    chat_id: str
    start_index: int | None = None
    end_index: int | None = None


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


# ---------------------------------------------------------------------------
# Completion tool inputs
# ---------------------------------------------------------------------------


class CompleteIngestionInput(BaseModel):
    summary: str


class CitedSource(BaseModel):
    source_id: str  # rec:N or chat:N
    start_offset: int | None = None
    end_offset: int | None = None


class DeliverResponseInput(BaseModel):
    answer: str
    cited_sources: list[CitedSource]
    consulted_nodes: list[str]


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
    node_id: str
    canonical_alias: str
    summary_line: str


class GetNodeNeighborhoodOutput(BaseModel):
    node: SemanticNode
    neighbors: list[NeighborSummary]


class GetNodeResult(BaseModel):
    node: SemanticNode
    edges: list[SemanticEdge] = []


class GetNodeOutput(BaseModel):
    results: list[GetNodeResult]
    not_found: list[str] = []


class TranscriptSummary(BaseModel):
    id: str
    timestamp: AgentTimestamp
    audio_path: str


class ListTranscriptsOutput(BaseModel):
    transcripts: list[TranscriptSummary]


class GetTranscriptSpanResult(BaseModel):
    transcript_id: str
    text: str


class GetTranscriptSpanOutput(BaseModel):
    results: list[GetTranscriptSpanResult]


class ChatSummary(BaseModel):
    id: str
    timestamp: AgentTimestamp


class ListChatsOutput(BaseModel):
    chats: list[ChatSummary]


class GetChatOutput(BaseModel):
    session: ChatSession


class GetThemeOutput(BaseModel):
    theme: Theme
