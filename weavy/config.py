import os

from dotenv import load_dotenv

load_dotenv()


def _clean_env_value(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned = value.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _getenv(name: str, default: str, *, alias: str | None = None) -> str:
    value = _clean_env_value(os.getenv(name))
    if value is not None:
        return value
    if alias is not None:
        alias_value = _clean_env_value(os.getenv(alias))
        if alias_value is not None:
            return alias_value
    return default


def _langfuse_host() -> str:
    host = _getenv(
        "LANGFUSE_HOST",
        "http://localhost:3100",
        alias="LANGFUSE_BASE_URL",
    )
    if "://" not in host:
        return f"http://{host}"
    return host


class Settings:
    FALKORDB_HOST: str = _getenv("FALKORDB_HOST", "localhost")
    FALKORDB_PORT: int = int(_getenv("FALKORDB_PORT", "6379"))
    GRAPH_NAME: str = _getenv("GRAPH_NAME", "weavy")

    GEMINI_MODEL: str = _getenv("GEMINI_MODEL", "gemini/gemini-2.5-flash")
    REASONING_EFFORT: str = _getenv("REASONING_EFFORT", "medium")
    GEMINI_EMBEDDING_MODEL: str = _getenv(
        "GEMINI_EMBEDDING_MODEL",
        "gemini/gemini-embedding-001",
    )

    LOG_TOKEN_BUDGET: int = int(_getenv("LOG_TOKEN_BUDGET", "2000"))
    HOT_THEME_TOKEN_BUDGET: int = int(_getenv("HOT_THEME_TOKEN_BUDGET", "250"))

    WHISPER_MODEL: str = _getenv("WHISPER_MODEL", "groq/whisper-large-v3-turbo")
    WHISPER_LANGUAGE: str = _getenv("WHISPER_LANGUAGE", "")
    WHISPER_PROMPT: str = _getenv("WHISPER_PROMPT", "")
    WHISPER_TEMPERATURE: float = float(_getenv("WHISPER_TEMPERATURE", "0"))

    LANGFUSE_HOST: str = _langfuse_host()
    LANGFUSE_PUBLIC_KEY: str = _getenv("LANGFUSE_PUBLIC_KEY", "")
    LANGFUSE_SECRET_KEY: str = _getenv("LANGFUSE_SECRET_KEY", "")


settings = Settings()
