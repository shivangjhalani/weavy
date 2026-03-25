from dataclasses import dataclass
from pathlib import Path
import os

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
    )
    return _config
