"""Scratch diagnostic: query-only eval against an ALREADY-INGESTED graph.

Lets us iterate on the query side without paying the ~14-min/$0.07 re-ingest each
time. Not part of the harness; safe to delete.

    uv run python -m bench._diag <graph_name> <sample_index> [max_questions]
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# Match the benchmark's model config BEFORE weavy import freezes it.
os.environ.setdefault("LLM_MODEL", "gpt-4o-mini")
os.environ.setdefault("EMBEDDING_MODEL", "text-embedding-3-small")

import litellm  # noqa: E402

litellm.drop_params = True

from bench.adapters.weavy_adapter import WeavyAdapter  # noqa: E402
from bench.datasets.locomo import load_locomo  # noqa: E402
from bench.harness import judge as judging  # noqa: E402


def main() -> int:
    graph = sys.argv[1]
    sample_idx = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    max_q = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    workers = int(os.environ.get("DIAG_WORKERS", "12"))

    conv = load_locomo("bench/data/locomo10.json")[sample_idx]
    qa = list(conv.qa)
    if max_q:
        qa = qa[:max_q]

    adapter = WeavyAdapter(graph, update_themes=False)

    def run(item):
        res = adapter.answer(item.question, conv.query_time)
        v = judging.judge_answer(
            question=item.question,
            gold=item.answer,
            prediction=res.answer,
            is_adversarial=item.is_adversarial,
            model="gpt-4o-mini",
        )
        return item, res, v

    rows = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(run, it): it for it in qa}
        for i, f in enumerate(as_completed(futs), 1):
            rows.append(f.result())
            if i % 25 == 0:
                print(f"  ...{i}/{len(qa)}")

    by_cat = defaultdict(lambda: [0, 0])
    for item, res, v in rows:
        by_cat[item.category_name][0] += int(bool(v.correct))
        by_cat[item.category_name][1] += 1

    total_c = sum(c for c, _ in by_cat.values())
    total_n = sum(n for _, n in by_cat.values())
    print(f"\n=== {graph}  ({total_n} questions) ===")
    for cat, (c, n) in sorted(by_cat.items()):
        print(f"  {cat:14s} {c/n:5.1%}  ({c}/{n})")
    print(f"  {'OVERALL':14s} {total_c/total_n:5.1%}  ({total_c}/{total_n})")

    # Dump the wrong recall answers (skip adversarial) for inspection.
    print("\n--- WRONG (recall) ---")
    for item, res, v in rows:
        if not v.correct and not item.is_adversarial:
            print(f"[{item.category_name}] Q: {item.question}")
            print(f"   gold: {item.answer}")
            print(f"   pred: {res.answer[:200]}")
            print(f"   why : {v.reason[:160]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
