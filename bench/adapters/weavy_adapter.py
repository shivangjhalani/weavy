"""Weavy adapter — the only bench module that imports ``weavy``.

Maps the harness contract onto the public Weavy SDK:

- ``reset``  -> ``Weavy.reset()``           (drop + reinit the named graph)
- ``ingest`` -> ``Weavy.add()`` per episode (session-date as event timestamp)
- ``answer`` -> ``Weavy.query(query_time=)`` (replay the question at a fixed time)

``weavy`` is imported lazily inside ``__init__`` so the CLI can set model/env
configuration *before* ``weavy.config`` is imported and frozen.
"""

from __future__ import annotations

import time
from datetime import datetime

from bench.adapters.base import AnswerResult, Episode, IngestStats, Usage

# Answer-format instruction passed as query context. LoCoMo gold answers are terse
# facts and the standard harness prompts the answerer to be concise, so this keeps
# Weavy comparable and scores memory rather than verbosity. It steers output
# format only — it does not hint at any answer.
_ANSWER_INSTRUCTION = (
    "Answer as concisely as possible with only the specific fact(s) asked for — "
    "a few words, a name, or a date. Do not explain, justify, or add context. If "
    "the memory has no answer, say so briefly."
)


def _usage_of(trace) -> Usage:
    """Sum per-turn token usage from a RunTrace (robust to total_usage gaps)."""
    u = Usage()
    for turn in trace.turns:
        tu = turn.usage
        u = u + Usage(
            prompt_tokens=tu.prompt_tokens,
            completion_tokens=tu.completion_tokens,
            total_tokens=tu.total_tokens,
        )
    return u


class WeavyAdapter:
    """Benchmark adapter around :class:`weavy.Weavy`."""

    def __init__(
        self,
        graph_name: str,
        *,
        update_themes: bool = True,
        use_context: bool = True,
        answer_instruction: str | None = _ANSWER_INSTRUCTION,
    ) -> None:
        import weavy  # lazy: env/model config must be set before this import

        self.name = "weavy"
        self._update_themes = update_themes
        self._use_context = use_context
        self._answer_instruction = answer_instruction
        self._w = weavy.Weavy(graph_name)

    def reset(self) -> None:
        self._w.reset()

    def ingest(self, episodes: list[Episode]) -> IngestStats:
        stats = IngestStats(episodes=len(episodes))
        t0 = time.monotonic()
        for ep in episodes:
            trace = self._w.add(
                ep.text,
                timestamp=ep.timestamp,
                context=ep.context if self._use_context else None,
                update_themes=self._update_themes,
            )
            stats.usage = stats.usage + _usage_of(trace)
            if trace.status != "completed":
                stats.failures += 1
        stats.latency_ms = (time.monotonic() - t0) * 1000
        return stats

    def answer(self, question: str, at: datetime) -> AnswerResult:
        t0 = time.monotonic()
        trace = self._w.query(question, context=self._answer_instruction, query_time=at)
        latency_ms = (time.monotonic() - t0) * 1000

        payload = trace.completion_payload or {}
        answer = (payload.get("answer") or "").strip()
        if trace.status != "completed" and not answer:
            answer = ""  # treated as an abstention / miss by the judge

        return AnswerResult(
            answer=answer,
            usage=_usage_of(trace),
            latency_ms=latency_ms,
            extra={
                "status": trace.status,
                "turns": len(trace.turns),
                "consulted_nodes": payload.get("consulted_nodes", []),
                "cited_sources": payload.get("cited_sources", []),
                "error": trace.error,
                # Weavy sets the Langfuse trace_id == run_id (tracing.py), so this
                # links each benchmark record to its agent trace for observability.
                "trace_id": trace.run_id,
            },
        )
