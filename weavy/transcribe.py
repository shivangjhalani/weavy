"""
Audio transcription — converts audio files to timestamped transcripts via Groq Whisper.
"""

from pathlib import Path

import litellm

from weavy.config import settings

_SUPPORTED_EXTENSIONS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg"}


def transcribe_audio(audio_path: str) -> str:
    """
    Transcribe an audio file and return a formatted transcript string with
    inline [M:SS] segment markers.

    Raises FileNotFoundError if the audio file does not exist.
    Raises ValueError if the file extension is not supported by Whisper.
    """
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
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

    with open(audio_path, "rb") as f:
        kwargs["file"] = f
        response = litellm.transcription(**kwargs)

    return _format_transcript(response)


def _seg_attr(seg, key: str):
    """Access a segment field whether it's a dict or a Pydantic/object."""
    if isinstance(seg, dict):
        return seg[key]
    return getattr(seg, key)


def _format_transcript(response) -> str:
    """
    Convert a verbose_json Whisper response into inline [M:SS] segment lines.
    Falls back to plain response.text if no segments are present.
    """
    segments = getattr(response, "segments", None)
    if not segments:
        return response.text.strip()

    lines = []
    for seg in segments:
        start_secs = int(_seg_attr(seg, "start"))
        text = _seg_attr(seg, "text").strip()
        if not text:
            continue
        minutes = start_secs // 60
        seconds = start_secs % 60
        lines.append(f"[{minutes}:{seconds:02d}] {text}")

    return "\n".join(lines) if lines else response.text.strip()
