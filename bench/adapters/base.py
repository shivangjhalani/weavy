"""The adapter contract every benchmarked memory system implements.

This is the *entire* coupling surface between the harness and any memory system.
The harness speaks only ``Episode`` / ``AnswerResult`` / ``IngestStats`` and the
three-method :class:`MemorySystem` protocol. To benchmark a new system, write a
module that satisfies this protocol — no harness changes required.

Design notes
------------
- ``ingest`` takes the whole episode list so an adapter is free to batch, stream,
  or parallelise internally however its system prefers.
- Token/latency fields are optional-by-default (0.0) so a system that does not
  expose usage still works; cost/efficiency metrics simply read as zero for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class Episode:
    """One unit of memory to ingest, with the time it occurred."""

    text: str
    timestamp: datetime
    context: str | None = None


@dataclass
class Usage:
    """LLM token accounting for a single operation (additive)."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


@dataclass
class IngestStats:
    """Outcome of ingesting a conversation's episodes."""

    episodes: int = 0
    usage: Usage = field(default_factory=Usage)
    latency_ms: float = 0.0
    failures: int = 0


@dataclass
class AnswerResult:
    """A system's answer to one question, plus observability metadata."""

    answer: str
    usage: Usage = field(default_factory=Usage)
    latency_ms: float = 0.0
    # Free-form, system-specific detail surfaced into per-question records for
    # error analysis (e.g. Weavy's touched/consulted nodes, retrieved ids).
    extra: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class MemorySystem(Protocol):
    """A memory layer under test.

    Lifecycle per conversation: ``reset()`` → ``ingest(episodes)`` →
    ``answer(...)`` for each question. Implementations should keep each instance
    bound to an isolated store (e.g. a named graph) so conversations cannot leak
    into one another.
    """

    name: str

    def reset(self) -> None:
        """Drop all memory and return to a clean, initialised state."""
        ...

    def ingest(self, episodes: list[Episode]) -> IngestStats:
        """Load episodes into memory, in chronological order."""
        ...

    def answer(self, question: str, at: datetime) -> AnswerResult:
        """Answer ``question`` as if asked at time ``at``."""
        ...
