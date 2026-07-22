"""Benchmark runner — two-phase orchestration of ingest → answer → judge.

LoCoMo answering is read-only and independent per question, so we split the run:

- **Phase 1 (ingest):** build each conversation's graph. Parallel across the 10
  conversations; each is an isolated store.
- **Phase 2 (answer):** a single global worker pool answers all ~2,000 questions
  across the already-built graphs. Questions no longer queue behind their
  conversation, so throughput scales with ``query_workers`` instead of being
  bounded by the largest conversation.

Connection safety: a query worker may touch any conversation's graph, so each
worker thread lazily builds its **own** answer-only adapter per graph
(``_AdapterPool``, thread-local). Adapters are never reset in phase 2 — that would
wipe the graph we just ingested.

The runner is system-agnostic: it is handed a ``make_system(graph_name)`` factory
returning a :class:`~bench.adapters.base.MemorySystem`.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from bench.adapters.base import IngestStats, MemorySystem
from bench.datasets.locomo import Conversation, Granularity, QAItem
from bench.harness import judge as judging
from bench.harness import metrics as M
from bench.harness.metrics import QuestionRecord
from bench.observability import LangfuseScorer

SystemFactory = Callable[[str], MemorySystem]
ProgressFn = Callable[[str], None]


class _AdapterPool:
    """Thread-local, answer-only adapters keyed by graph name (never reset)."""

    def __init__(self, make_system: SystemFactory) -> None:
        self._make = make_system
        self._local = threading.local()

    def get(self, graph_name: str) -> MemorySystem:
        cache: dict[str, MemorySystem] | None = getattr(self._local, "cache", None)
        if cache is None:
            cache = self._local.cache = {}
        if graph_name not in cache:
            cache[graph_name] = self._make(graph_name)
        return cache[graph_name]


def _ingest_phase(
    conversations: list[Conversation],
    *,
    make_system: SystemFactory,
    graph_prefix: str,
    granularity: Granularity,
    workers: int,
    progress: ProgressFn,
) -> tuple[dict[str, str], dict[str, IngestStats]]:
    """Build each conversation's graph. Returns sample_id -> graph_name / stats."""
    graph_names: dict[str, str] = {}
    stats_by_id: dict[str, IngestStats] = {}

    def _ingest(conv: Conversation) -> tuple[str, str, IngestStats]:
        graph_name = f"{graph_prefix}_{conv.sample_id}"
        system = make_system(graph_name)
        system.reset()
        stats = system.ingest(conv.to_episodes(granularity))
        progress(
            f"[{conv.sample_id}] ingested {stats.episodes} episodes "
            f"({stats.failures} failures)"
        )
        return conv.sample_id, graph_name, stats

    progress(
        f"Phase 1: ingesting {len(conversations)} conversations ({workers} workers)"
    )
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_ingest, c): c for c in conversations}
        for fut in as_completed(futures):
            conv = futures[fut]
            try:
                sample_id, graph_name, stats = fut.result()
                graph_names[sample_id] = graph_name
                stats_by_id[sample_id] = stats
            except Exception as e:  # a failed ingest drops that conversation
                progress(f"[{conv.sample_id}] INGEST FAILED: {e}")
    return graph_names, stats_by_id


def _answer_phase(
    conversations: list[Conversation],
    graph_names: dict[str, str],
    *,
    make_system: SystemFactory,
    judge_model: str,
    workers: int,
    scorer: LangfuseScorer,
    progress: ProgressFn,
) -> list[QuestionRecord]:
    """Answer + judge every question across the built graphs, in parallel."""
    pool_adapters = _AdapterPool(make_system)
    tasks: list[tuple[Conversation, QAItem]] = [
        (conv, qa)
        for conv in conversations
        if conv.sample_id in graph_names
        for qa in conv.qa
    ]

    def _answer(task: tuple[Conversation, QAItem]) -> QuestionRecord:
        conv, qa = task
        system = pool_adapters.get(graph_names[conv.sample_id])
        result = system.answer(qa.question, conv.query_time)
        verdict = judging.judge_answer(
            question=qa.question,
            gold=qa.answer,
            prediction=result.answer,
            is_adversarial=qa.is_adversarial,
            model=judge_model,
        )
        record = QuestionRecord(
            sample_id=conv.sample_id,
            category=qa.category,
            category_name=qa.category_name,
            question=qa.question,
            gold=qa.answer,
            prediction=result.answer,
            correct=verdict.correct,
            judge_reason=verdict.reason,
            is_adversarial=qa.is_adversarial,
            answer_prompt_tokens=result.usage.prompt_tokens,
            answer_completion_tokens=result.usage.completion_tokens,
            answer_total_tokens=result.usage.total_tokens,
            judge_total_tokens=verdict.usage.total_tokens,
            latency_ms=result.latency_ms,
            extra=result.extra,
            judge_error=verdict.error,
        )
        scorer.score(record)
        return record

    progress(f"Phase 2: answering {len(tasks)} questions ({workers} workers)")
    records: list[QuestionRecord] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_answer, t): t for t in tasks}
        for i, fut in enumerate(as_completed(futures), 1):
            try:
                records.append(fut.result())
            except Exception as e:  # one bad question must not sink the run
                conv, qa = futures[fut]
                progress(f"[{conv.sample_id}] ANSWER FAILED: {e}")
            if i % 100 == 0 or i == len(tasks):
                done = sum(r.correct for r in records)
                progress(f"  answered {i}/{len(tasks)} ({done} correct so far)")
    scorer.flush()
    return records


def run_benchmark(
    conversations: list[Conversation],
    *,
    make_system: SystemFactory,
    graph_prefix: str,
    granularity: Granularity,
    llm_model: str,
    judge_model: str,
    ingest_workers: int,
    query_workers: int,
    out_dir: Path,
    config: dict[str, Any],
    references: list[dict[str, Any]],
    scorer: LangfuseScorer,
    progress: ProgressFn = print,
) -> dict[str, Any]:
    """Execute the full benchmark and write artifacts. Returns the summary dict."""
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()

    graph_names, ingest_stats = _ingest_phase(
        conversations,
        make_system=make_system,
        graph_prefix=graph_prefix,
        granularity=granularity,
        workers=ingest_workers,
        progress=progress,
    )
    records = _answer_phase(
        conversations,
        graph_names,
        make_system=make_system,
        judge_model=judge_model,
        workers=query_workers,
        scorer=scorer,
        progress=progress,
    )

    summary = M.summarize(
        records,
        ingest_prompt_tokens=sum(s.usage.prompt_tokens for s in ingest_stats.values()),
        ingest_completion_tokens=sum(
            s.usage.completion_tokens for s in ingest_stats.values()
        ),
        ingest_latency_ms=sum(s.latency_ms for s in ingest_stats.values()),
        llm_model=llm_model,
        judge_model=judge_model,
    )
    summary["wall_clock_s"] = round(time.monotonic() - t0, 1)
    summary["ingest_failures"] = sum(s.failures for s in ingest_stats.values())

    # --- Artifacts ---
    with (out_dir / "results.jsonl").open("w") as f:
        for record in records:
            f.write(json.dumps(M.record_to_json(record)) + "\n")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    (out_dir / "config.json").write_text(json.dumps(config, indent=2))
    (out_dir / "summary.md").write_text(
        M.render_markdown(summary, config=config, references=references)
    )
    return summary
