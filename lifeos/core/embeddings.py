import litellm

from lifeos.core.config import get_config


def embed_text(text: str) -> list[float]:
    """Embed text for storage (RETRIEVAL_DOCUMENT task type)."""
    model = get_config().gemini_embedding_model
    response = litellm.embedding(
        model=model,
        input=[text],
        task_type="RETRIEVAL_DOCUMENT",
    )
    return response["data"][0]["embedding"]


def embed_query(text: str) -> list[float]:
    """Embed text for query-time (RETRIEVAL_QUERY task type)."""
    model = get_config().gemini_embedding_model
    response = litellm.embedding(
        model=model,
        input=[text],
        task_type="RETRIEVAL_QUERY",
    )
    return response["data"][0]["embedding"]
