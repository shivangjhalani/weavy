import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    FALKORDB_HOST: str = os.getenv("FALKORDB_HOST", "localhost")
    FALKORDB_PORT: int = int(os.getenv("FALKORDB_PORT", "6379"))
    GRAPH_NAME: str = os.getenv("GRAPH_NAME", "arakne")

    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini/gemini-2.5-flash")
    REASONING_EFFORT: str = os.getenv("REASONING_EFFORT", "medium")
    GEMINI_EMBEDDING_MODEL: str = os.getenv(
        "GEMINI_EMBEDDING_MODEL", "gemini/gemini-embedding-001"
    )

    LOG_TOKEN_BUDGET: int = int(os.getenv("LOG_TOKEN_BUDGET", "2000"))
    HOT_THEME_TOKEN_BUDGET: int = int(os.getenv("HOT_THEME_TOKEN_BUDGET", "250"))

    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "groq/whisper-large-v3-turbo")
    WHISPER_LANGUAGE: str = os.getenv("WHISPER_LANGUAGE", "")
    WHISPER_PROMPT: str = os.getenv("WHISPER_PROMPT", "")
    WHISPER_TEMPERATURE: float = float(os.getenv("WHISPER_TEMPERATURE", "0"))


settings = Settings()
