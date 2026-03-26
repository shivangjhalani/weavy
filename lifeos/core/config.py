import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class Config:
    gemini_api_key: str
    groq_api_key: str
    falkordb_host: str
    falkordb_port: int
    graph_name: str
    transcript_dir: Path
    gemini_model: str
    gemini_embedding_model: str
    reasoning_effort: str  # "none" | "low" | "medium" | "high" — maps to litellm reasoning_effort
    whisper_model: str
    whisper_language: str | None
    whisper_prompt: str | None
    whisper_response_format: str
    whisper_temperature: float


_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is not None:
        return _config
    load_dotenv(PROJECT_ROOT / ".env")
    _config = Config(
        gemini_api_key=os.environ["GEMINI_API_KEY"],
        groq_api_key=os.environ["GROQ_API_KEY"],
        falkordb_host=os.getenv("FALKORDB_HOST", "localhost"),
        falkordb_port=int(os.getenv("FALKORDB_PORT", "6379")),
        graph_name=os.getenv("GRAPH_NAME", "lifeos"),
        transcript_dir=PROJECT_ROOT / os.getenv("TRANSCRIPT_DIR", "data/transcripts"),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini/gemini-2.5-flash"),
        gemini_embedding_model=os.getenv(
            "GEMINI_EMBEDDING_MODEL", "gemini/gemini-embedding-001"
        ),
        reasoning_effort=os.getenv("REASONING_EFFORT", "medium"),
        whisper_model=os.getenv("WHISPER_MODEL", "groq/whisper-large-v3-turbo"),
        whisper_language=os.getenv("WHISPER_LANGUAGE") or None,
        whisper_prompt=os.getenv("WHISPER_PROMPT") or None,
        whisper_response_format=os.getenv("WHISPER_RESPONSE_FORMAT", "verbose_json"),
        whisper_temperature=float(os.getenv("WHISPER_TEMPERATURE", "0")),
    )
    return _config
