# Weavy Evaluation — LongMemEval

Weavy is evaluated against [LongMemEval](https://github.com/xiaowu0162/LongMemEval), a benchmark for long-term memory in chat assistants (ICLR 2025). This document covers everything you need to know to run evaluations, interpret results, and use Langfuse for observability.

---

## What LongMemEval Measures

LongMemEval presents a system with a history of timestamped chat sessions, then asks a question that requires recalling and reasoning over that history. It tests five core abilities:

| Ability | Description |
|---|---|
| Information extraction | Recall a specific fact from a past session |
| Multi-session reasoning | Synthesise information across multiple sessions |
| Knowledge updates | Track when a piece of information changed over time |
| Temporal reasoning | Answer questions about timing, duration, or sequence |
| Abstention | Refuse to answer when the information was never stated |

These map to six **question types** that appear in the metrics output:

| Question type | What it tests |
|---|---|
| `single-session-user` | User stated something in one session |
| `single-session-assistant` | Assistant stated something in one session |
| `single-session-preference` | User expressed a preference in one session |
| `temporal-reasoning` | Time-based calculation across sessions |
| `knowledge-update` | Information was updated; return the latest value |
| `multi-session` | Answer requires combining facts from multiple sessions |

Questions whose IDs end in `_abs` are **abstention questions** — the correct answer is to say the information is not available.

---

## The Three Dataset Variants

Place data files in `eval/data/` (gitignored). Download from the [LongMemEval releases](https://github.com/xiaowu0162/LongMemEval).

| Flag | File | Sessions per instance | What it tests |
|---|---|---|---|
| `--dataset oracle` | `longmemeval_oracle.json` | 3–5 (evidence only) | Can Weavy answer when given exactly the right sessions? |
| `--dataset s` | `longmemeval_s.json` | ~40 (~115k tokens) | Can Weavy retrieve and answer from a small haystack? |
| `--dataset m` | `longmemeval_m.json` | ~500 sessions | Can Weavy retrieve and answer from a large haystack? |

**Which to start with:** `oracle`. It removes retrieval from the equation and isolates answer quality. Run `s` and `m` once oracle scores are good — the gap between oracle and S/M tells you how much Weavy's semantic search is losing.

All three have 500 questions. Each question has the same ground truth answer regardless of dataset variant — only the amount of noise (irrelevant sessions) differs.

---

## What We Measure

**Captured by this eval harness:**

- QA accuracy per question type
- Overall accuracy (all 500 instances)
- Task-averaged accuracy (mean of per-category accuracies)
- Abstention accuracy

**Not captured** (would require instrumenting Weavy's query agent to record which graph nodes it accessed):

- Session-level memory recall (did retrieval find the right sessions?)
- Turn-level memory recall (did retrieval find the right turns?)

For benchmarking Weavy's progress over time, QA accuracy is the primary signal.

---

## Architecture

```
eval/
  eval.py           — unified CLI: run / status / reset / judge / score / metrics
  evaluate_qa.py    — patched LongMemEval judge (litellm instead of openai)
  data/             — gitignored; place dataset JSON files here
  .state/           — gitignored; per-dataset checkpoint files
    oracle/
      results.jsonl       one line per answered instance
      eval_results.jsonl  one line per judged instance
    s/
      results.jsonl
      eval_results.jsonl
    m/
      ...
```

**Zero changes to `weavy/`.** The harness is a pure consumer of the public SDK.

**Per-instance flow:**
1. `w.reset()` — drop and reinitialise the isolated `longmemeval` graph
2. `w.add(session_text, timestamp=session_date)` — ingest each haystack session
3. `w.query(question, query_time=question_date)` — query at the benchmark's fixed timestamp
4. Record `hypothesis` + `trace_id` (the Langfuse trace ID) to `results.jsonl`

The `longmemeval` graph is isolated from your main Weavy graph (`weavy`). It is wiped clean before each instance so sessions from one question never bleed into another.

---

## Commands

All commands accept `--dataset oracle|s|m` (default: `oracle`) or `--data PATH` for a custom file. The two are mutually exclusive.

### `run` — ingest and query

```bash
uv run eval/eval.py run --dataset oracle
uv run eval/eval.py run --dataset oracle --limit 10   # test with first 10 pending
uv run eval/eval.py run --dataset s
```

Processes each pending instance: reset → ingest all sessions → query. Automatically resumes from the last checkpoint — if it crashes or is interrupted, just run it again. `--limit N` processes at most N pending instances in this invocation; run without it to continue.

**Output per instance:**
```
[42/500] q123_temporal  (temporal-reasoning)  — 4 session(s)
  ingest [1/4] 2024-01-15  ✓
  ingest [2/4] 2024-03-02  ✓
  ingest [3/4] 2024-06-10  ✓
  ingest [4/4] 2024-09-20  ✓
  query  ✓  trace=a3f7c1b2e509
  → The user mentioned switching from Python to Go in March 2024…
```

Each `w.add()` and `w.query()` call emits a Langfuse trace automatically (if Langfuse is configured). The `trace=` prefix shows the first 12 characters of the Langfuse trace ID.

---

### `status` — progress overview

```bash
uv run eval/eval.py status --dataset oracle
uv run eval/eval.py status --dataset s
```

Shows answered/judged counts, overall accuracy, per-category accuracy with progress bars, and the Langfuse host URL.

```
────────────────────────────────────────────────────────
  Weavy / LongMemEval  [oracle]
────────────────────────────────────────────────────────
  Answered :  500 / 500  (100.0%)
  Judged   :  500 / 500  (100.0%)
  Correct  :  347 / 500  (69.4%)  ██████████████░░░░░░

  By category:
    knowledge-update              ████████████████░░░░   81/100   81.0%
    multi-session                 ██████████████░░░░░░   72/100   72.0%
    single-session-assistant      ████████████████████   83/ 83  100.0%
    ...

  Langfuse :  http://localhost:3100
             score names: longmemeval/correct, longmemeval/<category>
────────────────────────────────────────────────────────
```

Works without a live FalkorDB connection — reads from `.state/` only.

---

### `judge` — run LLM-as-judge

```bash
uv run eval/eval.py judge --dataset oracle
uv run eval/eval.py judge --dataset oracle --model gemini/gemini-2.5-flash-lite
uv run eval/eval.py judge --dataset oracle --model gpt-4o
```

Runs the LLM judge over all un-judged hypotheses and appends to `eval_results.jsonl`. Also auto-resumes — already-judged instances are skipped.

The judge model can be any [LiteLLM-supported model string](https://docs.litellm.ai/docs/providers). Default is `gemini/gemini-2.5-flash-lite`.

**Comparability note:** Published LongMemEval leaderboard scores use `gpt-4o` as judge. Results with a different judge are not directly comparable to published numbers, but are fully valid for tracking Weavy's own progress across runs. Pick one model and keep it consistent between runs.

The judge prompt logic is unchanged from the original LongMemEval `evaluate_qa.py` — only the model call was patched from `openai` SDK to `litellm`.

---

### `score` — post to Langfuse

```bash
uv run eval/eval.py score --dataset oracle
```

Posts two Langfuse scores to each query trace:

| Score name | Type | What it is |
|---|---|---|
| `longmemeval/correct` | BOOLEAN | 1 = correct, 0 = incorrect |
| `longmemeval/{category}` | BOOLEAN | Same value, scoped to question type |

The per-category scores let Langfuse's Scores page aggregate each question type independently. In the Langfuse UI you get separate charts for `longmemeval/temporal-reasoning`, `longmemeval/multi-session`, etc. — the exact breakdown LongMemEval reports.

Requires Langfuse credentials in `.env` (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`).

---

### `metrics` — accuracy table

```bash
uv run eval/eval.py metrics --dataset oracle
```

Prints the full LongMemEval metrics table locally — no Langfuse needed:

```
────────────────────────────────────────────────────────
  LongMemEval accuracy  [oracle]
────────────────────────────────────────────────────────
  knowledge-update                  ████████████████░░░░  0.8100  (100)
  multi-session                     ██████████████░░░░░░  0.7200  (100)
  single-session-assistant          ████████████████████  1.0000  ( 83)
  single-session-preference         ██████████████░░░░░░  0.7100  ( 50)
  single-session-user               ███████████████░░░░░  0.7400  ( 67)
  temporal-reasoning                ████████████░░░░░░░░  0.6000  (100)
────────────────────────────────────────────────────────
  Task-averaged accuracy : 0.7300
  Overall accuracy       : 0.6940  (500 instances)
  Abstention accuracy    : 0.8200  (50)
────────────────────────────────────────────────────────
```

**Task-averaged accuracy** is the primary comparable metric from the paper — it is the mean of per-category accuracies (not the overall count). Use this when comparing to published numbers.

---

### `reset` — clear state

```bash
uv run eval/eval.py reset --dataset oracle          # reset oracle state only
uv run eval/eval.py reset --all                     # reset all datasets
uv run eval/eval.py reset --dataset oracle --force  # skip confirmation
```

Deletes `results.jsonl` and `eval_results.jsonl` for the specified dataset. Does not touch the FalkorDB graph (it is wiped per-instance during `run` anyway).

---

## Standard Workflow

```bash
# 1. Place data files
#    eval/data/longmemeval_oracle.json
#    eval/data/longmemeval_s.json     (optional)
#    eval/data/longmemeval_m.json     (optional)

# 2. Run eval — oracle first
uv run eval/eval.py run --dataset oracle

# 3. Check progress mid-run (separate terminal)
uv run eval/eval.py status --dataset oracle

# 4. Judge answers
uv run eval/eval.py judge --dataset oracle --model gemini/gemini-2.5-flash-lite

# 5. Push scores to Langfuse
uv run eval/eval.py score --dataset oracle

# 6. Print metrics table
uv run eval/eval.py metrics --dataset oracle

# 7. Iterate on Weavy, then reset and re-run to measure improvement
uv run eval/eval.py reset --dataset oracle
uv run eval/eval.py run --dataset oracle
```

For quick iteration while developing, use `--limit` to test on a small slice:

```bash
uv run eval/eval.py run --dataset oracle --limit 20
uv run eval/eval.py judge --dataset oracle
uv run eval/eval.py metrics --dataset oracle
```

---

## Using Langfuse for Observability

Every `w.add()` and `w.query()` call during `run` creates a Langfuse trace automatically. After `score`, each query trace has correctness scores attached.

**In the Langfuse UI:**

- **Traces page** — filter by `longmemeval/correct = 0` to see every failing question. Drill into any trace to inspect the full agent reasoning: which tool calls were made, what the search queries looked like, what was retrieved.
- **Scores page** — aggregated pass rate per score name. `longmemeval/correct` shows overall, `longmemeval/temporal-reasoning` shows just that category.
- **Comparing runs** — run Weavy v1 → score → run Weavy v2 → score. Filter traces by date range to compare score distributions between the two runs.

The `comment` field on each score includes `dataset=oracle category=temporal-reasoning` for additional filtering context.

---

## Standalone Judge

`evaluate_qa.py` can also be called directly without `eval.py`:

```bash
uv run eval/evaluate_qa.py gemini/gemini-2.5-flash-lite hyp.jsonl ref.json [out.jsonl]
```

Input `hyp.jsonl`: one JSON object per line with at least `question_id` and `hypothesis`. Output: same lines with `autoeval_label: {model, label}` appended.

---

## Environment Variables

The eval harness inherits all of Weavy's environment variables. Relevant ones:

| Variable | Purpose |
|---|---|
| `GEMINI_MODEL` | Weavy agent model (default: `gemini/gemini-2.5-flash`) |
| `LANGFUSE_PUBLIC_KEY` | Required for `score` command |
| `LANGFUSE_SECRET_KEY` | Required for `score` command |
| `LANGFUSE_HOST` | Langfuse server URL (default: `http://localhost:3100`) |
| `FALKORDB_HOST` / `PORT` | FalkorDB connection |

The judge model (`--model`) is set at the CLI, not via environment variable, so you can switch judge models between runs without touching `.env`.
