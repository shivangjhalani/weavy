"""
Audio transcription — converts audio files to structured transcript segments via Groq Whisper.
"""

from pathlib import Path

import litellm

from weavy.config import settings
from weavy.models.canonical import TranscriptSegment, parse_transcript_text

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


def transcribe_audio(audio_path: str) -> list[TranscriptSegment]:
    """
    Transcribe an audio file and return structured segments with start/end times.

    Raises FileNotFoundError if the audio file does not exist.
    Raises ValueError if the file extension is not supported by Whisper.
    """
    path = Path(audio_path)
    if path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported audio format '{path.suffix}'. "
            f"Supported: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}"
        )

    kwargs: dict = {
        "model": settings.WHISPER_MODEL,
        "response_format": "verbose_json",
        "temperature": settings.WHISPER_TEMPERATURE,
    }
    if settings.WHISPER_LANGUAGE:
        kwargs["language"] = settings.WHISPER_LANGUAGE
    if settings.WHISPER_PROMPT:
        kwargs["prompt"] = settings.WHISPER_PROMPT

    with path.open("rb") as f:
        kwargs["file"] = f
        response = litellm.transcription(**kwargs)

    return _parse_segments(response)


def _seg_attr(seg, key: str):
    """Access a segment field whether it's a dict or a Pydantic/object."""
    if isinstance(seg, dict):
        return seg[key]
    return getattr(seg, key)


def _parse_segments(response) -> list[TranscriptSegment]:
    """Convert a verbose_json Whisper response into TranscriptSegment list."""
    raw = getattr(response, "segments", None)
    if not raw:
        return parse_transcript_text(response.text.strip())

    segments = []
    for seg in raw:
        text = _seg_attr(seg, "text").strip()
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                start=float(_seg_attr(seg, "start")),
                end=float(_seg_attr(seg, "end")),
                text=text,
            )
        )
    return segments
