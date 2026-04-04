import os

from dotenv import load_dotenv

load_dotenv()


def _getenv(name: str, default: str, *, alias: str | None = None) -> str:
    value = os.getenv(name)
    if value is not None:
        return value
    if alias is not None:
        alias_value = os.getenv(alias)
        if alias_value is not None:
            return alias_value
    return default


class Settings:
    FALKORDB_HOST: str = _getenv("FALKORDB_HOST", "localhost")
    FALKORDB_PORT: int = int(_getenv("FALKORDB_PORT", "6379"))
    GRAPH_NAME: str = _getenv("GRAPH_NAME", "arakne")

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

    LANGFUSE_HOST: str = _getenv(
        "LANGFUSE_HOST",
        "http://localhost:3100",
        alias="LANGFUSE_BASE_URL",
    )
    LANGFUSE_PUBLIC_KEY: str = _getenv("LANGFUSE_PUBLIC_KEY", "")
    LANGFUSE_SECRET_KEY: str = _getenv("LANGFUSE_SECRET_KEY", "")


settings = Settings()
