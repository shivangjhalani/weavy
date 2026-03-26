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
    name: str
    summary: str
    aliases: list[str] = Field(default_factory=list)
    log: list[LogEntry] = Field(default_factory=list)
    refs: list[TranscriptRef] = Field(default_factory=list)
    embedding: list[float] | None = None


class Edge(BaseModel):
    id: str
    label: str
    source_id: str
    target_id: str
    summary: str
    log: list[LogEntry] = Field(default_factory=list)
    refs: list[TranscriptRef] = Field(default_factory=list)
    embedding: list[float] | None = None


class EpisodeSpan(BaseModel):
    start_offset: int
    end_offset: int
    summary: str
    embedding: list[float] | None = None


class Transcript(BaseModel):
    id: str
    recorded_at: datetime
    text: str
    segments: list[dict] = Field(default_factory=list)
    episode_spans: list[EpisodeSpan] = Field(default_factory=list)
