#!/usr/bin/env python3
"""
Weavy / LongMemEval evaluation harness.

    uv run eval/eval.py run     --dataset oracle  [--limit N]
    uv run eval/eval.py status  --dataset oracle
    uv run eval/eval.py reset   --dataset oracle  [--all] [--force]
    uv run eval/eval.py judge   --dataset oracle  [--model MODEL]
    uv run eval/eval.py score   --dataset oracle
    uv run eval/eval.py metrics --dataset oracle

Datasets (place in eval/data/):
    oracle  — evidence sessions only (~3-5 sessions/instance)   easiest
    s       — ~40 sessions / ~115k tokens per instance          medium
    m       — ~500 sessions per instance                        hardest

State is scoped per dataset under eval/.state/{dataset}/ so all three can
run concurrently. Use --data PATH to point at any custom file.
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
STATE_DIR = EVAL_DIR / ".state"

DATASET_FILES: dict[str, Path] = {
    "oracle": EVAL_DIR / "data" / "longmemeval_oracle.json",
    "s":      EVAL_DIR / "data" / "longmemeval_s.json",
    "m":      EVAL_DIR / "data" / "longmemeval_m.json",
}

EVAL_GRAPH = "longmemeval"   # isolated FalkorDB graph; never touches your main graph

SEP = "─" * 54

# ---------------------------------------------------------------------------
# Dataset / state resolution
# ---------------------------------------------------------------------------

def _resolve_dataset(args: argparse.Namespace) -> tuple[Path, str]:
    """Return (data_path, dataset_name) from CLI args.

    --dataset oracle|s|m  uses the predefined path in eval/data/
    --data PATH           explicit path; name derived from the file stem
    The two flags are never used together (argparse mutual-exclusion group).
    """
    data_override = getattr(args, "data", None)
    if data_override:
        p = Path(data_override)
        name = p.stem.removeprefix("longmemeval_") or p.stem
        return p, name
    ds = getattr(args, "dataset", "oracle")
    return DATASET_FILES[ds], ds


def _state_files(name: str) -> tuple[Path, Path]:
    """Return (results_file, eval_results_file) for the given dataset name."""
    d = STATE_DIR / name
    return d / "results.jsonl", d / "eval_results.jsonl"


# ---------------------------------------------------------------------------
# State I/O helpers
# ---------------------------------------------------------------------------

def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _append_jsonl(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


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


# ---------------------------------------------------------------------------
# Text / display helpers
# ---------------------------------------------------------------------------

def _parse_date(s: str) -> datetime:
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    raise ValueError(f"Cannot parse date: {s!r}")


def _format_session(turns: list[dict], date: str) -> str:
    """Flatten a LongMemEval session to plain text for Weavy ingestion."""
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
    """Add --dataset / --data flags to a subcommand parser."""
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


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> None:
    import weavy

    data_path, ds_name = _resolve_dataset(args)
    data = _load_data(data_path)
    results_file, _ = _state_files(ds_name)

    done_ids = {r["question_id"] for r in _load_jsonl(results_file)}
    pending = [x for x in data if x["question_id"] not in done_ids]
    if args.limit:
        pending = pending[: args.limit]

    if not pending:
        print(f"Nothing to run — {len(done_ids)}/{len(data)} already answered for dataset '{ds_name}'.")
        print("Use 'reset' to start over or 'judge' to score existing results.")
        return

    total_done = len(done_ids)
    total_all = len(data)
    print(f"{SEP}")
    print(f"  Weavy / LongMemEval — run  [{ds_name}]")
    print(f"{SEP}")
    print(f"  Dataset      : {ds_name}  ({data_path.name})")
    print(f"  Already done : {total_done} / {total_all}")
    print(f"  This batch   : {len(pending)}" + (f"  (--limit {args.limit})" if args.limit else ""))
    print(f"  Graph        : {EVAL_GRAPH!r}  (isolated, reset per instance)")
    print(f"  State        : {results_file.parent}")
    print(f"{SEP}\n")

    w = weavy.Weavy(EVAL_GRAPH)

    for i, instance in enumerate(pending, 1):
        qid = instance["question_id"]
        qtype = instance["question_type"]
        sessions = instance["haystack_sessions"]
        dates = instance["haystack_dates"]
        n_sessions = len(sessions)

        global_idx = total_done + i
        print(f"[{global_idx}/{total_all}] {qid}  ({qtype})  — {n_sessions} session(s)")

        w.reset()

        for j, (turns, date) in enumerate(zip(sessions, dates), 1):
            text = _format_session(turns, date)
            ts = _parse_date(date)
            ingest_trace = w.add(text, timestamp=ts)
            ok = "✓" if ingest_trace.status == "completed" else "✗"
            width = len(str(n_sessions))
            print(f"  ingest [{j:>{width}}/{n_sessions}] {date}  {ok}")

        question_dt = _parse_date(instance["question_date"])
        query_trace = w.query(instance["question"], query_time=question_dt)

        hypothesis = (query_trace.completion_payload or {}).get("answer", "")
        ok = "✓" if query_trace.status == "completed" else "✗"
        print(f"  query  {ok}  trace={query_trace.run_id[:12]}")
        if hypothesis:
            preview = hypothesis[:120].replace("\n", " ")
            print(f"  → {preview}{'…' if len(hypothesis) > 120 else ''}")
        print()

        _append_jsonl(results_file, {
            "question_id": qid,
            "question_type": qtype,
            "hypothesis": hypothesis,
            "trace_id": query_trace.run_id,
            "answered_at": datetime.now(tz=timezone.utc).isoformat(),
        })

    total_now = total_done + len(pending)
    print(f"{SEP}")
    print(f"  Done: {total_now}/{total_all} answered  [{ds_name}]")
    if total_now < total_all:
        print(f"  Run again (no --limit) to continue, or 'judge' to score what's done.")
    else:
        print(f"  All answered. Next: eval/eval.py judge --dataset {ds_name}")
    print(f"{SEP}")


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def cmd_status(args: argparse.Namespace) -> None:
    data_path, ds_name = _resolve_dataset(args)
    results_file, eval_results_file = _state_files(ds_name)

    results = _load_jsonl(results_file)
    eval_results = _load_jsonl(eval_results_file)

    total: int | str = "?"
    if data_path.exists():
        total = len(_load_data(data_path))

    answered = len(results)
    judged = len(eval_results)
    correct = sum(1 for r in eval_results if r.get("autoeval_label", {}).get("label", False))

    print(f"\n{SEP}")
    print(f"  Weavy / LongMemEval  [{ds_name}]")
    print(f"{SEP}")
    print(f"  Answered :  {answered} / {total}  ({_pct(answered, total if isinstance(total, int) else 0)})")
    print(f"  Judged   :  {judged} / {answered}  ({_pct(judged, answered)})")
    if judged:
        ratio = correct / judged
        print(f"  Correct  :  {correct} / {judged}  ({_pct(correct, judged)})  {_bar(ratio)}")
    else:
        print(f"  Correct  :  — (run 'judge --dataset {ds_name}' first)")

    if judged:
        print()
        print("  By category:")
        type2items: dict[str, list[dict]] = {}
        for r in eval_results:
            type2items.setdefault(r.get("question_type", "unknown"), []).append(r)

        for qtype in sorted(type2items):
            items = type2items[qtype]
            n = len(items)
            c = sum(1 for x in items if x.get("autoeval_label", {}).get("label", False))
            print(f"    {qtype:<38}  {_bar(c/n if n else 0)}  {c:>3}/{n:<3}  {_pct(c, n)}")

    try:
        from weavy.config import settings  # noqa: PLC0415
        print()
        print(f"  Langfuse :  {settings.LANGFUSE_HOST}")
        print(f"             score names: longmemeval/correct, longmemeval/<category>")
    except Exception:
        pass

    print(f"{SEP}\n")


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------

def cmd_reset(args: argparse.Namespace) -> None:
    if args.all:
        # collect all dataset state dirs
        targets: list[tuple[str, Path, Path]] = []
        for ds_name in (list(DATASET_FILES) + [
            p.name for p in STATE_DIR.iterdir() if p.is_dir()
        ] if STATE_DIR.exists() else []):
            rf, ef = _state_files(ds_name)
            if rf.exists() or ef.exists():
                targets.append((ds_name, rf, ef))
        # deduplicate
        seen: set[str] = set()
        targets = [t for t in targets if not (t[0] in seen or seen.add(t[0]))]  # type: ignore[func-returns-value]
    else:
        _, ds_name = _resolve_dataset(args)
        rf, ef = _state_files(ds_name)
        targets = [(ds_name, rf, ef)] if (rf.exists() or ef.exists()) else []

    if not targets:
        print("No state to reset.")
        return

    print(f"{SEP}")
    print("  This will permanently delete:")
    for ds_name, rf, ef in targets:
        r_count = len(_load_jsonl(rf))
        e_count = len(_load_jsonl(ef))
        print(f"    [{ds_name}]  {r_count} answered,  {e_count} judged")
    print(f"{SEP}")

    if not args.force:
        try:
            confirm = input("  Type 'yes' to confirm: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            return
        if confirm.lower() != "yes":
            print("Aborted.")
            return

    for _, rf, ef in targets:
        if rf.exists():
            rf.unlink()
        if ef.exists():
            ef.unlink()
    print("State cleared.")


# ---------------------------------------------------------------------------
# judge
# ---------------------------------------------------------------------------

def cmd_judge(args: argparse.Namespace) -> None:
    import tempfile

    sys.path.insert(0, str(EVAL_DIR))
    from evaluate_qa import run_judge  # noqa: PLC0415

    data_path, ds_name = _resolve_dataset(args)
    results_file, eval_results_file = _state_files(ds_name)

    results = _load_jsonl(results_file)
    if not results:
        print(f"No hypotheses to judge for dataset '{ds_name}'. Run 'run' first.")
        return

    already_judged = {r["question_id"] for r in _load_jsonl(eval_results_file)}
    to_judge = [r for r in results if r["question_id"] not in already_judged]

    if not to_judge:
        print(f"All {len(results)} hypotheses already judged for '{ds_name}'. Use 'reset' to start over.")
        return

    print(f"{SEP}")
    print(f"  Judge  [{ds_name}]")
    print(f"{SEP}")
    print(f"  Pending  : {len(to_judge)} / {len(results)}")
    print(f"  Model    : {args.model}")
    print(f"  Ref file : {data_path.name}")
    print(f"{SEP}\n")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        tmp = Path(f.name)
        for r in to_judge:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    try:
        judged = run_judge(
            hyp_file=tmp,
            ref_file=data_path,
            model=args.model,
            out_file=eval_results_file,
            append=True,
            verbose=False,
        )
    finally:
        tmp.unlink(missing_ok=True)

    correct = sum(1 for r in judged if r.get("autoeval_label", {}).get("label", False))
    total_now = len(_load_jsonl(eval_results_file))
    print(f"\n  This batch : {correct}/{len(judged)} correct")
    print(f"  Total judged : {total_now} / {len(results)}")
    print(f"\n  Next: eval/eval.py score --dataset {ds_name}")


# ---------------------------------------------------------------------------
# score  (post to Langfuse)
# ---------------------------------------------------------------------------

def cmd_score(args: argparse.Namespace) -> None:
    _, ds_name = _resolve_dataset(args)
    _, eval_results_file = _state_files(ds_name)

    eval_results = _load_jsonl(eval_results_file)
    if not eval_results:
        print(f"No judged results for '{ds_name}'. Run 'judge' first.")
        return

    try:
        from weavy.config import settings          # noqa: PLC0415
        from weavy.langfuse_client import get_langfuse  # noqa: PLC0415
    except ImportError as e:
        print(f"[error] {e}")
        sys.exit(1)

    if not settings.LANGFUSE_PUBLIC_KEY:
        print("[error] Langfuse not configured — set LANGFUSE_PUBLIC_KEY in your .env")
        return

    lf = get_langfuse()
    posted = 0

    for entry in eval_results:
        trace_id = entry.get("trace_id")
        if not trace_id:
            continue
        label = entry.get("autoeval_label", {}).get("label", False)
        value = 1.0 if label else 0.0
        qtype = entry.get("question_type", "")

        # Overall correctness — one score per trace, queryable across all categories
        lf.create_score(
            trace_id=trace_id,
            name="longmemeval/correct",
            value=value,
            data_type="BOOLEAN",
            comment=f"dataset={ds_name} category={qtype}",
        )

        # Per-category score — lets Langfuse aggregate each category independently
        if qtype:
            lf.create_score(
                trace_id=trace_id,
                name=f"longmemeval/{qtype}",
                value=value,
                data_type="BOOLEAN",
                comment=f"dataset={ds_name}",
            )

        posted += 1

    lf.flush()

    correct = sum(1 for e in eval_results if e.get("autoeval_label", {}).get("label", False))
    print(f"Posted scores for {posted} trace(s)  [{ds_name}]")
    print(f"  Overall : {correct}/{posted}  ({_pct(correct, posted)})")
    print(f"  Host    : {settings.LANGFUSE_HOST}")
    print(f"  Scores  : longmemeval/correct  +  longmemeval/<category>")


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------

def cmd_metrics(args: argparse.Namespace) -> None:
    _, ds_name = _resolve_dataset(args)
    _, eval_results_file = _state_files(ds_name)

    eval_results = _load_jsonl(eval_results_file)
    if not eval_results:
        print(f"No judged results for '{ds_name}'. Run 'judge' first.")
        return

    type2acc: dict[str, list[int]] = {}
    for r in eval_results:
        qtype = r.get("question_type", "unknown")
        label = 1 if r.get("autoeval_label", {}).get("label", False) else 0
        type2acc.setdefault(qtype, []).append(label)

    all_acc: list[int] = []
    task_means: list[float] = []
    abstention_acc: list[int] = []

    print(f"\n{SEP}")
    print(f"  LongMemEval accuracy  [{ds_name}]")
    print(f"{SEP}")
    for qtype in sorted(type2acc):
        acc = type2acc[qtype]
        mean = sum(acc) / len(acc)
        print(f"  {qtype:<38}  {_bar(mean)}  {mean:.4f}  ({len(acc)})")
        all_acc.extend(acc)
        task_means.append(mean)

    for r in eval_results:
        if "_abs" in r.get("question_id", ""):
            abstention_acc.append(1 if r.get("autoeval_label", {}).get("label", False) else 0)

    print(f"{SEP}")
    if task_means:
        task_avg = sum(task_means) / len(task_means)
        print(f"  Task-averaged accuracy : {task_avg:.4f}")
    if all_acc:
        overall = sum(all_acc) / len(all_acc)
        print(f"  Overall accuracy       : {overall:.4f}  ({len(all_acc)} instances)")
    if abstention_acc:
        abs_acc = sum(abstention_acc) / len(abstention_acc)
        print(f"  Abstention accuracy    : {abs_acc:.4f}  ({len(abstention_acc)})")
    print(f"{SEP}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="eval",
        description="Weavy / LongMemEval evaluation harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  uv run eval/eval.py run --dataset oracle --limit 10\n"
            "  uv run eval/eval.py run --dataset s\n"
            "  uv run eval/eval.py status --dataset oracle\n"
            "  uv run eval/eval.py judge --dataset oracle --model gemini/gemini-2.5-flash-lite\n"
            "  uv run eval/eval.py score --dataset oracle\n"
            "  uv run eval/eval.py metrics --dataset oracle\n"
            "  uv run eval/eval.py reset --dataset oracle\n"
            "  uv run eval/eval.py reset --all\n"
            "  uv run eval/eval.py run --data path/to/custom.json\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # run
    p = sub.add_parser("run", help="Ingest + query instances (auto-resumes)")
    _add_dataset_args(p, need_data_file=True)
    p.add_argument("--limit", type=int, default=None, metavar="N",
                   help="Process at most N pending instances in this invocation")

    # status
    p = sub.add_parser("status", help="Show progress, accuracy, and Langfuse link")
    _add_dataset_args(p, need_data_file=True)

    # reset
    p = sub.add_parser("reset", help="Delete eval state for a dataset (or all)")
    _add_dataset_args(p)
    p.add_argument("--all", action="store_true", help="Reset state for all datasets")
    p.add_argument("--force", action="store_true", help="Skip confirmation prompt")

    # judge
    p = sub.add_parser("judge", help="Run LLM-as-judge on completed hypotheses")
    _add_dataset_args(p, need_data_file=True)
    p.add_argument("--model", default="gemini/gemini-2.5-flash-lite", metavar="MODEL",
                   help="LiteLLM judge model (default: gemini/gemini-2.5-flash-lite)")

    # score
    p = sub.add_parser("score", help="Post judge labels as Langfuse scores on query traces")
    _add_dataset_args(p)

    # metrics
    p = sub.add_parser("metrics", help="Print per-category accuracy table")
    _add_dataset_args(p)

    args = parser.parse_args()
    dispatch = {
        "run": cmd_run,
        "status": cmd_status,
        "reset": cmd_reset,
        "judge": cmd_judge,
        "score": cmd_score,
        "metrics": cmd_metrics,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
