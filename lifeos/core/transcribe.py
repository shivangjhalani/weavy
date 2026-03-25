from pathlib import Path

import litellm

litellm.drop_params = True


def transcribe_file(
    audio_path: Path,
    model: str = "groq/whisper-large-v3-turbo",
    language: str | None = None,
    prompt: str | None = None,
    response_format: str = "verbose_json",
    temperature: float = 0.0,
) -> dict:
    """Transcribe a single audio file. Returns the full response dict."""
    kwargs = {
        "file": open(audio_path, "rb"),
        "model": model,
        "response_format": response_format,
        "temperature": temperature,
    }
    if language:
        kwargs["language"] = language
    if prompt:
        kwargs["prompt"] = prompt
    if response_format == "verbose_json":
        kwargs["timestamp_granularities"] = ["segment", "word"]

    with kwargs["file"] as fp:
        kwargs["file"] = fp
        response = litellm.transcription(**kwargs)

    text = getattr(response, "text", "") or ""
    data = response.model_dump() if hasattr(response, "model_dump") else {"text": text}
    return data
