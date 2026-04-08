from typing import Literal

from pydantic import BaseModel

from weavy.timefmt import AgentTimestamp


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class Transcript(BaseModel):
    id: str  # rec:N
    audio_path: str
    timestamp: AgentTimestamp
    text: str


class ChatSession(BaseModel):
    id: str  # chat:N
    timestamp: AgentTimestamp
    messages: list[ChatMessage]
