"""
Shared Langfuse client access.

The client is created lazily so importing tracing or prompt helpers does not
eagerly initialize the SDK during unrelated code paths.
"""

from functools import lru_cache

from langfuse import Langfuse

from arakne.config import settings


@lru_cache(maxsize=1)
def get_langfuse() -> Langfuse:
    return Langfuse(
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        secret_key=settings.LANGFUSE_SECRET_KEY,
        base_url=settings.LANGFUSE_HOST,
    )
