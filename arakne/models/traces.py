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
    reasoning_content: str | None = None
    text_content: str | None = None
    tool_calls: list[ToolCall] = []
    usage: TurnUsage = Field(default_factory=TurnUsage)
    timestamp: datetime


class RunTrace(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    mode: Literal["ingestion", "query", "theme"]
    started_at: datetime
    ended_at: datetime | None = None
    input_summary: str
    turns: list[Turn] = []
    total_usage: TurnUsage = Field(default_factory=TurnUsage)
    tool_calls: list[ToolCall] = []  # deprecated — kept for compat, no longer populated
    llm_outputs: list[str] = []  # deprecated — kept for compat, no longer populated
    completion_payload: dict[str, Any] | None = None
    touched_nodes: list[TouchedNode] = []
    touched_edges: list[TouchedEdge] = []
    status: Literal["running", "completed", "failed"] = "running"
    error: str | None = None
    conversation: list[dict] | None = None
