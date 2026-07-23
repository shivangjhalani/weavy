"""Benchmark CLI.

    # one-time: fetch the dataset
    python -m bench.run download

    # run the LoCoMo benchmark against Weavy on gpt-4o-mini
    python -m bench.run run --system weavy

    # themes-off ablation, fewer conversations for a smoke test
    python -m bench.run run --system weavy --no-themes --limit-conversations 1

Environment / models are configured here *before* ``weavy`` is imported, because
``weavy.config`` freezes settings at import time. We also enable
``litellm.drop_params`` so unsupported params (Weavy always sends
``reasoning_effort``, which gpt-4o-mini rejects) are silently dropped.

Provider credentials: set ``OPENAI_API_KEY`` (LiteLLM picks it up automatically).
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
DEFAULT_DATA = BENCH_DIR / "data" / "locomo10.json"
REPORTS_DIR = BENCH_DIR / "reports"
LOCOMO_URL = (
    "https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json"
)


def _download(args: argparse.Namespace) -> int:
    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading LoCoMo -> {dest}")
    urllib.request.urlretrieve(LOCOMO_URL, dest)
    size = dest.stat().st_size
    print(f"Done ({size:,} bytes).")
    return 0


def _make_weavy_factory(update_themes: bool, use_context: bool):
    from bench.adapters.weavy_adapter import WeavyAdapter

    def factory(graph_name: str):
        return WeavyAdapter(
            graph_name, update_themes=update_themes, use_context=use_context
        )

    return factory


# Registry — add mem0/graphiti factories here to benchmark them on the same harness.
def _build_factory(system: str, *, update_themes: bool, use_context: bool):
    if system == "weavy":
        return _make_weavy_factory(update_themes, use_context)
    raise SystemExit(
        f"Unknown system '{system}'. Available: weavy. "
        f"Add an adapter + a branch here to benchmark another system."
    )


def _run(args: argparse.Namespace) -> int:
    # 1) Configure models/env BEFORE any weavy import.
    os.environ["LLM_MODEL"] = args.llm_model
    os.environ["EMBEDDING_MODEL"] = args.embedding_model

    import litellm

    litellm.drop_params = True  # gpt-4o-mini rejects reasoning_effort; drop it

    # 2) Imports that (transitively) touch weavy config are safe now.
    from bench.datasets.locomo import load_locomo
    from bench.harness.runner import run_benchmark
    from bench.observability import LangfuseScorer, langfuse_configured
    from bench.reference import REFERENCE_LINES

    conversations = load_locomo(args.data)
    if args.limit_conversations:
        conversations = conversations[: args.limit_conversations]
    if args.limit_questions:
        for i, c in enumerate(conversations):
            object.__setattr__(c, "qa", c.qa[: args.limit_questions])

    langfuse_on = not args.no_langfuse and langfuse_configured()
    n_q = sum(len(c.qa) for c in conversations)
    print(
        f"Loaded {len(conversations)} conversations, {n_q} questions. "
        f"LLM={args.llm_model} embed={args.embedding_model} judge={args.judge_model} "
        f"themes={'on' if not args.no_themes else 'off'} "
        f"context={'on' if not args.no_context else 'off'} "
        f"langfuse={'on' if langfuse_on else 'off'} "
        f"ingest_workers={args.ingest_workers} query_workers={args.query_workers}"
    )

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    label = f"{args.system}_{'nothemes' if args.no_themes else 'themes'}"
    out_dir = Path(args.out_dir or (REPORTS_DIR / f"{run_id}_{label}"))

    config = {
        "run_id": run_id,
        "system": args.system,
        "dataset": "locomo",
        "n_conversations": len(conversations),
        "n_questions": n_q,
        "granularity": args.granularity,
        "themes": not args.no_themes,
        "caller_context": not args.no_context,
        "langfuse": langfuse_on,
        "llm_model": args.llm_model,
        "embedding_model": args.embedding_model,
        "judge_model": args.judge_model,
        "ingest_workers": args.ingest_workers,
        "query_workers": args.query_workers,
    }

    scorer = LangfuseScorer.create(
        enabled=langfuse_on, bench_run_id=run_id, run_config=config
    )
    factory = _build_factory(
        args.system, update_themes=not args.no_themes, use_context=not args.no_context
    )
    summary = run_benchmark(
        conversations,
        make_system=factory,
        graph_prefix=f"bench_{run_id}",
        granularity=args.granularity,
        llm_model=args.llm_model,
        judge_model=args.judge_model,
        ingest_workers=args.ingest_workers,
        query_workers=args.query_workers,
        out_dir=out_dir,
        config=config,
        references=REFERENCE_LINES,
        scorer=scorer,
        ingest_only=args.ingest_only,
        reuse_prefix=args.reuse_graphs,
    )

    if args.ingest_only:
        print(f"\nIngest-only run complete. Graphs: bench_{run_id}_<sample_id>")
        print(f"Reports written to: {out_dir}")
        return 0

    print("\n=== Summary ===")
    print(f"Overall recall accuracy: {summary['overall_recall_accuracy']:.1%}")
    for name, row in summary["by_category"].items():
        print(f"  {name:12s} {row['accuracy']:.1%}  (n={row['n']})")
    if summary["adversarial_abstention_accuracy"] is not None:
        print(
            f"  adversarial  {summary['adversarial_abstention_accuracy']:.1%}  (abstention)"
        )
    print(f"Answer tokens/question: {summary['tokens']['answer_per_question']}")
    print(
        f"Total cost: ${summary['cost_usd']['total']}  |  wall-clock: {summary['wall_clock_s']}s"
    )
    print(f"\nReports written to: {out_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bench", description="Weavy memory benchmark")
    sub = parser.add_subparsers(dest="command", required=True)

    p_dl = sub.add_parser("download", help="download locomo10.json")
    p_dl.add_argument("--out", default=str(DEFAULT_DATA))
    p_dl.set_defaults(func=_download)

    p_run = sub.add_parser("run", help="run the benchmark")
    p_run.add_argument("--system", default="weavy")
    p_run.add_argument("--data", default=str(DEFAULT_DATA))
    p_run.add_argument("--out-dir", default=None, help="override report directory")
    p_run.add_argument(
        "--granularity", choices=["session", "turn", "conversation"], default="session"
    )
    p_run.add_argument("--no-themes", action="store_true", help="themes-off ablation")
    p_run.add_argument(
        "--no-context", action="store_true", help="skip caller_context at ingest"
    )
    p_run.add_argument(
        "--no-langfuse", action="store_true", help="disable Langfuse eval scoring"
    )
    p_run.add_argument("--llm-model", default="gpt-4o-mini")
    p_run.add_argument("--embedding-model", default="text-embedding-3-small")
    p_run.add_argument("--judge-model", default="gpt-4o-mini")
    p_run.add_argument(
        "--ingest-workers",
        type=int,
        default=10,
        help="conversations ingested in parallel",
    )
    p_run.add_argument(
        "--query-workers", type=int, default=16, help="questions answered in parallel"
    )
    p_run.add_argument("--limit-conversations", type=int, default=0)
    p_run.add_argument(
        "--limit-questions", type=int, default=0, help="per conversation"
    )
    p_run.add_argument(
        "--ingest-only",
        action="store_true",
        help="stop after phase 1 (build graphs, skip answering)",
    )
    p_run.add_argument(
        "--reuse-graphs",
        default=None,
        metavar="PREFIX",
        help="skip ingest; answer against existing graphs named PREFIX_<sample_id>",
    )
    p_run.set_defaults(func=_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
