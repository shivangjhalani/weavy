from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator


class LogEntry(BaseModel):
    source_id: str  # rec:N or chat:N
    timestamp: datetime
    start_offset: int  # seconds for rec, message_index for chat
    end_offset: int | None  # seconds for rec, null for chat
    note: str


class ProvenanceInput(BaseModel):
    source_id: str  # rec:N or chat:N
    start_offset: int
    end_offset: int | None

    @model_validator(mode="after")
    def validate_offsets(self) -> "ProvenanceInput":
        if self.source_id.startswith("rec:") and self.end_offset is None:
            raise ValueError("rec: provenance requires end_offset")
        return self

    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, v: str) -> str:
        if not (v.startswith("rec:") or v.startswith("chat:")):
            raise ValueError("source_id must be rec:N or chat:N")
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
