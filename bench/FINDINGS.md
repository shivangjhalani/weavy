# Weavy benchmark iteration — findings

Branch `weavy-bench-iteration`. Method: empirical, fundamentals-first, no
result-gaming. All LLM calls on `gpt-4o-mini`, session granularity, themes on.

## Headline

Full LoCoMo (10 conv, 1986 questions): **27.9% overall recall** (run `150201`,
`reports/full_getedge/`). Adversarial abstention 73.1%.

## Root cause (decisive): extraction density gates accuracy, and it is stochastic

Per-conversation accuracy correlates directly with how much the ingestion agent
captured:

| conv | nodes | recall acc |
|------|-------|-----------|
| conv-30 | 23 | 17.3% |
| conv-26 | 22 | 18.4% |
| conv-48 | 86 | 22.0% |
| conv-41 | 66 | 31.6% |
| conv-43 | 65 | 34.8% |

The clincher: **conv-26 scored 18.4% with 22 nodes in this run, but ~42% on an
earlier graph of the same conversation with 67 nodes** — same questions, same
query code. 3× the nodes → 2.3× the accuracy.

Extraction is highly stochastic: similar-length conversations ingest to anywhere
from 22 to 88 nodes. A 24-session dialogue rich with concrete personal facts
(pets named Oliver/Luna/Bailey, books, songs) often compresses to <30 nodes,
dropping exactly the autobiographical specifics later questions ask for. The
query side is **not** the bottleneck — when a fact is in the graph, it retrieves.

## What was tried

1. **Ingestion-prompt change to preserve concrete specifics** (capture pets,
   books, events as discrete searchable facts). Re-ingested conv-26 + full eval:
   **35.5% vs 42.7% baseline — worse.** Diff: 21 questions newly fixed (concrete
   particulars), 45 newly broken (identity/attribute/symbolism). Lesson: with a
   bounded-capacity extractor, exhortation does not add capture — it *reallocates
   attention*, here trading attribute recall for detail recall, net negative.
   **Reverted** (would have been overfitting, and did not help).

2. **`get_edge` read tool** (commit `ed5534e`). The query prompt instructs the
   agent to "inspect the edge's log" for temporal / relationship-change
   questions, but no tool existed to fetch an edge by id — the agent was observed
   erroring with `get_node('edge:1')`. `store.graph.get_edge` already existed;
   this exposes it. Same-graph A/B: 42.2% vs 42.7% baseline — net-neutral
   aggregate, small gains in temporal (45.9→48.6%) and open_domain (30.8→38.5%),
   regresses nothing, tested. Kept as a correctness/completeness fix.

## Methodological notes

- Single-conversation accuracy has ±2–3 pts of pure query-stochastic noise
  (same graph, same code: 42.7 vs 42.2). Small query-side fixes can only be
  validated on the full 10-conversation set.
- A query-only diagnostic (`bench/_diag.py`) runs the QA set against an
  already-ingested graph, so query-side iteration costs ~$0.5 instead of a
  ~14-min/$0.1 re-ingest.

## Other real issues found (not fixed — would be fragile or unvalidatable here)

- **Cross-entity summary contamination.** `update_node` replaces a node's summary
  wholesale with no identity guard; observed node `Melanie` rewritten to a summary
  about Caroline's adoption. Hard to fix at the store layer without semantics.
- **Summary decay.** One-sentence entity summaries + wholesale overwrite means
  specifics decay across updates; old detail survives only in log notes, which
  `search_graph` never reads (it scans aliases + summary only).
- **Keyword search is full-substring `CONTAINS`** — useless for multi-word
  queries; recall leans entirely on top-10 vector search.
- **Dataset noise.** Some LoCoMo gold labels are unanswerable: e.g. "When did
  Melanie paint a sunrise? → 2022" cites evidence D1:12, which is a *sunset over
  a lake* caption with no year. Do not tune toward these.

## The real lever (future work, deliberately not done — cost/validation bound)

Accuracy is gated by ingestion recall. Prompt exhortation is a wash. The
principled levers all trade cost or context: finer ingest granularity (smaller
chunks → less forced dropping), a stronger ingest model, or multi-pass
extraction. Each needs a full-set re-run (~$14) to validate, so none was applied
speculatively.

## Cost

Full run $14.06 (answer $12.94 at ~43k tok/q — the query agent over-searches;
ingest $1.05; judge $0.08). Total iteration spend ~$16.
