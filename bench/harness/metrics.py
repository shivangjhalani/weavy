"""Aggregation, cost, and the human-readable summary.

Turns the flat list of per-question records into the numbers that tell the story:
accuracy per category, an overall recall score (adversarial excluded, matching
the convention most papers use), a separate abstention score for adversarial,
plus token / cost / latency efficiency.

Cost is computed from tracked LLM tokens against a small, transparent price
table. Embedding tokens are not tracked by the memory system's traces and are
negligible on these models, so reported cost is LLM completion + judge only.
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from typing import Any

# USD per 1M tokens (input, output). Extend as you add models/systems.
PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "text-embedding-3-small": (0.02, 0.0),
}

# Categories that count toward the headline recall accuracy.
RECALL_CATEGORIES = ("multi_hop", "temporal", "open_domain", "single_hop")


@dataclass
class QuestionRecord:
    """One graded question — the unit written to results.jsonl."""

    sample_id: str
    category: int
    category_name: str
    question: str
    gold: str
    prediction: str
    correct: bool
    judge_reason: str
    is_adversarial: bool
    answer_prompt_tokens: int = 0
    answer_completion_tokens: int = 0
    answer_total_tokens: int = 0
    judge_total_tokens: int = 0
    latency_ms: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)
    judge_error: str | None = None


def _cost(prompt: int, completion: int, model: str) -> float:
    pin, pout = PRICES.get(model, (0.0, 0.0))
    return (prompt * pin + completion * pout) / 1_000_000


def _acc(records: list[QuestionRecord]) -> float:
    return sum(r.correct for r in records) / len(records) if records else 0.0


def summarize(
    records: list[QuestionRecord],
    *,
    ingest_prompt_tokens: int,
    ingest_completion_tokens: int,
    ingest_latency_ms: float,
    llm_model: str,
    judge_model: str,
) -> dict[str, Any]:
    """Compute the full metrics dict for a run."""
    recall = [r for r in records if not r.is_adversarial]
    adversarial = [r for r in records if r.is_adversarial]

    by_category = {}
    for name in RECALL_CATEGORIES:
        rows = [r for r in recall if r.category_name == name]
        if rows:
            by_category[name] = {"accuracy": round(_acc(rows), 4), "n": len(rows)}

    ans_prompt = sum(r.answer_prompt_tokens for r in records)
    ans_completion = sum(r.answer_completion_tokens for r in records)
    judge_tokens = sum(r.judge_total_tokens for r in records)
    latencies = [r.latency_ms for r in records if r.latency_ms]

    answer_cost = _cost(ans_prompt, ans_completion, llm_model)
    ingest_cost = _cost(ingest_prompt_tokens, ingest_completion_tokens, llm_model)
    # Judge tokens are mostly input; approximate input/output split is unknown so
    # charge them at the input rate (conservative, dominates anyway).
    judge_cost = _cost(judge_tokens, 0, judge_model)

    n_answer = max(len(records), 1)
    return {
        "n_questions": len(records),
        "overall_recall_accuracy": round(_acc(recall), 4),
        "by_category": by_category,
        "adversarial_abstention_accuracy": round(_acc(adversarial), 4)
        if adversarial
        else None,
        "adversarial_n": len(adversarial),
        "tokens": {
            "ingest_total": ingest_prompt_tokens + ingest_completion_tokens,
            "answer_total": ans_prompt + ans_completion,
            "answer_per_question": round((ans_prompt + ans_completion) / n_answer, 1),
            "judge_total": judge_tokens,
        },
        "latency_ms": {
            "answer_p50": round(statistics.median(latencies), 1) if latencies else None,
            "answer_p95": round(_pct(latencies, 95), 1) if latencies else None,
            "ingest_total": round(ingest_latency_ms, 1),
        },
        "cost_usd": {
            "ingest": round(ingest_cost, 4),
            "answer": round(answer_cost, 4),
            "judge": round(judge_cost, 4),
            "total": round(ingest_cost + answer_cost + judge_cost, 4),
        },
    }


def _pct(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * (pct / 100)
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def render_markdown(
    summary: dict[str, Any],
    *,
    config: dict[str, Any],
    references: list[dict[str, Any]],
) -> str:
    """Render the summary + published reference lines as a Markdown report."""
    lines: list[str] = ["# LoCoMo benchmark — summary\n"]

    lines.append("## Configuration\n")
    for k, v in config.items():
        lines.append(f"- **{k}**: {v}")
    lines.append("")

    lines.append("## Accuracy by category (LLM-judge / J score)\n")
    lines.append("| Category | Accuracy | n |")
    lines.append("|---|---|---|")
    for name, row in summary["by_category"].items():
        lines.append(f"| {name} | {row['accuracy']:.1%} | {row['n']} |")
    lines.append(
        f"| **overall (recall)** | **{summary['overall_recall_accuracy']:.1%}** "
        f"| {summary['n_questions'] - summary['adversarial_n']} |"
    )
    if summary["adversarial_abstention_accuracy"] is not None:
        lines.append(
            f"| _adversarial (abstention)_ | {summary['adversarial_abstention_accuracy']:.1%} "
            f"| {summary['adversarial_n']} |"
        )
    lines.append("")

    eff = summary["tokens"]
    cost = summary["cost_usd"]
    lat = summary["latency_ms"]
    lines.append("## Efficiency\n")
    lines.append(f"- **Answer tokens / question**: {eff['answer_per_question']}")
    lines.append(f"- **Ingest tokens (total)**: {eff['ingest_total']:,}")
    lines.append(
        f"- **Answer latency**: p50 {lat['answer_p50']} ms · p95 {lat['answer_p95']} ms"
    )
    lines.append(
        f"- **Cost (USD)**: ingest ${cost['ingest']} · answer ${cost['answer']} · "
        f"judge ${cost['judge']} · **total ${cost['total']}**"
    )
    lines.append("")

    if references:
        lines.append("## Published reference lines\n")
        lines.append(
            "> Self-reported, run on different harnesses/SDK versions. Treat as "
            "fuzzy context (±10pts is normal for this benchmark), not head-to-head.\n"
        )
        lines.append("| System | Metric | Score | Source |")
        lines.append("|---|---|---|---|")
        for r in references:
            lines.append(
                f"| {r['system']} | {r['metric']} | {r['score']} | {r['source']} |"
            )
        lines.append("")

    return "\n".join(lines)


def record_to_json(record: QuestionRecord) -> dict[str, Any]:
    return asdict(record)
