"""Evaluate semantic search experiments with journal-level ranking metrics.

The analyzer:
- deduplicates results by journal and keeps the best (minimum) distance
- derives journal identity dynamically from the current corpus titles
- canonicalizes duplicate titles to a stable journal identity
- reports both classic recall and Coverage@5 for top-5 discovery fairness
"""

import json
import math
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SEARCH_DIR = Path(__file__).resolve().parent
RESULTS_PATH = SEARCH_DIR / "eval_raw_results.json"
SUMMARIES_DIR = ROOT / "private" / "summaries"
TOP_K = 5
CANDIDATE_DEPTH = 50  # All methods retrieve 50 candidates, deduplicate by journal, return top-5

EXPERIMENTS = [
    "full_blob",
    "structured_fields",
    "grouped_structured",
    "semantic_chunks",
    "enriched_chunks",
    "grouped_semantic_chunks",
    "grouped_enriched_chunks",
    "sentence_chunks_512",
    "sentence_chunks_1024",
    "sentence_chunks_2048",
    "grouped_sentence_chunks_512",
    "grouped_sentence_chunks_1024",
    "grouped_sentence_chunks_2048",
]
EXP_LABELS = {
    "full_blob": "Full Blob",
    "structured_fields": "Struct Fields",
    "grouped_structured": "Grp Struct",
    "semantic_chunks": "Sem. Chunks",
    "enriched_chunks": "Enr. Chunks",
    "grouped_semantic_chunks": "Grp Sem. Chunks",
    "grouped_enriched_chunks": "Grp Enr. Chunks",
    "sentence_chunks_512": "Sent. 512",
    "sentence_chunks_1024": "Sent. 1024",
    "sentence_chunks_2048": "Sent. 2048",
    "grouped_sentence_chunks_512": "Grp Sent. 512",
    "grouped_sentence_chunks_1024": "Grp Sent. 1024",
    "grouped_sentence_chunks_2048": "Grp Sent. 2048",
}
CATEGORIES = ["exact", "thematic", "question", "emotional", "indirect"]


def _load_title_mappings() -> tuple[int, dict[str, list[int]], dict[int, int], dict[str, list[int]]]:
    summary_paths = sorted(SUMMARIES_DIR.glob("*_summary.json"))
    title_to_indices: dict[str, list[int]] = defaultdict(list)
    for idx, path in enumerate(summary_paths):
        with open(path) as fh:
            summary = json.load(fh)
        title = str(summary.get("title", "")).strip()
        if title:
            title_to_indices[title].append(idx)

    canonical_idx_by_index = {idx: idx for idx in range(len(summary_paths))}
    for indices in title_to_indices.values():
        canonical = min(indices)
        for idx in indices:
            canonical_idx_by_index[idx] = canonical

    duplicate_title_groups = {
        title: indices
        for title, indices in title_to_indices.items()
        if len(indices) > 1
    }
    return (
        len(summary_paths),
        dict(title_to_indices),
        canonical_idx_by_index,
        duplicate_title_groups,
    )


RAW_SUMMARY_COUNT, TITLE_TO_INDICES, CANONICAL_IDX_BY_INDEX, DUPLICATE_TITLE_GROUPS = _load_title_mappings()
CANONICAL_JOURNAL_COUNT = len(set(CANONICAL_IDX_BY_INDEX.values()))


def extract_journal_index(result: dict) -> int | None:
    """Return canonical journal index for a result, or None if unresolvable."""
    for title in _title_candidates(result):
        indices = TITLE_TO_INDICES.get(title)
        if indices:
            return min(indices)
    return None


def _title_candidates(result: dict):
    title = result.get("title", "").strip()
    if title:
        yield title
    content = result.get("content", "")
    m = re.search(r"title:\s*(.+?)(?:\n|$)", content)
    if m:
        yield m.group(1).strip()
    m = re.match(r"\[(.+?)\s*\|", content)
    if m:
        yield m.group(1).strip()


def _effective_expected(expected: list[int]) -> set[int]:
    return {CANONICAL_IDX_BY_INDEX.get(idx, idx) for idx in expected}


def resolve_expected_indices(q_data: dict) -> list[int]:
    expected_titles = q_data.get("expected_titles", [])
    if expected_titles:
        resolved: list[int] = []
        missing: list[str] = []
        for title in expected_titles:
            clean_title = str(title).strip()
            indices = TITLE_TO_INDICES.get(clean_title)
            if not indices:
                missing.append(clean_title)
                continue
            resolved.extend(indices)
        if missing:
            missing_fmt = "; ".join(missing)
            raise ValueError(f"missing ground-truth title(s): {missing_fmt}")
        return sorted(set(resolved))
    return list(q_data.get("expected_indices", []))


def deduplicate_by_journal(results: list[dict]) -> list[tuple[int, float]]:
    """Deduplicate results by journal, keeping min distance. Returns sorted list."""
    best: dict[int, float] = {}
    for r in results:
        idx = extract_journal_index(r)
        if idx is None:
            continue
        dist = r.get("distance", 99.0)
        if idx not in best or dist < best[idx]:
            best[idx] = dist
    return sorted(best.items(), key=lambda x: x[1])


def compute_mrr(ranked: list[int], relevant: set[int]) -> float:
    for i, idx in enumerate(ranked):
        if idx in relevant:
            return 1.0 / (i + 1)
    return 0.0


def compute_success_at_k(ranked: list[int], relevant: set[int], k: int) -> int:
    return 1 if any(idx in relevant for idx in ranked[:k]) else 0


def compute_ndcg5(ranked: list[int], relevant: set[int]) -> float:
    dcg = 0.0
    for i, idx in enumerate(ranked[:TOP_K]):
        if idx in relevant:
            dcg += 1.0 / math.log2(i + 2)  # i+2 because rank starts at 1
    # Ideal DCG: all relevant docs at top positions
    ideal_count = min(len(relevant), TOP_K)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_count))
    return dcg / idcg if idcg > 0 else 0.0


def compute_coverage_at_k(ranked: list[int], relevant: set[int], k: int = TOP_K) -> float:
    """Top-k coverage with capped denominator so perfect top-k coverage can reach 1.0."""
    denom = min(len(relevant), k)
    if denom == 0:
        return 0.0
    hits = sum(1 for idx in ranked[:k] if idx in relevant)
    return hits / denom


def compute_metrics(results: list[dict], expected: list[int]) -> dict:
    eff = _effective_expected(expected)
    deduped = deduplicate_by_journal(results)
    ranked_indices = [idx for idx, _ in deduped]
    visible_ranked = ranked_indices[:TOP_K]

    unique_count = len(visible_ranked)
    relevant_found = [idx for idx in visible_ranked if idx in eff]
    unique_relevant = len(relevant_found)

    mrr = compute_mrr(ranked_indices, eff)
    s1 = compute_success_at_k(visible_ranked, eff, 1)
    s3 = compute_success_at_k(visible_ranked, eff, 3)
    s5 = compute_success_at_k(visible_ranked, eff, TOP_K)
    ndcg5 = compute_ndcg5(visible_ranked, eff)
    jp = unique_relevant / max(unique_count, 1)
    recall = unique_relevant / max(len(eff), 1)
    coverage5 = compute_coverage_at_k(visible_ranked, eff, TOP_K)

    all_dists = [r.get("distance", 99.0) for r in results]

    return {
        "mrr": mrr,
        "s1": s1,
        "s3": s3,
        "s5": s5,
        "ndcg5": ndcg5,
        "jp": jp,
        "recall": recall,
        "coverage5": coverage5,
        "unique_count": unique_count,
        "retrieved_indices": visible_ranked,
        "distances": all_dists,
        "embedding_types": [r.get("embedding_for", "") for r in results],
        "per_result_indices": [extract_journal_index(r) for r in results],
    }


def detect_experiment_issue(exp_data: dict | None) -> str | None:
    if exp_data is None:
        return "missing run record"

    error = exp_data.get("error")
    if error:
        return str(error)

    returncode = exp_data.get("returncode")
    if returncode not in (None, 0):
        return f"non-zero return code: {returncode}"

    raw = exp_data.get("raw", "")
    parsed = exp_data.get("parsed", [])
    stripped = raw.strip()
    if not stripped:
        return "empty stdout/stderr"

    error_markers = [
        "Traceback (most recent call last):",
        "ImportError:",
        "ModuleNotFoundError:",
        "RuntimeError:",
        "ValueError:",
    ]
    for marker in error_markers:
        if marker in raw:
            first_line = stripped.splitlines()[0]
            return f"runtime failure: {first_line}"

    if stripped == "No results.":
        return None

    if not parsed:
        first_line = stripped.splitlines()[0]
        return f"unparsed output: {first_line}"

    return None


def composite_score(metrics: dict) -> float:
    """Journal-discovery composite for a top-5 UI: first hit, rank quality, and coverage."""
    return metrics["mrr"] + metrics["ndcg5"] + metrics["coverage5"]


def pairwise_breakdown(
    all_metrics: dict[str, dict],
    q_keys: list[str],
    exp_a: str,
    exp_b: str,
) -> tuple[int, int, int]:
    a_wins = 0
    b_wins = 0
    ties = 0
    for q_key in q_keys:
        score_a = composite_score(all_metrics[q_key]["by_exp"][exp_a])
        score_b = composite_score(all_metrics[q_key]["by_exp"][exp_b])
        if math.isclose(score_a, score_b, rel_tol=1e-12, abs_tol=1e-12):
            ties += 1
        elif score_a > score_b:
            a_wins += 1
        else:
            b_wins += 1
    return a_wins, b_wins, ties


def main():
    with open(RESULTS_PATH) as f:
        data = json.load(f)

    # Determine which experiments appear in any query row.
    q_keys = sorted(data.keys())
    available_exps = [
        e for e in EXPERIMENTS
        if any(e in data[q_key].get("experiments", {}) for q_key in q_keys)
    ]

    run_issues: list[tuple[str, str, str]] = []
    for q_key in q_keys:
        q_data = data[q_key]
        try:
            resolve_expected_indices(q_data)
        except ValueError as exc:
            run_issues.append((q_key, "ground_truth", str(exc)))
        for exp in available_exps:
            exp_data = q_data.get("experiments", {}).get(exp)
            issue = detect_experiment_issue(exp_data)
            if issue:
                run_issues.append((q_key, exp, issue))

    if run_issues:
        print("=" * 120)
        print("SEMANTIC SEARCH EXPERIMENT EVALUATION REPORT")
        print("=" * 120)
        print("\nEvaluation aborted: benchmark artifact contains failed or unparseable search runs.")
        print("Fix the runtime environment and regenerate `eval_raw_results.json` before trusting any metrics.\n")
        print("Detected issues:")
        for q_key, exp, issue in run_issues[:20]:
            label = EXP_LABELS.get(exp, exp)
            print(f"  {q_key} | {label:<16} | {issue}")
        remaining = len(run_issues) - 20
        if remaining > 0:
            print(f"  ... and {remaining} more failures")
        raise SystemExit(1)

    all_metrics: dict[str, dict] = {}
    for q_key in q_keys:
        q_data = data[q_key]
        resolved_expected = resolve_expected_indices(q_data)
        all_metrics[q_key] = {
            "query": q_data["query"],
            "category": q_data["category"],
            "expected": resolved_expected,
            "expected_titles": q_data.get("expected_titles", []),
            "expected_raw_indices": q_data.get("expected_indices", []),
            "by_exp": {},
        }
        for exp in available_exps:
            parsed = q_data["experiments"][exp]["parsed"]
            all_metrics[q_key]["by_exp"][exp] = compute_metrics(
                parsed, resolved_expected
            )

    # ══════════════════════════════════════════════════════════════════
    print("=" * 120)
    print("SEMANTIC SEARCH EXPERIMENT EVALUATION REPORT")
    print("=" * 120)

    impossible_queries = []
    for q_key in q_keys:
        eff = _effective_expected(all_metrics[q_key]["expected"])
        if len(eff) > TOP_K:
            impossible_queries.append((q_key, all_metrics[q_key]["query"], len(eff)))
    available_set = set(available_exps)

    # ── SECTION 0: Benchmark Notes ──
    print("\n" + "─" * 120)
    print("SECTION 0: Benchmark Notes")
    print("─" * 120)
    print(
        f"  Corpus summary files: {RAW_SUMMARY_COUNT} | Canonical journal identities: {CANONICAL_JOURNAL_COUNT} "
        f"| Queries: {len(q_keys)} | Visible ranking depth: top-{TOP_K}"
    )
    if all(all_metrics[q_key]["expected_titles"] for q_key in q_keys):
        print("  Ground truth is title-based (resolved to current corpus indices at runtime).")
    else:
        print("  WARNING: legacy index-based ground truth detected; this can drift when corpus order changes.")
    if DUPLICATE_TITLE_GROUPS:
        print("  Duplicate title groups are canonicalized for evaluation:")
        for title, indices in sorted(DUPLICATE_TITLE_GROUPS.items()):
            print(f"    {title} -> {indices}")
    if impossible_queries:
        print(
            f"  {len(impossible_queries)} queries have more than {TOP_K} known relevant journals; "
            "classic Recall cannot reach 1.0 on those queries."
        )
        print(
            f"  Coverage@{TOP_K} caps the denominator at {TOP_K} so the top-{TOP_K} ranking target remains achievable."
        )
        for q_key, query, rel_count in impossible_queries:
            print(
                f"    {q_key}: {rel_count} relevant journals -> max classic Recall {TOP_K / rel_count:.2f} | {query}"
            )
    print(
        f"  All methods retrieve top-{CANDIDATE_DEPTH} candidates, deduplicate by journal (min distance), "
        f"and return top-{TOP_K} journals."
    )
    print(
        "  Distance summaries are descriptive only; absolute distance magnitudes are not directly comparable across indexes."
    )

    # ── SECTION 1: Per-Query Results ──
    print("\n" + "─" * 120)
    print("SECTION 1: Per-Query Results")
    print("─" * 120)

    header = (
        f"  {'Experiment':<16} {'MRR':>5} {'S@1':>4} {'S@3':>4}"
        f" {'nDCG@5':>7} {'JP':>5} {'R@5':>6} {'Cov@5':>6} {'#Uniq':>5}  Retrieved Journals"
    )
    for q_key in q_keys:
        qm = all_metrics[q_key]
        eff_expected = sorted(_effective_expected(qm["expected"]))
        print(f"\n{'─'*100}")
        print(f"[{q_key}] ({qm['category'].upper()}) {qm['query']}")
        if qm["expected_titles"]:
            print(f"  Expected titles: {qm['expected_titles']}")
        print(f"  Expected indices: {qm['expected_raw_indices']}")
        if sorted(qm["expected"]) != sorted(qm["expected_raw_indices"]):
            print(f"  Expected indices (resolved): {sorted(qm['expected'])}")
        if sorted(qm["expected"]) != eff_expected:
            print(f"  Expected canonical: {eff_expected}")
        if len(eff_expected) > TOP_K:
            print(
                f"  Note: {len(eff_expected)} relevant journals for a top-{TOP_K} list; "
                f"max classic Recall = {TOP_K / len(eff_expected):.2f}"
            )
        print(header)
        for exp in available_exps:
            m = qm["by_exp"][exp]
            print(
                f"  {EXP_LABELS[exp]:<16}"
                f" {m['mrr']:>5.2f}"
                f" {m['s1']:>4}"
                f" {m['s3']:>4}"
                f" {m['ndcg5']:>7.3f}"
                f" {m['jp']:>5.2f}"
                f" {m['recall']:>6.2f}"
                f" {m['coverage5']:>6.2f}"
                f" {m['unique_count']:>5}"
                f"  {m['retrieved_indices']}"
            )

    # ── SECTION 2: Aggregate Metrics by Experiment ──
    print("\n" + "─" * 120)
    print("SECTION 2: Aggregate Metrics by Experiment")
    print("─" * 120)

    agg_header = (
        f"    {'Category':<14}"
        f" {'AvgMRR':>7}"
        f" {'S@1%':>6}"
        f" {'S@3%':>6}"
        f" {'nDCG@5':>7}"
        f" {'JP':>6}"
        f" {'R@5':>7}"
        f" {'Cov@5':>7}"
        f" {'AvgUniq':>8}"
    )

    for exp in available_exps:
        print(f"\n  {EXP_LABELS[exp]}:")
        print(agg_header)
        for cat in CATEGORIES + ["ALL"]:
            keys = [
                k for k in q_keys
                if cat == "ALL" or all_metrics[k]["category"] == cat
            ]
            if not keys:
                continue
            n = len(keys)
            avg_mrr = sum(all_metrics[k]["by_exp"][exp]["mrr"] for k in keys) / n
            s1_pct = sum(all_metrics[k]["by_exp"][exp]["s1"] for k in keys) / n * 100
            s3_pct = sum(all_metrics[k]["by_exp"][exp]["s3"] for k in keys) / n * 100
            avg_ndcg = sum(all_metrics[k]["by_exp"][exp]["ndcg5"] for k in keys) / n
            avg_jp = sum(all_metrics[k]["by_exp"][exp]["jp"] for k in keys) / n
            avg_r = sum(all_metrics[k]["by_exp"][exp]["recall"] for k in keys) / n
            avg_cov = sum(all_metrics[k]["by_exp"][exp]["coverage5"] for k in keys) / n
            avg_uniq = sum(all_metrics[k]["by_exp"][exp]["unique_count"] for k in keys) / n
            label = f"═══ ALL ═══" if cat == "ALL" else cat.upper()
            print(
                f"    {label:<14}"
                f" {avg_mrr:>7.3f}"
                f" {s1_pct:>5.1f}%"
                f" {s3_pct:>5.1f}%"
                f" {avg_ndcg:>7.3f}"
                f" {avg_jp:>6.3f}"
                f" {avg_r:>7.3f}"
                f" {avg_cov:>7.3f}"
                f" {avg_uniq:>8.1f}"
            )

    # ── SECTION 3: Head-to-Head ──
    print("\n" + "─" * 120)
    print(f"SECTION 3: HEAD-TO-HEAD COMPARISON (journal-discovery composite = MRR + nDCG@5 + Coverage@{TOP_K})")
    print("─" * 120)

    # Summary-level
    summary_exps = [e for e in ["full_blob", "structured_fields", "grouped_structured"] if e in available_exps]
    if len(summary_exps) >= 2:
        print("\n  ▸ SUMMARY-LEVEL:")
        wins = {e: 0 for e in summary_exps}
        ties = 0
        for q_key in q_keys:
            scores = {e: composite_score(all_metrics[q_key]["by_exp"][e]) for e in summary_exps}
            best_score = max(scores.values())
            winners = [e for e, s in scores.items() if s == best_score]
            if len(winners) == len(summary_exps):
                ties += 1
            else:
                for w in winners:
                    wins[w] += 1
        parts = [f"{EXP_LABELS[e]} wins: {wins[e]}" for e in summary_exps]
        print(f"    {'  |  '.join(parts)}  |  Ties: {ties}")

    # Transcript-level (semantic, enriched, sentence chunk variants)
    transcript_exps = [
        e for e in [
            "semantic_chunks",
            "enriched_chunks",
            "sentence_chunks_512",
            "sentence_chunks_1024",
            "sentence_chunks_2048",
            "grouped_semantic_chunks",
            "grouped_enriched_chunks",
            "grouped_sentence_chunks_512",
            "grouped_sentence_chunks_1024",
            "grouped_sentence_chunks_2048",
        ]
        if e in available_exps
    ]
    if len(transcript_exps) >= 2:
        print("\n  ▸ TRANSCRIPT-LEVEL:")
        wins = {e: 0 for e in transcript_exps}
        ties = 0
        for q_key in q_keys:
            scores = {e: composite_score(all_metrics[q_key]["by_exp"][e]) for e in transcript_exps}
            best_score = max(scores.values())
            winners = [e for e, s in scores.items() if s == best_score]
            if len(winners) == len(transcript_exps):
                ties += 1
            else:
                for w in winners:
                    wins[w] += 1
        parts = [f"{EXP_LABELS[e]} wins: {wins[e]}" for e in transcript_exps]
        print(f"    {'  |  '.join(parts)}  |  Ties: {ties}")

    # Cross-level ranking
    print("\n  ▸ CROSS-LEVEL RANKING (by avg composite):")
    exp_composites = []
    for exp in available_exps:
        avg = sum(composite_score(all_metrics[k]["by_exp"][exp]) for k in q_keys) / len(q_keys)
        exp_composites.append((exp, avg))
    exp_composites.sort(key=lambda x: x[1], reverse=True)
    for rank, (exp, avg) in enumerate(exp_composites, 1):
        print(f"    {rank}. {EXP_LABELS[exp]:<16} composite={avg:.3f}")

    # ── SECTION 3.5: Fair Comparison Tracks ──
    print("\n" + "─" * 120)
    print("SECTION 3.5: Fair Comparison Tracks")
    print("─" * 120)

    same_budget_names = [
        "semantic_chunks",
        "grouped_semantic_chunks",
        "sentence_chunks_512",
        "sentence_chunks_1024",
        "sentence_chunks_2048",
        "grouped_sentence_chunks_512",
        "grouped_sentence_chunks_1024",
        "grouped_sentence_chunks_2048",
    ]
    enriched_names = [
        "full_blob",
        "structured_fields",
        "grouped_structured",
        "enriched_chunks",
        "grouped_enriched_chunks",
    ]

    for track_label, track_names, track_desc in [
        (
            "Track A: Same Information Budget (strict retriever comparison)",
            same_budget_names,
            "Transcript-level methods that index the same raw information without enrichment.",
        ),
        (
            "Track B: Enriched Data (product-oriented comparison)",
            enriched_names,
            "Methods that index enriched/summary data (summaries, structured fields, enriched transcripts).",
        ),
    ]:
        track_exps = [e for e in track_names if e in available_exps]
        print(f"\n  ▸ {track_label}")
        print(f"    {track_desc}")
        print(f"    Experiments: {', '.join(EXP_LABELS[e] for e in track_exps)}")

        if len(track_exps) < 2:
            print("    (fewer than 2 experiments available — skipping)")
            continue

        # Ranking by avg composite
        track_composites = []
        for exp in track_exps:
            avg = sum(composite_score(all_metrics[k]["by_exp"][exp]) for k in q_keys) / len(q_keys)
            track_composites.append((exp, avg))
        track_composites.sort(key=lambda x: x[1], reverse=True)
        print("\n    Ranking (by avg composite):")
        for rank, (exp, avg) in enumerate(track_composites, 1):
            print(f"      {rank}. {EXP_LABELS[exp]:<16} composite={avg:.3f}")

        # Pairwise win counts
        print("\n    Pairwise win counts:")
        wins = {e: 0 for e in track_exps}
        ties = 0
        for q_key in q_keys:
            scores = {e: composite_score(all_metrics[q_key]["by_exp"][e]) for e in track_exps}
            best_score = max(scores.values())
            winners = [e for e, s in scores.items() if s == best_score]
            if len(winners) == len(track_exps):
                ties += 1
            else:
                for w in winners:
                    wins[w] += 1
        parts = [f"{EXP_LABELS[e]} wins: {wins[e]}" for e in track_exps]
        print(f"      {'  |  '.join(parts)}  |  Ties: {ties}")

    # ── SECTION 4: Structured Fields — Field Attribution ──
    print("\n" + "─" * 120)
    print("SECTION 4: Structured Fields — Field Attribution")
    print("─" * 120)
    if "structured_fields" in available_exps:
        field_counts: dict[str, int] = {}
        field_hit_counts: dict[str, int] = {}
        for q_key in q_keys:
            qm = all_metrics[q_key]
            eff = _effective_expected(qm["expected"])
            m = qm["by_exp"]["structured_fields"]
            for i, et in enumerate(m["embedding_types"]):
                field_type = et.split("(")[0] if "(" in et else et
                field_counts[field_type] = field_counts.get(field_type, 0) + 1
                idx = m["per_result_indices"][i]
                if idx is not None and idx in eff:
                    field_hit_counts[field_type] = field_hit_counts.get(field_type, 0) + 1
        print(f"  {'Field Type':<12} {'Total':>6} {'Relevant':>9} {'Hit Rate':>10}")
        for ft in sorted(field_counts.keys()):
            total = field_counts[ft]
            hits = field_hit_counts.get(ft, 0)
            rate = hits / total * 100 if total else 0
            print(f"  {ft:<12} {total:>6} {hits:>9} {rate:>9.1f}%")
    else:
        print("  (structured_fields not available)")

    # ── SECTION 5: Distance Distribution ──
    print("\n" + "─" * 120)
    print("SECTION 5: Distance Distribution (descriptive only)")
    print("─" * 120)
    for exp in available_exps:
        all_d1, all_d5, all_spreads = [], [], []
        for q_key in q_keys:
            dists = all_metrics[q_key]["by_exp"][exp]["distances"]
            if dists:
                all_d1.append(dists[0])
                all_d5.append(dists[-1])
                all_spreads.append(dists[-1] - dists[0])
        if not all_d1:
            print(f"  {EXP_LABELS[exp]:<16}  no distance data")
            continue
        print(
            f"  {EXP_LABELS[exp]:<16}"
            f"  AvgDist#1={sum(all_d1)/len(all_d1):.4f}"
            f"  AvgDist#5={sum(all_d5)/len(all_d5):.4f}"
            f"  AvgSpread={sum(all_spreads)/len(all_spreads):.4f}"
        )

    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 120)
    print("FINAL VERDICT")
    print("=" * 120)

    metric_names = ["AvgMRR", "S@1%", "S@3%", "nDCG@5", "JP", "R@5", "Cov@5", "AvgUniq"]
    print(
        f"\n  {'Experiment':<16} {metric_names[0]:>7} {metric_names[1]:>6} {metric_names[2]:>6} "
        f"{metric_names[3]:>7} {metric_names[4]:>6} {metric_names[5]:>7} {metric_names[6]:>7} {metric_names[7]:>8}"
    )
    print(f"  {'─'*16} {'─'*7} {'─'*6} {'─'*6} {'─'*7} {'─'*6} {'─'*7} {'─'*7} {'─'*8}")

    exp_final_scores = {}
    for exp in available_exps:
        n = len(q_keys)
        avg_mrr = sum(all_metrics[k]["by_exp"][exp]["mrr"] for k in q_keys) / n
        s1 = sum(all_metrics[k]["by_exp"][exp]["s1"] for k in q_keys) / n * 100
        s3 = sum(all_metrics[k]["by_exp"][exp]["s3"] for k in q_keys) / n * 100
        avg_ndcg = sum(all_metrics[k]["by_exp"][exp]["ndcg5"] for k in q_keys) / n
        avg_jp = sum(all_metrics[k]["by_exp"][exp]["jp"] for k in q_keys) / n
        avg_r = sum(all_metrics[k]["by_exp"][exp]["recall"] for k in q_keys) / n
        avg_cov = sum(all_metrics[k]["by_exp"][exp]["coverage5"] for k in q_keys) / n
        avg_uniq = sum(all_metrics[k]["by_exp"][exp]["unique_count"] for k in q_keys) / n
        exp_final_scores[exp] = avg_mrr + avg_ndcg + avg_cov
        print(
            f"  {EXP_LABELS[exp]:<16}"
            f" {avg_mrr:>7.3f}"
            f" {s1:>5.1f}%"
            f" {s3:>5.1f}%"
            f" {avg_ndcg:>7.3f}"
            f" {avg_jp:>6.3f}"
            f" {avg_r:>7.3f}"
            f" {avg_cov:>7.3f}"
            f" {avg_uniq:>8.1f}"
        )

    summary_pool = [e for e in ["full_blob", "structured_fields", "grouped_structured"] if e in available_exps]
    transcript_pool = [
        e for e in [
            "semantic_chunks",
            "enriched_chunks",
            "sentence_chunks_512",
            "sentence_chunks_1024",
            "sentence_chunks_2048",
            "grouped_semantic_chunks",
            "grouped_enriched_chunks",
            "grouped_sentence_chunks_512",
            "grouped_sentence_chunks_1024",
            "grouped_sentence_chunks_2048",
        ]
        if e in available_exps
    ]


if __name__ == "__main__":
    main()