"""Optional Langfuse eval-scoring layer.

Weavy already emits a full agent trace per ``add``/``query`` when Langfuse is
configured. This module adds the missing eval half: it attaches the judge verdict
and efficiency numbers as **scores** to each query's trace, so in Langfuse you can
filter traces by ``correct = 0`` and ``category = multi_hop`` and click straight
into the agent run that produced a wrong answer.

Design constraints:
- **No Weavy import.** We construct our own Langfuse client from the standard
  ``LANGFUSE_*`` env vars and link scores by ``trace_id`` (which Weavy sets equal
  to the run id). The harness stays system-agnostic.
- **Graceful no-op.** Disabled, missing keys, a record without a ``trace_id``
  (e.g. a non-Weavy adapter), or any Langfuse error must never break a run.

Scores written per question (all stamped with ``bench_run_id`` / ``category`` in
score metadata for grouping and filtering):

- ``correct``            NUMERIC 0/1  — the LoCoMo "J" verdict (comment = reason)
- ``category``           CATEGORICAL  — single_hop / multi_hop / temporal / ...
- ``answer_tokens``      NUMERIC      — retrieval+answer tokens for the question
- ``answer_latency_ms``  NUMERIC      — wall-clock latency of the answer
- ``judge_error``        NUMERIC 1    — only when the judge call itself failed
"""

from __future__ import annotations

import os
from typing import Any

from bench.harness.metrics import QuestionRecord


def langfuse_configured() -> bool:
    return bool(
        os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")
    )


class LangfuseScorer:
    """Attaches eval scores to existing Weavy traces. Safe to call always."""

    def __init__(self, *, bench_run_id: str, run_config: dict[str, Any]) -> None:
        self._bench_run_id = bench_run_id
        self._run_config = run_config
        self._lf: Any = None
        self._warned = False

    @classmethod
    def create(
        cls,
        *,
        enabled: bool,
        bench_run_id: str,
        run_config: dict[str, Any],
    ) -> "LangfuseScorer":
        scorer = cls(bench_run_id=bench_run_id, run_config=run_config)
        if enabled and langfuse_configured():
            try:
                from langfuse import Langfuse

                scorer._lf = Langfuse()  # reads LANGFUSE_* from env
            except Exception as e:  # pragma: no cover - env dependent
                print(f"[langfuse] disabled (init failed: {e})")
        return scorer

    @property
    def active(self) -> bool:
        return self._lf is not None

    def score(self, record: QuestionRecord) -> None:
        """Push scores for one graded question to its trace (best-effort)."""
        trace_id = record.extra.get("trace_id") if record.extra else None
        if self._lf is None or not trace_id:
            return

        meta = {
            "bench_run_id": self._bench_run_id,
            "category": record.category_name,
            "sample_id": record.sample_id,
            "is_adversarial": record.is_adversarial,
            "themes": self._run_config.get("themes"),
        }
        try:
            self._lf.create_score(
                name="correct",
                value=1.0 if record.correct else 0.0,
                trace_id=trace_id,
                data_type="NUMERIC",
                comment=record.judge_reason or None,
                metadata=meta,
            )
            self._lf.create_score(
                name="category",
                value=record.category_name,
                trace_id=trace_id,
                data_type="CATEGORICAL",
                metadata=meta,
            )
            self._lf.create_score(
                name="answer_tokens",
                value=float(record.answer_total_tokens),
                trace_id=trace_id,
                data_type="NUMERIC",
                metadata=meta,
            )
            if record.latency_ms:
                self._lf.create_score(
                    name="answer_latency_ms",
                    value=float(record.latency_ms),
                    trace_id=trace_id,
                    data_type="NUMERIC",
                    metadata=meta,
                )
            if record.judge_error:
                self._lf.create_score(
                    name="judge_error",
                    value=1.0,
                    trace_id=trace_id,
                    data_type="NUMERIC",
                    comment=record.judge_error,
                    metadata=meta,
                )
        except Exception as e:
            if not self._warned:
                print(f"[langfuse] scoring error (further warnings suppressed): {e}")
                self._warned = True

    def flush(self) -> None:
        if self._lf is not None:
            try:
                self._lf.flush()
            except Exception:
                pass
