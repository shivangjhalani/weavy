from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, field_serializer, field_validator, model_validator

from arakne.timefmt import format_agent_date_range, format_agent_timestamp


class LogEntry(BaseModel):
    is_fence: Literal[False] = False
    source_id: str  # rec:N or chat:N
    timestamp: datetime
    start_offset: int  # seconds for rec, message_index for chat
    end_offset: int | None  # seconds for rec, null for chat
    note: str

    @field_serializer("timestamp", when_used="json")
    def serialize_timestamp(self, value: datetime) -> str:
        return format_agent_timestamp(value)


class FenceEntry(BaseModel):
    is_fence: Literal[True]
    timestamp: datetime
    note: str
    entries_behind: int
    date_range: tuple[datetime, datetime]

    @field_serializer("timestamp", when_used="json")
    def serialize_timestamp(self, value: datetime) -> str:
        return format_agent_timestamp(value)

    @field_serializer("date_range", when_used="json")
    def serialize_date_range(self, value: tuple[datetime, datetime]) -> list[str]:
        return format_agent_date_range(value[0], value[1])


AnyLogEntry = Annotated[Union[LogEntry, FenceEntry], ...]


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
    embedding: list[float] | None = None
    total_log_count: int = 0
    log: list[AnyLogEntry] = []

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
