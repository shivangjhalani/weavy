import re
from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

_INLINE_TS = re.compile(r"^\[(\d+):(\d{2})\]\s*(.+)")


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class TranscriptSegment(BaseModel):
    start: float  # seconds from recording start
    end: float  # seconds from recording start
    text: str


def format_transcript_segments(segments: list[TranscriptSegment]) -> str:
    return "\n".join(
        f"[{int(segment.start) // 60}:{int(segment.start) % 60:02d}] {segment.text}"
        for segment in segments
    )


def parse_transcript_text(text: str) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    for line in text.splitlines():
        match = _INLINE_TS.match(line.strip())
        if not match:
            continue
        start = float(int(match.group(1)) * 60 + int(match.group(2)))
        segments.append(TranscriptSegment(start=start, end=start, text=match.group(3)))

    if not segments:
        return [TranscriptSegment(start=0.0, end=1.0, text=text.strip())]

    for index in range(len(segments) - 1):
        segments[index] = TranscriptSegment(
            start=segments[index].start,
            end=segments[index + 1].start,
            text=segments[index].text,
        )

    last = segments[-1]
    segments[-1] = TranscriptSegment(
        start=last.start, end=last.start + 1, text=last.text
    )
    return segments


def is_untimed_transcript(segments: Sequence[TranscriptSegment]) -> bool:
    return len(segments) == 1 and segments[0].start == 0.0 and segments[0].end == 1.0


def extract_transcript_span(
    segments: list[TranscriptSegment],
    start_offset: float,
    end_offset: float,
    context_secs: float = 0,
) -> str:
    lo = max(0.0, start_offset - context_secs)
    hi = end_offset + context_secs
    matched = [
        segment for segment in segments if segment.end > lo and segment.start < hi
    ]
    if matched:
        return format_transcript_segments(matched)
    if is_untimed_transcript(segments):
        return segments[0].text
    return ""


class Transcript(BaseModel):
    id: str  # rec:N
    audio_path: str
    timestamp: datetime
    segments: list[TranscriptSegment]

    @property
    def text(self) -> str:
        """Render segments as [M:SS] lines for LLM consumption."""
        return format_transcript_segments(self.segments)


class ChatSession(BaseModel):
    id: str  # chat:N
    timestamp: datetime
    messages: list[ChatMessage]
