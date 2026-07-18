"""Embedding utilities — thin wrapper around LiteLLM for vector operations."""

from functools import lru_cache

import litellm

from weavy.config import settings


@lru_cache(maxsize=1)
def get_dimension() -> int:
    info = litellm.get_model_info(settings.EMBEDDING_MODEL)
    dim = info.get("output_vector_size")
    if dim is None:
        raise RuntimeError(
            f"litellm has no output_vector_size for {settings.EMBEDDING_MODEL!r}"
        )
    return int(dim)


def embed(text: str) -> list[float]:
    response = litellm.embedding(
        model=settings.EMBEDDING_MODEL,
        input=[text],
    )
    return response.data[0]["embedding"]


def embed_node(
    aliases: list[str], summary: str, notes: list[str] | None = None
) -> list[float]:
    """Embed a node's accumulated knowledge, not just its current summary.

    Log notes carry the facts that earlier summaries held (updates archive the
    prior summary into the log) — folding them into the vector keeps past facts
    retrievable after the summary moves on.
    """
    text = " | ".join(aliases) + " — " + summary
    if notes:
        text += "\n" + "\n".join(notes)
    return embed(text[:6000])


def embed_edge(label: str, fact: str) -> list[float]:
    return embed(f"{label} — {fact}")
