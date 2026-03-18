"""Analyze passage-level retrieval results with unbiased metrics.

Scoring principles:
- Relevance via span overlap: a retrieved chunk is relevant if it overlaps
  a gold target span in the same source document (title + optional date).
- Ground-truth denominator: recall/AP/nDCG use len(targets) as the total
  relevant count, not the number of relevant chunks in the result set.
- First-hit deduplication: each gold target can only be "found" once.
  Subsequent chunks covering the same target do not contribute additional gain.
- Fixed text budget: in addition to top-K, report metrics at fixed character
  budgets (4k, 8k, 16k) so methods with different chunk sizes are comparable.
- Enriched chunks are evaluated on raw transcript spans (start_char/end_char),
  not on the prefixed content, so metadata enrichment does not inflate scores.
"""

import json
import math
from pathlib import Path

PASSAGE_DIR = Path(__file__).resolve().parent
RESULTS_PATH = PASSAGE_DIR / "raw_results.json"
TOP_K = 5
TEXT_BUDGETS = [4096, 8192, 16384]

EXP_LABELS = {
    "semantic_chunks": "Sem. Chunks",
    "enriched_chunks": "Enr. Chunks",
    "sentence_chunks_512": "Sent. 512",
    "sentence_chunks_1024": "Sent. 1024",
    "sentence_chunks_2048": "Sent. 2048",
}


def _spans_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def _match_target(hit: dict, target: dict) -> bool:
    """Check if a retrieved chunk covers a gold target via span overlap."""
    hit_title = str(hit.get("title", "")).strip().lower()
    t_title = str(target.get("title", "")).strip().lower()
    if t_title and hit_title != t_title:
        return False

    t_date = str(target.get("date", "")).strip()
    if t_date:
        hit_date = str(hit.get("date", "")).strip()
        if hit_date != t_date:
            return False

    h_start = hit.get("start_char")
    h_end = hit.get("end_char")
    t_start = target.get("start_char")
    t_end = target.get("end_char")

    if (
        h_start is not None
        and h_end is not None
        and t_start is not None
        and t_end is not None
    ):
        return _spans_overlap(h_start, h_end, t_start, t_end)

    # Fallback: snippet substring match on content (for legacy data without spans)
    t_snippet = str(target.get("snippet", "")).strip().lower()
    hit_content = str(hit.get("content", "")).lower()
    return bool(t_snippet and t_snippet in hit_content)


def _first_hit_flags(hits: list[dict], targets: list[dict]) -> list[int]:
    """For each hit, return the index of the first-matched unseen target, or -1.

    Each target can only be matched once (first-hit deduplication).
    Returns a list of target indices (0-based) or -1 for non-relevant hits.
    """
    seen_targets: set[int] = set()
    flags: list[int] = []
    for hit in hits:
        matched = -1
        for ti, target in enumerate(targets):
            if ti in seen_targets:
                continue
            if _match_target(hit, target):
                matched = ti
                seen_targets.add(ti)
                break
        flags.append(matched)
    return flags


def _hits_at_budget(hits: list[dict], budget: int) -> int:
    """Return number of hits that fit within a character budget."""
    total = 0
    for i, hit in enumerate(hits):
        total += len(str(hit.get("content", "")))
        if total > budget:
            return i
    return len(hits)


def _reciprocal_rank(flags: list[int]) -> float:
    for i, f in enumerate(flags, start=1):
        if f >= 0:
            return 1.0 / i
    return 0.0


def _hit_at_k(flags: list[int], k: int) -> int:
    return 1 if any(f >= 0 for f in flags[:k]) else 0


def _recall_at_k(flags: list[int], total_targets: int, k: int) -> float:
    if total_targets <= 0:
        return 0.0
    found = sum(1 for f in flags[:k] if f >= 0)
    return found / total_targets


def _precision_at_k(flags: list[int], k: int) -> float:
    top = flags[:k]
    if not top:
        return 0.0
    return sum(1 for f in top if f >= 0) / len(top)


def _average_precision(flags: list[int], total_targets: int) -> float:
    if total_targets <= 0:
        return 0.0
    hits = 0
    score = 0.0
    for i, f in enumerate(flags, start=1):
        if f < 0:
            continue
        hits += 1
        score += hits / i
    return score / total_targets


def _ndcg_at_k(flags: list[int], total_targets: int, k: int) -> float:
    dcg = 0.0
    for i, f in enumerate(flags[:k], start=1):
        if f >= 0:
            dcg += 1.0 / math.log2(i + 1)
    ideal_count = min(total_targets, k)
    if ideal_count == 0:
        return 0.0
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_count + 1))
    return dcg / idcg


def _metrics_for_query(hits: list[dict], targets: list[dict], k: int) -> dict:
    total_targets = len(targets)
    flags = _first_hit_flags(hits, targets)
    top_flags = flags[:k]

    rr = _reciprocal_rank(flags)
    h1 = _hit_at_k(top_flags, 1)
    h3 = _hit_at_k(top_flags, 3)
    h5 = _hit_at_k(top_flags, min(5, k))
    recall_k = _recall_at_k(flags, total_targets, k)
    precision_k = _precision_at_k(flags, k)
    ap = _average_precision(flags[:k], total_targets)
    ndcg_k = _ndcg_at_k(flags, total_targets, k)

    # Budget-based metrics
    budget_metrics = {}
    for budget in TEXT_BUDGETS:
        n_hits = _hits_at_budget(hits, budget)
        budget_flags = _first_hit_flags(hits[:n_hits], targets)
        budget_metrics[budget] = {
            "n_hits": n_hits,
            "recall": _recall_at_k(budget_flags, total_targets, n_hits),
            "mrr": _reciprocal_rank(budget_flags),
        }

    return {
        "rr": rr,
        "hit1": h1,
        "hit3": h3,
        "hit5": h5,
        "precision_k": precision_k,
        "recall_k": recall_k,
        "ap": ap,
        "ndcg_k": ndcg_k,
        "total_targets": total_targets,
        "budget": budget_metrics,
    }


def _composite(m: dict) -> float:
    return m["rr"] + m["ndcg_k"] + m["recall_k"]


def main() -> None:
    with open(RESULTS_PATH) as fh:
        payload = json.load(fh)

    queries = payload.get("queries", {})
    if not queries:
        raise SystemExit("No queries found in passage-level/raw_results.json")

    q_keys = sorted(queries.keys())
    experiments = payload.get("meta", {}).get("experiments", list(EXP_LABELS.keys()))
    k = int(payload.get("meta", {}).get("top_n", TOP_K))

    print("=" * 120)
    print("PASSAGE-LEVEL RETRIEVAL EVALUATION (UNBIASED)")
    print("=" * 120)
    print(f"Scoring depth: top-{k}")
    print("Relevance: span-overlap with gold targets (first-hit dedup per target)")
    print(f"Denominator: ground-truth target count (not retrieved-set count)")
    print(f"Text budgets: {', '.join(f'{b//1024}k chars' for b in TEXT_BUDGETS)}")

    all_metrics: dict[str, dict[str, dict]] = {}
    for q_key in q_keys:
        q_data = queries[q_key]
        targets = q_data["targets"]
        all_metrics[q_key] = {}
        for exp in experiments:
            exp_data = q_data["experiments"].get(exp, {})
            if exp_data.get("error"):
                raise SystemExit(f"Run failure in {q_key}/{exp}: {exp_data['error']}")
            parsed = exp_data.get("parsed", [])
            all_metrics[q_key][exp] = _metrics_for_query(parsed, targets, k)

    # ── Per-query detail ──
    print("\n" + "-" * 120)
    print("PER-QUERY")
    print("-" * 120)
    for q_key in q_keys:
        q_data = queries[q_key]
        print(f"\n[{q_key}] ({q_data.get('category', 'misc').upper()}) {q_data['query']}")
        print(f"  Targets ({len(q_data['targets'])}): ", end="")
        for t in q_data["targets"]:
            print(f"[{t['title'][:40]}... chars {t.get('start_char','?')}-{t.get('end_char','?')}] ", end="")
        print()
        print(
            f"  {'Experiment':<14} {'RR':>6} {'H@1':>5} {'H@3':>5} {'H@5':>5}"
            f" {'nDCG':>7} {'R@K':>7} {'P@K':>7} {'AP@K':>7}"
        )
        for exp in experiments:
            m = all_metrics[q_key][exp]
            print(
                f"  {EXP_LABELS.get(exp, exp):<14}"
                f" {m['rr']:>6.3f}"
                f" {m['hit1']:>5}"
                f" {m['hit3']:>5}"
                f" {m['hit5']:>5}"
                f" {m['ndcg_k']:>7.3f}"
                f" {m['recall_k']:>7.3f}"
                f" {m['precision_k']:>7.3f}"
                f" {m['ap']:>7.3f}"
            )

    # ── Fixed text budget comparison ──
    print("\n" + "-" * 120)
    print("FIXED TEXT BUDGET COMPARISON")
    print("-" * 120)
    print("  (Recall at equivalent character budgets — eliminates chunk-size bias)")
    for budget in TEXT_BUDGETS:
        label = f"{budget // 1024}k chars"
        print(f"\n  Budget: {label}")
        print(f"    {'Experiment':<14} {'AvgRecall':>10} {'AvgMRR':>8} {'AvgHits':>8}")
        for exp in experiments:
            recalls = [all_metrics[q][exp]["budget"][budget]["recall"] for q in q_keys]
            mrrs = [all_metrics[q][exp]["budget"][budget]["mrr"] for q in q_keys]
            n_hits = [all_metrics[q][exp]["budget"][budget]["n_hits"] for q in q_keys]
            n = len(q_keys)
            print(
                f"    {EXP_LABELS.get(exp, exp):<14}"
                f" {sum(recalls)/n:>10.3f}"
                f" {sum(mrrs)/n:>8.3f}"
                f" {sum(n_hits)/n:>8.1f}"
            )

    # ── Fair comparison tracks ──
    print("\n" + "-" * 120)
    print("FAIR COMPARISON TRACKS")
    print("-" * 120)

    track_a = [e for e in ["semantic_chunks", "sentence_chunks_512", "sentence_chunks_1024", "sentence_chunks_2048"] if e in experiments]
    track_b = [e for e in experiments]

    for track_label, track_exps, track_desc in [
        (
            "Track A: Raw Transcript Only (strict chunker comparison)",
            track_a,
            "Methods that index raw transcript text without metadata enrichment.",
        ),
        (
            "Track B: All Methods (including enriched)",
            track_b,
            "All methods including metadata-augmented retrieval.",
        ),
    ]:
        print(f"\n  ▸ {track_label}")
        print(f"    {track_desc}")

        if len(track_exps) < 2:
            print("    (fewer than 2 experiments — skipping)")
            continue

        # Ranking by composite
        track_composites = []
        for exp in track_exps:
            avg = sum(_composite(all_metrics[q][exp]) for q in q_keys) / len(q_keys)
            track_composites.append((exp, avg))
        track_composites.sort(key=lambda x: x[1], reverse=True)
        print("\n    Ranking (by avg composite = MRR + nDCG + Recall@K):")
        for rank, (exp, avg) in enumerate(track_composites, 1):
            print(f"      {rank}. {EXP_LABELS.get(exp, exp):<14} composite={avg:.3f}")

        # Pairwise wins
        print("\n    Pairwise win counts:")
        wins = {e: 0 for e in track_exps}
        ties = 0
        for q_key in q_keys:
            scores = {e: _composite(all_metrics[q_key][e]) for e in track_exps}
            best_score = max(scores.values())
            winners = [e for e, s in scores.items() if s == best_score]
            if len(winners) == len(track_exps):
                ties += 1
            else:
                for w in winners:
                    wins[w] += 1
        parts = [f"{EXP_LABELS.get(e, e)} wins: {wins[e]}" for e in track_exps]
        print(f"      {'  |  '.join(parts)}  |  Ties: {ties}")

        # Budget-based ranking
        for budget in TEXT_BUDGETS:
            label = f"{budget // 1024}k"
            budget_composites = []
            for exp in track_exps:
                avg_recall = sum(all_metrics[q][exp]["budget"][budget]["recall"] for q in q_keys) / len(q_keys)
                avg_mrr = sum(all_metrics[q][exp]["budget"][budget]["mrr"] for q in q_keys) / len(q_keys)
                budget_composites.append((exp, avg_recall + avg_mrr))
            budget_composites.sort(key=lambda x: x[1], reverse=True)
            print(f"\n    At {label} budget (Recall + MRR):")
            for rank, (exp, sc) in enumerate(budget_composites, 1):
                print(f"      {rank}. {EXP_LABELS.get(exp, exp):<14} score={sc:.3f}")

    # ── Final verdict ──
    print("\n" + "=" * 120)
    print("FINAL VERDICT (PASSAGE-LEVEL)")
    print("=" * 120)

    metric_names = ["MRR", "H@1%", "H@3%", "H@5%", "nDCG", "R@K", "P@K", "MAP@K", "Comp"]
    print(
        f"\n  {'Experiment':<14}"
        f" {metric_names[0]:>6}"
        f" {metric_names[1]:>6}"
        f" {metric_names[2]:>6}"
        f" {metric_names[3]:>6}"
        f" {metric_names[4]:>7}"
        f" {metric_names[5]:>7}"
        f" {metric_names[6]:>7}"
        f" {metric_names[7]:>7}"
        f" {metric_names[8]:>7}"
    )

    ranked: list[tuple[str, float]] = []
    for exp in experiments:
        rows = [all_metrics[q][exp] for q in q_keys]
        n = len(rows)
        mrr = sum(r["rr"] for r in rows) / n
        h1 = sum(r["hit1"] for r in rows) / n * 100
        h3 = sum(r["hit3"] for r in rows) / n * 100
        h5 = sum(r["hit5"] for r in rows) / n * 100
        ndcg = sum(r["ndcg_k"] for r in rows) / n
        recall = sum(r["recall_k"] for r in rows) / n
        precision = sum(r["precision_k"] for r in rows) / n
        mapk = sum(r["ap"] for r in rows) / n
        comp = mrr + ndcg + recall
        ranked.append((exp, comp))
        print(
            f"  {EXP_LABELS.get(exp, exp):<14}"
            f" {mrr:>6.3f}"
            f" {h1:>5.1f}%"
            f" {h3:>5.1f}%"
            f" {h5:>5.1f}%"
            f" {ndcg:>7.3f}"
            f" {recall:>7.3f}"
            f" {precision:>7.3f}"
            f" {mapk:>7.3f}"
            f" {comp:>7.3f}"
        )

    ranked.sort(key=lambda x: x[1], reverse=True)
    print("\nOverall ranking by composite (MRR + nDCG + Recall@K):")
    for i, (exp, score) in enumerate(ranked, start=1):
        print(f"  {i}. {EXP_LABELS.get(exp, exp):<14} composite={score:.3f}")

    # Budget-based final ranking
    print(f"\nBudget-normalized ranking (avg Recall across all budgets):")
    budget_final = []
    for exp in experiments:
        avg_recall = 0.0
        for budget in TEXT_BUDGETS:
            avg_recall += sum(all_metrics[q][exp]["budget"][budget]["recall"] for q in q_keys) / len(q_keys)
        avg_recall /= len(TEXT_BUDGETS)
        budget_final.append((exp, avg_recall))
    budget_final.sort(key=lambda x: x[1], reverse=True)
    for i, (exp, score) in enumerate(budget_final, start=1):
        print(f"  {i}. {EXP_LABELS.get(exp, exp):<14} avg_recall={score:.3f}")


if __name__ == "__main__":
    main()
