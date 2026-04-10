from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LogEntry(BaseModel):
    source_id: str  # s:N
    timestamp: datetime
    note: str


class ProvenanceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str  # s:N

    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, v: str) -> str:
        if not v.startswith("s:"):
            raise ValueError("source_id must be s:N")
        return v


class SemanticNode(BaseModel):
    id: str  # node:N
    aliases: list[str]  # aliases[0] is canonical name; min 1
    summary: str
    total_log_count: int = 0
    log: list[LogEntry] = Field(default_factory=list)

    @field_validator("aliases")
    @classmethod
    def aliases_nonempty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("aliases must have at least one entry")
        return v


class SemanticEdge(BaseModel):
    id: str  # edge:N
    from_node_id: str
    to_node_id: str
    label: str
    note: str | None = None  # why this relationship exists
    source_id: str | None = None  # s:N — which session created this edge
