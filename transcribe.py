#!/usr/bin/env python3
"""
Standalone audio transcription via Groq Whisper.

No dependency on the Weavy memory layer. Reads WHISPER_* env vars directly.

Usage:
    python transcribe.py <audio_path> [--output path.json]
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import litellm
from pydantic import BaseModel

_SUPPORTED_EXTENSIONS = {
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".m4a",
    ".wav",
    ".webm",
    ".ogg",
}

_INLINE_TS = re.compile(r"^\[(\d+):(\d{2})\]\s*(.+)")

WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "groq/whisper-large-v3-turbo")
WHISPER_LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "")
WHISPER_PROMPT = os.environ.get("WHISPER_PROMPT", "")
WHISPER_TEMPERATURE = float(os.environ.get("WHISPER_TEMPERATURE", "0"))


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


def format_transcript_segments(segments: list[TranscriptSegment]) -> str:
    """Format segments for display: [0] text, [1] text, ..."""
    return "\n".join(f"[{i}] {seg.text}" for i, seg in enumerate(segments))


def parse_transcript_text(text: str) -> list[TranscriptSegment]:
    """Parse [MM:SS] timestamped text into segments."""
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


def extract_segment_range(
    segments: list[TranscriptSegment], start_index: int, end_index: int
) -> str:
    """Return the text of segments[start_index:end_index] joined by spaces."""
    selected = segments[start_index:end_index]
    if not selected:
        return ""
    return " ".join(seg.text for seg in selected)


def transcribe_audio(audio_path: str) -> dict:
    """Transcribe an audio file and return the raw Whisper response as a dict."""
    path = Path(audio_path)
    if path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported audio format '{path.suffix}'. "
            f"Supported: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}"
        )

    kwargs: dict = {
        "model": WHISPER_MODEL,
        "response_format": "verbose_json",
        "temperature": WHISPER_TEMPERATURE,
    }
    if WHISPER_LANGUAGE:
        kwargs["language"] = WHISPER_LANGUAGE
    if WHISPER_PROMPT:
        kwargs["prompt"] = WHISPER_PROMPT

    with path.open("rb") as f:
        kwargs["file"] = f
        response = litellm.transcription(**kwargs)

    return response.model_dump()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Transcribe audio to JSON via Whisper"
    )
    parser.add_argument("audio_path", help="Path to the audio file")
    parser.add_argument("--output", default=None, help="Output file or directory (default: stdout)")
    args = parser.parse_args()

    result = transcribe_audio(args.audio_path)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        out = Path(args.output)
        if out.is_dir():
            out = out / (Path(args.audio_path).stem + ".json")
        out.write_text(text)
    else:
        sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
