from google import genai
from google.genai import types

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client()
    return _client


def embed_text(text: str) -> list[float]:
    """Embed text for storage (RETRIEVAL_DOCUMENT task type). Returns 3072-dim vector."""
    result = _get_client().models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
    )
    return result.embeddings[0].values


def embed_query(text: str) -> list[float]:
    """Embed text for query-time (RETRIEVAL_QUERY task type). Returns 3072-dim vector."""
    result = _get_client().models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
    )
    return result.embeddings[0].values
