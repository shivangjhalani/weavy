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


@lru_cache(maxsize=1)
def get_max_input_tokens() -> int:
    info = litellm.get_model_info(settings.EMBEDDING_MODEL)
    max_tokens = info.get("max_input_tokens")
    if max_tokens is None:
        raise RuntimeError(
            f"litellm has no max_input_tokens for {settings.EMBEDDING_MODEL!r}"
        )
    return int(max_tokens)


# No embedding model exposes a public tokenizer via litellm generically, so an
# exact token count isn't available here (prompts.py faces the same gap and
# uses cl100k_base as an approximation for a different model family). This
# ratio is a deliberately conservative stand-in, not a measurement — it only
# needs to keep embed() calls under the model's real limit, never to be exact.
_CHARS_PER_TOKEN_ESTIMATE = 3


def get_char_budget() -> int:
    """Conservative character budget for one embed() call, derived from the
    configured embedding model's real max_input_tokens — not a guess."""
    return get_max_input_tokens() * _CHARS_PER_TOKEN_ESTIMATE


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
    retrievable after the summary moves on. Notes are packed newest-first until
    the model's real input budget fills, so history is never cut by an
    arbitrary count — the newest note (the one just being written) always
    survives, and older notes drop off first when space runs out.
    """
    header = " | ".join(aliases) + " — " + summary
    budget = get_char_budget()
    remaining = budget - len(header)

    packed: list[str] = []
    if notes and remaining > 0:
        used = 0
        for note in reversed(notes):
            cost = len(note) + 1  # +1 for the joining newline
            if used + cost > remaining:
                break
            packed.append(note)
            used += cost
        packed.reverse()

    text = header
    if packed:
        text += "\n" + "\n".join(packed)
    return embed(text[:budget])


def embed_edge(label: str, fact: str) -> list[float]:
    return embed(f"{label} — {fact}")
