#!/usr/bin/env python3
"""
Weavy / LongMemEval evaluation harness — Langfuse Datasets + Experiments.

    uv run eval/eval.py upload  --dataset oracle
    uv run eval/eval.py run     --dataset oracle  [--limit N] [--judge-model MODEL]
    uv run eval/eval.py status  --dataset oracle
    uv run eval/eval.py metrics --dataset oracle
    uv run eval/eval.py reset   --dataset oracle  [--all] [--force]

Datasets (place in eval/data/):
    oracle  — evidence sessions only (~3-5 sessions/instance)   easiest
    s       — ~40 sessions / ~115k tokens per instance          medium
    m       — ~500 sessions per instance                        hardest

Upload pushes LongMemEval instances into Langfuse as dataset items.
Run executes experiments via Langfuse's experiment runner, with built-in
LLM-as-judge evaluation and aggregate metrics.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

EVAL_DIR = Path(__file__).parent

DATASET_FILES: dict[str, Path] = {
    "oracle": EVAL_DIR / "data" / "longmemeval_oracle.json",
    "s":      EVAL_DIR / "data" / "longmemeval_s.json",
    "m":      EVAL_DIR / "data" / "longmemeval_m.json",
}

EVAL_GRAPH = "longmemeval"

SEP = "─" * 54
DEFAULT_JUDGE_MODEL = "gemini/gemini-2.5-flash-lite"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_dataset(args: argparse.Namespace) -> tuple[Path, str]:
    data_override = getattr(args, "data", None)
    if data_override:
        p = Path(data_override)
        name = p.stem.removeprefix("longmemeval_") or p.stem
        return p, name
    ds = getattr(args, "dataset", "oracle")
    return DATASET_FILES[ds], ds


def _langfuse_dataset_name(ds_name: str) -> str:
    return f"longmemeval/{ds_name}"


def _load_data(path: Path) -> list[dict]:
    if not path.exists():
        print(f"[error] data file not found: {path}")
        print("        Download from https://github.com/xiaowu0162/longmemeval")
        print("        and place in eval/data/ as:")
        for k, v in DATASET_FILES.items():
            print(f"          {v.name}   (--dataset {k})")
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def _parse_date(s: str) -> datetime:
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d", "%Y/%m/%d (%a) %H:%M"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    raise ValueError(f"Cannot parse date: {s!r}")


def _format_session(turns: list[dict], date: str) -> str:
    lines = [f"[{date}]"]
    for turn in turns:
        role = "User" if turn["role"] == "user" else "Assistant"
        lines.append(f"{role}: {turn['content']}")
    return "\n".join(lines)


def _pct(num: int, denom: int) -> str:
    return f"{num / denom * 100:.1f}%" if denom > 0 else "—"


def _bar(ratio: float, width: int = 20) -> str:
    filled = round(ratio * width)
    return "█" * filled + "░" * (width - filled)


def _add_dataset_args(p: argparse.ArgumentParser, *, need_data_file: bool = False) -> None:
    group = p.add_mutually_exclusive_group()
    group.add_argument(
        "--dataset", choices=["oracle", "s", "m"], default="oracle", metavar="{oracle,s,m}",
        help="Dataset variant to use (default: oracle)",
    )
    if need_data_file:
        group.add_argument(
            "--data", default=None, metavar="PATH",
            help="Explicit path to a LongMemEval JSON file (overrides --dataset)",
        )


def _get_langfuse():
    from weavy.langfuse_client import get_langfuse
    return get_langfuse()


# ---------------------------------------------------------------------------
# upload — push LongMemEval instances into Langfuse as dataset items
# ---------------------------------------------------------------------------

def cmd_upload(args: argparse.Namespace) -> None:
    data_path, ds_name = _resolve_dataset(args)
    data = _load_data(data_path)
    lf_ds_name = _langfuse_dataset_name(ds_name)
    lf = _get_langfuse()

    lf.create_dataset(
        name=lf_ds_name,
        description=f"LongMemEval {ds_name} — {len(data)} instances",
        metadata={
            "benchmark": "longmemeval",
            "variant": ds_name,
            "source_file": data_path.name,
            "instance_count": len(data),
        },
    )

    print(f"{SEP}")
    print(f"  Upload LongMemEval → Langfuse  [{ds_name}]")
    print(f"{SEP}")
    print(f"  Dataset    : {lf_ds_name}")
    print(f"  Instances  : {len(data)}")
    print(f"  Source     : {data_path}")
    print(f"{SEP}\n")

    for i, instance in enumerate(data, 1):
        qid = instance["question_id"]
        qtype = instance["question_type"]

        lf.create_dataset_item(
            dataset_name=lf_ds_name,
            id=f"{ds_name}:{qid}",
            input={
                "question_id": qid,
                "question": instance["question"],
                "question_date": instance["question_date"],
                "haystack_sessions": instance["haystack_sessions"],
                "haystack_dates": instance["haystack_dates"],
            },
            expected_output={
                "answer": instance["answer"],
                "question_type": qtype,
                "abstention": "_abs" in qid,
            },
            metadata={
                "question_type": qtype,
                "num_sessions": len(instance["haystack_sessions"]),
            },
        )

        if i % 50 == 0 or i == len(data):
            print(f"  uploaded {i}/{len(data)}")

    lf.flush()
    print(f"\n  Done. Dataset '{lf_ds_name}' ready in Langfuse.")


# ---------------------------------------------------------------------------
# run — execute experiment via Langfuse experiment runner
# ---------------------------------------------------------------------------

def _run_single_item(
    item,
    idx: int,
    total: int,
    graph_name: str,
    ds_name: str,
    judge_model: str,
    print_lock,
) -> dict:
    """Execute one eval instance on a dedicated graph. Thread-safe."""
    from weavy.application.session_runs import run_add, run_query
    from weavy.application.theme_runs import run_theme_update
    from weavy.services.embedding import get_dimension
    from weavy.store.client import delete_graph_if_exists, get_graph
    from weavy.store.system import init_system

    from evaluate_qa import get_anscheck_prompt, _judge_call

    inp = item.input
    expected = item.expected_output
    qid = inp["question_id"]
    qtype = expected["question_type"]
    sessions = inp["haystack_sessions"]
    dates = inp["haystack_dates"]
    n_sessions = len(sessions)
    abstention = expected.get("abstention", False)

    graph = get_graph(graph_name)
    delete_graph_if_exists(graph)
    init_system(graph, embedding_dim=get_dimension())

    # ---- Ingest sessions + theme update after each ----
    for turns, date in zip(sessions, dates):
        text = _format_session(turns, date)
        ts = _parse_date(date)
        ingest_trace = run_add(text, graph, timestamp=ts)
        if ingest_trace.status == "completed":
            run_theme_update(graph)

    # ---- Query ----
    question_dt = _parse_date(inp["question_date"])
    query_trace = run_query(inp["question"], graph, query_time=question_dt)
    hypothesis = (query_trace.completion_payload or {}).get("answer", "")
    trace_id = query_trace.run_id

    # ---- LLM-as-judge ----
    if hypothesis:
        prompt = get_anscheck_prompt(
            qtype, inp["question"], expected["answer"], hypothesis, abstention,
        )
        raw = _judge_call(judge_model, prompt)
        correct = "yes" in raw.lower()
    else:
        raw = "no hypothesis"
        correct = False

    # ---- Post scores to Langfuse ----
    lf = _get_langfuse()
    lf.create_score(
        trace_id=trace_id,
        name="longmemeval/correct",
        value=1.0 if correct else 0.0,
        data_type="BOOLEAN",
        comment=f"dataset={ds_name} category={qtype} judge={judge_model} raw={raw}",
    )
    if qtype:
        lf.create_score(
            trace_id=trace_id,
            name=f"longmemeval/{qtype}",
            value=1.0 if correct else 0.0,
            data_type="BOOLEAN",
            comment=f"dataset={ds_name} judge={judge_model}",
        )

    # ---- Thread-safe output ----
    preview = ""
    if hypothesis:
        preview = hypothesis[:100].replace("\n", " ")
        if len(hypothesis) > 100:
            preview += "…"
    judge_icon = "✓" if correct else "✗"
    query_icon = "✓" if query_trace.status == "completed" else "✗"

    with print_lock:
        print(
            f"[{idx}/{total}] {qid}  ({qtype})  {n_sessions} sess  "
            f"query={query_icon}  judge={judge_icon} ({raw.strip()})  "
            f"trace={trace_id[:12]}"
        )
        if preview:
            print(f"  → {preview}")

    # ---- Cleanup graph ----
    delete_graph_if_exists(graph)

    return {
        "question_id": qid,
        "question_type": qtype,
        "correct": correct,
        "abstention": abstention,
    }


def cmd_run(args: argparse.Namespace) -> None:
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from weavy.config import settings

    sys.path.insert(0, str(EVAL_DIR))

    _, ds_name = _resolve_dataset(args)
    lf_ds_name = _langfuse_dataset_name(ds_name)
    lf = _get_langfuse()
    judge_model = args.judge_model
    concurrency = args.concurrency

    try:
        dataset = lf.get_dataset(lf_ds_name)
    except Exception:
        print(f"[error] Dataset '{lf_ds_name}' not found in Langfuse.")
        print(f"        Run: uv run eval/eval.py upload --dataset {ds_name}")
        sys.exit(1)

    items = list(dataset.items)
    if args.limit:
        items = items[: args.limit]

    if not items:
        print(f"No items in dataset '{lf_ds_name}'.")
        return

    total = len(items)
    print(f"{SEP}")
    print(f"  Weavy / LongMemEval — experiment  [{ds_name}]")
    print(f"{SEP}")
    print(f"  Dataset      : {lf_ds_name}  ({total} items)")
    print(f"  Judge model  : {judge_model}")
    print(f"  Weavy model  : {settings.GEMINI_MODEL}")
    print(f"  Concurrency  : {concurrency}  (graph per worker)")
    print(f"{SEP}\n")

    run_name = f"weavy-{ds_name}-{datetime.now(tz=timezone.utc).strftime('%Y%m%dT%H%M%S')}"
    print_lock = threading.Lock()

    # Each worker slot gets its own graph: longmemeval_0, longmemeval_1, ...
    graph_names = [f"{EVAL_GRAPH}_{slot}" for slot in range(concurrency)]

    results: list[dict] = []

    # Partition items into per-slot queues so each graph is used sequentially
    slot_queues: list[list[tuple[int, object]]] = [[] for _ in range(concurrency)]
    for i, item in enumerate(items):
        slot_queues[i % concurrency].append((i, item))

    def _run_slot(slot: int) -> list[dict]:
        slot_results = []
        for i, item in slot_queues[slot]:
            try:
                r = _run_single_item(
                    item=item,
                    idx=i + 1,
                    total=total,
                    graph_name=graph_names[slot],
                    ds_name=ds_name,
                    judge_model=judge_model,
                    print_lock=print_lock,
                )
                slot_results.append(r)
            except Exception as e:
                with print_lock:
                    print(f"[{i + 1}/{total}] FAILED: {e}")
        return slot_results

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(_run_slot, slot) for slot in range(concurrency)]
        for future in as_completed(futures):
            results.extend(future.result())

    lf.flush()

    # ---- Print summary ----
    type2correct: dict[str, list[int]] = {}
    all_correct: list[int] = []
    abstention_correct: list[int] = []

    for r in results:
        val = 1 if r["correct"] else 0
        type2correct.setdefault(r["question_type"], []).append(val)
        all_correct.append(val)
        if r["abstention"]:
            abstention_correct.append(val)

    print(f"\n{SEP}")
    print(f"  Experiment complete  [{ds_name}]")
    print(f"{SEP}")
    print(f"  Run name     : {run_name}")
    print(f"  Items        : {len(all_correct)}")

    if all_correct:
        print(f"  Overall      : {sum(all_correct)}/{len(all_correct)}  ({_pct(sum(all_correct), len(all_correct))})")

    task_means: list[float] = []
    for qtype in sorted(type2correct):
        acc = type2correct[qtype]
        mean = sum(acc) / len(acc) if acc else 0
        print(f"    {qtype:<36}  {_bar(mean)}  {mean:.4f}  ({len(acc)})")
        task_means.append(mean)

    if task_means:
        task_avg = sum(task_means) / len(task_means)
        print(f"  Task-averaged: {task_avg:.4f}")

    if abstention_correct:
        print(f"  Abstention   : {sum(abstention_correct)}/{len(abstention_correct)}  ({_pct(sum(abstention_correct), len(abstention_correct))})")

    print(f"  Langfuse     : {settings.LANGFUSE_HOST}")
    print(f"{SEP}")


# ---------------------------------------------------------------------------
# status — show experiment runs for a dataset
# ---------------------------------------------------------------------------

def cmd_status(args: argparse.Namespace) -> None:
    _, ds_name = _resolve_dataset(args)
    lf_ds_name = _langfuse_dataset_name(ds_name)
    lf = _get_langfuse()

    try:
        dataset = lf.get_dataset(lf_ds_name)
    except Exception:
        print(f"Dataset '{lf_ds_name}' not found in Langfuse.")
        print(f"Run: uv run eval/eval.py upload --dataset {ds_name}")
        return

    print(f"{SEP}")
    print(f"  Weavy / LongMemEval  [{ds_name}]")
    print(f"{SEP}")
    print(f"  Dataset  : {lf_ds_name}")
    print(f"  Items    : {len(dataset.items)}")

    from weavy.config import settings
    print(f"  Langfuse : {settings.LANGFUSE_HOST}")

    runs = lf.api.dataset_runs.list(dataset_name=lf_ds_name)
    if hasattr(runs, "data") and runs.data:
        print(f"\n  Experiment runs ({len(runs.data)}):")
        for r in runs.data:
            name = r.name if hasattr(r, "name") else str(r)
            created = r.created_at.strftime("%Y-%m-%d %H:%M") if hasattr(r, "created_at") and r.created_at else "?"
            print(f"    {name}  ({created})")
    else:
        print("\n  No experiment runs yet.")
        print(f"  Run: uv run eval/eval.py run --dataset {ds_name}")

    print(f"{SEP}")


# ---------------------------------------------------------------------------
# metrics — print accuracy table from Langfuse scores
# ---------------------------------------------------------------------------

def cmd_metrics(args: argparse.Namespace) -> None:
    _, ds_name = _resolve_dataset(args)
    lf_ds_name = _langfuse_dataset_name(ds_name)
    lf = _get_langfuse()

    try:
        lf.get_dataset(lf_ds_name)
    except Exception:
        print(f"Dataset '{lf_ds_name}' not found.")
        return

    # Fetch scores for traces linked to this dataset
    all_scores = []
    page = 1
    while True:
        scores_page = lf.api.scores.list(
            page=page,
            limit=100,
        )
        if not hasattr(scores_page, "data") or not scores_page.data:
            break
        all_scores.extend(scores_page.data)
        if len(scores_page.data) < 100:
            break
        page += 1

    # Filter to longmemeval scores
    lme_scores = [s for s in all_scores if hasattr(s, "name") and s.name.startswith("longmemeval/")]

    if not lme_scores:
        print("No longmemeval scores found in Langfuse.")
        print(f"Run an experiment first: uv run eval/eval.py run --dataset {ds_name}")
        return

    # Group by category
    type2acc: dict[str, list[int]] = {}
    overall: list[int] = []

    for s in lme_scores:
        val = 1 if (hasattr(s, "value") and s.value and s.value >= 0.5) else 0
        if s.name == "longmemeval/correct":
            overall.append(val)
        elif s.name.startswith("longmemeval/") and s.name not in (
            "longmemeval/overall_accuracy",
            "longmemeval/task_averaged_accuracy",
            "longmemeval/abstention_accuracy",
        ):
            category = s.name.removeprefix("longmemeval/")
            type2acc.setdefault(category, []).append(val)

    print(f"\n{SEP}")
    print(f"  LongMemEval accuracy  [{ds_name}]")
    print(f"{SEP}")

    task_means: list[float] = []
    for qtype in sorted(type2acc):
        acc = type2acc[qtype]
        mean = sum(acc) / len(acc) if acc else 0
        print(f"  {qtype:<38}  {_bar(mean)}  {mean:.4f}  ({len(acc)})")
        task_means.append(mean)

    print(f"{SEP}")
    if task_means:
        task_avg = sum(task_means) / len(task_means)
        print(f"  Task-averaged accuracy : {task_avg:.4f}")
    if overall:
        ov = sum(overall) / len(overall)
        print(f"  Overall accuracy       : {ov:.4f}  ({len(overall)} instances)")
    print(f"{SEP}\n")


# ---------------------------------------------------------------------------
# reset — delete Langfuse dataset
# ---------------------------------------------------------------------------

def cmd_reset(args: argparse.Namespace) -> None:
    if args.all:
        targets = list(DATASET_FILES.keys())
    else:
        _, ds_name = _resolve_dataset(args)
        targets = [ds_name]

    if not args.force:
        names = ", ".join(targets)
        confirm = input(f"Delete Langfuse datasets for [{names}]? This removes all experiment history. [y/N] ")
        if confirm.strip().lower() != "y":
            print("Cancelled.")
            return

    lf = _get_langfuse()
    for ds in targets:
        lf_name = _langfuse_dataset_name(ds)
        try:
            lf.api.datasets.delete(dataset_name=lf_name)
            print(f"  Deleted dataset '{lf_name}'")
        except Exception:
            print(f"  Dataset '{lf_name}' not found (already clean)")

    # Also clean up legacy .state/ if present
    state_dir = EVAL_DIR / ".state"
    for ds in targets:
        ds_dir = state_dir / ds
        if ds_dir.exists():
            for f in ds_dir.iterdir():
                f.unlink()
            ds_dir.rmdir()
            print(f"  Cleaned legacy .state/{ds}/")

    print("Done.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="eval",
        description="Weavy / LongMemEval evaluation harness (Langfuse Experiments)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  uv run eval/eval.py upload --dataset oracle\n"
            "  uv run eval/eval.py run --dataset oracle --limit 10\n"
            "  uv run eval/eval.py run --dataset oracle --judge-model gpt-4o\n"
            "  uv run eval/eval.py run --dataset oracle --concurrency 4\n"
            "  uv run eval/eval.py status --dataset oracle\n"
            "  uv run eval/eval.py metrics --dataset oracle\n"
            "  uv run eval/eval.py reset --dataset oracle\n"
            "  uv run eval/eval.py reset --all --force\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # upload
    p = sub.add_parser("upload", help="Upload LongMemEval data to Langfuse as a dataset")
    _add_dataset_args(p, need_data_file=True)

    # run
    p = sub.add_parser("run", help="Run experiment: ingest + query + judge (all in one)")
    _add_dataset_args(p, need_data_file=True)
    p.add_argument("--limit", type=int, default=None, metavar="N",
                   help="Process at most N items")
    p.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL, metavar="MODEL",
                   help=f"LiteLLM judge model (default: {DEFAULT_JUDGE_MODEL})")
    p.add_argument("--concurrency", type=int, default=1, metavar="N",
                   help="Number of parallel workers, each with its own graph (default: 1)")

    # status
    p = sub.add_parser("status", help="Show dataset info and experiment runs")
    _add_dataset_args(p)

    # metrics
    p = sub.add_parser("metrics", help="Print per-category accuracy from Langfuse scores")
    _add_dataset_args(p)

    # reset
    p = sub.add_parser("reset", help="Delete Langfuse dataset and experiment history")
    _add_dataset_args(p)
    p.add_argument("--all", action="store_true", help="Reset all datasets")
    p.add_argument("--force", action="store_true", help="Skip confirmation prompt")

    args = parser.parse_args()
    dispatch = {
        "upload": cmd_upload,
        "run": cmd_run,
        "status": cmd_status,
        "metrics": cmd_metrics,
        "reset": cmd_reset,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
