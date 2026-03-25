from datetime import datetime

from pydantic import BaseModel, Field


class TranscriptRef(BaseModel):
    transcript_id: str
    start_offset: int | None = None
    end_offset: int | None = None


class LogEntry(BaseModel):
    recorded_at: datetime
    note: str


class Node(BaseModel):
    id: str
    type: str
    summary: str
    aliases: list[str] = Field(default_factory=list)
    log: list[LogEntry] = Field(default_factory=list)
    refs: list[TranscriptRef] = Field(default_factory=list)
    embedding: list[float] | None = None


class Edge(BaseModel):
    id: str
    type: str
    source_id: str
    target_id: str
    summary: str
    log: list[LogEntry] = Field(default_factory=list)
    refs: list[TranscriptRef] = Field(default_factory=list)
    embedding: list[float] | None = None
