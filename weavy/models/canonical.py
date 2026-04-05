from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_serializer

from weavy.timefmt import format_agent_timestamp


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class Transcript(BaseModel):
    id: str  # rec:N
    audio_path: str
    timestamp: datetime
    text: str

    @field_serializer("timestamp", when_used="json")
    def serialize_timestamp(self, value: datetime) -> str:
        return format_agent_timestamp(value)


class ChatSession(BaseModel):
    id: str  # chat:N
    timestamp: datetime
    messages: list[ChatMessage]

    @field_serializer("timestamp", when_used="json")
    def serialize_timestamp(self, value: datetime) -> str:
        return format_agent_timestamp(value)
