from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class Transcript(BaseModel):
    id: str  # rec:N
    audio_path: str
    timestamp: datetime
    text: str


class ChatSession(BaseModel):
    id: str  # chat:N
    timestamp: datetime
    messages: list[ChatMessage]
