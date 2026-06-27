# Weavy benchmark harness

A standalone, system-agnostic harness for evaluating memory layers on
[LoCoMo](https://github.com/snap-research/locomo). It treats the memory system as
a black box behind a three-method adapter, so Weavy today and mem0/graphiti later
run through the *exact same* harness, judge, and metrics.

Nothing under `weavy/` imports from `bench/` — the dependency points one way.

## Quick start

```bash
# 0) services + provider key
docker compose --profile falkordb up -d
export OPENAI_API_KEY=sk-...

# 1) fetch the dataset (once) -> bench/data/locomo10.json
uv run python -m bench.run download

# 2) smoke test: 1 conversation, a few questions
uv run python -m bench.run run --limit-conversations 1 --limit-questions 5

# 3) full run (Weavy, gpt-4o-mini, themes on)
uv run python -m bench.run run

# 4) ablations — does the theme layer / caller-context actually help recall?
uv run python -m bench.run run --no-themes
uv run python -m bench.run run --no-context
```

### Observability (Langfuse)

If `LANGFUSE_*` keys are set, Weavy already emits a full agent trace per
`add`/`query` for free. On top of that, the harness attaches the eval verdict as
**scores** to each query trace (Weavy sets the Langfuse `trace_id` to the run id,
so the link is exact and needs no Weavy coupling):

| Score | Type | Use |
|---|---|---|
| `correct` | numeric 0/1 | the J verdict; comment holds the judge's reason |
| `category` | categorical | filter by single_hop / multi_hop / temporal / open_domain |
| `answer_tokens` | numeric | per-question cost |
| `answer_latency_ms` | numeric | per-question latency |

Each score carries `bench_run_id`, `category`, and `themes` in its metadata, so in
the Langfuse UI you can filter to (say) `correct = 0` and `category = multi_hop`
and click straight into the failing agent trace. `results.jsonl` also carries the
`trace_id` per row for the same correlation offline. Disable with `--no-langfuse`.

Scoring is **best-effort and decoupled**: no Langfuse keys, `--no-langfuse`, or a
non-Weavy adapter (no `trace_id` in `extra`) simply skips scoring — it never
breaks a run, and the system-agnostic `summary.md` / `results.jsonl` remain the
source of truth.

Reports land in `bench/reports/<run_id>_<label>/`:

- `summary.md` — accuracy by category, efficiency, and published reference lines
- `summary.json` — the same numbers, machine-readable
- `results.jsonl` — one record per question (gold, prediction, judge verdict +
  reason, tokens, latency, consulted nodes) for error analysis
- `config.json` — the exact run configuration

## What it measures

| Metric | Meaning |
|---|---|
| accuracy by category | single-hop / multi-hop / temporal / open-domain (LLM-judge "J") |
| overall recall | mean over the four recall categories (adversarial excluded) |
| adversarial abstention | category 5 scored separately — did the system refuse the false premise? |
| answer tokens/question | retrieval+answer cost per query |
| ingest tokens, latency, USD cost | efficiency / the accuracy-vs-cost frontier |

## Methodology decisions (and why)

- **Backbone**: gpt-4o-mini + text-embedding-3-small — the standard LoCoMo stack,
  for comparability with published numbers.
- **Ingestion granularity**: one episode **per session** (session date as the
  event timestamp). Preserves temporal structure and gives the ingestion agent
  coherent context. `--granularity turn|conversation` available for ablations.
- **Themes on by default**: themes feed both the ingestion and query agents, so
  this benchmarks the system as shipped. `--no-themes` isolates raw retrieval.
- **Caller context on at ingest, off at query**: a minimal, neutral hint ("a chat
  between X and Y") is passed at ingestion — realistic, non-leaking, and what a
  real integration would supply. Questions are asked with no context. `--no-context`
  runs the pure source-agnostic variant.
- **Judge**: gpt-4o-mini LLM-as-judge, binary correct/incorrect, separate rubric
  for adversarial questions.
- **Adversarial**: excluded from the headline (matches most papers) and reported
  as a standalone abstention score.
- **Execution**: two phases — ingest all graphs in parallel (`--ingest-workers`),
  then answer all questions from a shared pool (`--query-workers`, each worker its
  own connection). Single run, no error bars.

> ⚠️ Reference lines in `summary.md` are **self-reported on other harnesses** and
> the public Mem0/Zep dispute showed ±15-point swings on this benchmark. They are
> orientation, not a like-for-like comparison. For a true comparison, run a rival
> through this harness (below).

## Adding another memory system (mem0, graphiti, ...)

1. Create `bench/adapters/mem0_adapter.py` implementing the
   [`MemorySystem`](adapters/base.py) protocol — `reset()`, `ingest(episodes)`,
   `answer(question, at)`.
2. Add a branch in `_build_factory` in [`run.py`](run.py).
3. `uv run python -m bench.run run --system mem0`.

No harness, judge, dataset, or metrics changes required — that's the point of the
adapter boundary.

## Layout

```
bench/
  adapters/
    base.py            # MemorySystem protocol + Episode/AnswerResult/IngestStats
    weavy_adapter.py   # the ONLY module that imports weavy
  datasets/
    locomo.py          # locomo10.json -> typed Conversations / QAItems / Episodes
  harness/
    judge.py           # LLM-as-judge (J score), recall + adversarial rubrics
    metrics.py         # aggregation, cost table, markdown summary
    runner.py          # parallel ingest -> answer -> judge orchestration
  observability.py     # optional Langfuse eval-scoring (decoupled, best-effort)
  reference.py         # published reference lines + citations
  run.py               # CLI: download / run
```
