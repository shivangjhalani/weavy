# Weavy Evaluation — LongMemEval

Weavy is evaluated against [LongMemEval](https://github.com/xiaowu0162/LongMemEval), a benchmark for long-term memory in chat assistants (ICLR 2025). The eval harness uses **Langfuse Datasets + Experiments** for full observability: dataset management, experiment comparison, built-in LLM-as-judge scoring, and aggregate metrics — all visible in the Langfuse UI.

---

## What LongMemEval Measures

LongMemEval presents a system with a history of timestamped chat sessions, then asks a question that requires recalling and reasoning over that history. It tests five core abilities:

| Ability                 | Description                                            |
| ----------------------- | ------------------------------------------------------ |
| Information extraction  | Recall a specific fact from a past session             |
| Multi-session reasoning | Synthesise information across multiple sessions        |
| Knowledge updates       | Track when a piece of information changed over time    |
| Temporal reasoning      | Answer questions about timing, duration, or sequence   |
| Abstention              | Refuse to answer when the information was never stated |

These map to six **question types** that appear in the metrics output:

| Question type               | What it tests                                          |
| --------------------------- | ------------------------------------------------------ |
| `single-session-user`       | User stated something in one session                   |
| `single-session-assistant`  | Assistant stated something in one session              |
| `single-session-preference` | User expressed a preference in one session             |
| `temporal-reasoning`        | Time-based calculation across sessions                 |
| `knowledge-update`          | Information was updated; return the latest value       |
| `multi-session`             | Answer requires combining facts from multiple sessions |

Questions whose IDs end in `_abs` are **abstention questions** — the correct answer is to say the information is not available.

---

## The Three Dataset Variants

Place data files in `eval/data/` (gitignored). Download from the [LongMemEval releases](https://github.com/xiaowu0162/LongMemEval).

| Flag               | File                      | Sessions per instance | What it tests                                           |
| ------------------ | ------------------------- | --------------------- | ------------------------------------------------------- |
| `--dataset oracle` | `longmemeval_oracle.json` | 3–5 (evidence only)   | Can Weavy answer when given exactly the right sessions? |
| `--dataset s`      | `longmemeval_s.json`      | ~40 (~115k tokens)    | Can Weavy retrieve and answer from a small haystack?    |
| `--dataset m`      | `longmemeval_m.json`      | ~500 sessions         | Can Weavy retrieve and answer from a large haystack?    |

**Which to start with:** `oracle`. It removes retrieval from the equation and isolates answer quality. Run `s` and `m` once oracle scores are good — the gap between oracle and S/M tells you how much Weavy's semantic search is losing.

All three have 500 questions. Each question has the same ground truth answer regardless of dataset variant — only the amount of noise (irrelevant sessions) differs.

---

## What We Measure

**Scores attached per item (via LLM-as-judge evaluator):**

| Score name               | Type    | What it is                          |
| ------------------------ | ------- | ----------------------------------- |
| `longmemeval/correct`    | BOOLEAN | 1 = correct, 0 = incorrect          |
| `longmemeval/{category}` | BOOLEAN | Same value, scoped to question type |

**Aggregate scores (via run-level evaluator):**

| Score name                           | What it is                                                  |
| ------------------------------------ | ----------------------------------------------------------- |
| `longmemeval/overall_accuracy`       | Correct / total                                             |
| `longmemeval/task_averaged_accuracy` | Mean of per-category accuracies (primary comparable metric) |
| `longmemeval/abstention_accuracy`    | Accuracy on abstention questions only                       |

**Not captured** (would require instrumenting Weavy's query agent to record which graph nodes it accessed):

- Session-level memory recall (did retrieval find the right sessions?)
- Turn-level memory recall (did retrieval find the right turns?)

---

## Architecture

```
eval/
  eval.py           — unified CLI: upload / run / status / metrics / reset
  evaluate_qa.py    — LongMemEval judge prompts + litellm judge call
  data/             — gitignored; place dataset JSON files here
```

State lives in **Langfuse**, not local files. Each LongMemEval instance is a Langfuse dataset item. Each `run` invocation creates a Langfuse experiment run with traces, scores, and aggregate metrics.

The harness uses the `weavy.application` layer directly (`run_add`, `run_theme_update`, `run_query`). Themes are updated after every successful session ingestion — matching `Weavy.add()` behavior.

**Per-instance flow (inside the experiment task function):**

1. Reset the isolated `longmemeval` graph (drop + reinitialise)
2. For each haystack session: `run_add(session_text, graph, timestamp=session_date)` then `run_theme_update(graph)`
3. `run_query(question, graph, query_time=question_date)` — query at the benchmark's fixed timestamp
4. LLM-as-judge evaluator scores the hypothesis against ground truth
5. Run-level evaluator computes aggregate accuracy metrics

The `longmemeval` graph is isolated from your main Weavy graph (`weavy`). It is wiped clean before each instance so sessions from one question never bleed into another.

---

## Commands

### `upload` — push LongMemEval data to Langfuse

```bash
uv run eval/eval.py upload --dataset oracle
uv run eval/eval.py upload --dataset s
uv run eval/eval.py upload --dataset m
```

Creates a Langfuse dataset named `longmemeval/oracle` (or `/s`, `/m`) and uploads all 500 instances as dataset items. Each item contains:

- **input**: `question_id`, `question`, `question_date`, `haystack_sessions`, `haystack_dates`
- **expected_output**: `answer`, `question_type`, `abstention`
- **metadata**: `question_type`, `num_sessions`

This is a one-time setup step per dataset variant. Re-running upserts items by stable ID (`{variant}:{question_id}`).

---

### `run` — execute experiment (ingest + query + judge, all in one)

```bash
uv run eval/eval.py run --dataset oracle
uv run eval/eval.py run --dataset oracle --limit 10
uv run eval/eval.py run --dataset oracle --judge-model gpt-4o
uv run eval/eval.py run --dataset oracle --concurrency 4
```

Runs eval items with configurable parallelism. Each worker gets its own isolated FalkorDB graph (`longmemeval:0`, `longmemeval:1`, ...) so items never collide. Default is `--concurrency 1` (sequential). For each item:

1. Resets the isolated FalkorDB graph
2. Ingests each haystack session via `run_add`, with `run_theme_update` after each
3. Runs `run_query` with the question
4. Runs the LLM-as-judge and posts `longmemeval/correct` and `longmemeval/{category}` scores to the query trace in Langfuse
5. After all items, prints aggregate metrics (overall, per-category, task-averaged, abstention)

Each run gets a unique name like `weavy-oracle-20260412T140000`. Scores are attached to Langfuse traces for filtering and analysis in the UI.

**Output per instance:**

```
  [q123_temporal] 4 session(s) — reset graph
    ingest [1/4] 2024-01-15 ✓
    ingest [2/4] 2024-03-02 ✓
    ingest [3/4] 2024-06-10 ✓
    ingest [4/4] 2024-09-20 ✓
    themes ✓
    query  ✓  trace=a3f7c1b2e509
    → The user mentioned switching from Python to Go in March 2024…
```

**Comparability note:** Published LongMemEval leaderboard scores use `gpt-4o` as judge. Results with a different judge are not directly comparable to published numbers, but are fully valid for tracking Weavy's own progress across runs. Pick one model and keep it consistent between runs.

---

### `status` — show dataset and experiment runs

```bash
uv run eval/eval.py status --dataset oracle
```

Shows the Langfuse dataset info, item count, and lists all experiment runs with their timestamps. Links to the Langfuse host URL.

---

### `metrics` — print accuracy table from Langfuse scores

```bash
uv run eval/eval.py metrics --dataset oracle
```

Fetches `longmemeval/*` scores from Langfuse and prints the full accuracy breakdown:

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
────────────────────────────────────────────────────────
```

**Task-averaged accuracy** is the primary comparable metric from the paper — it is the mean of per-category accuracies (not the overall count). Use this when comparing to published numbers.

---

### `reset` — delete Langfuse dataset and experiment history

```bash
uv run eval/eval.py reset --dataset oracle
uv run eval/eval.py reset --all
uv run eval/eval.py reset --dataset oracle --force
```

Deletes the Langfuse dataset and all associated experiment runs and scores. After reset, you need to `upload` again before running experiments.

---

## Standard Workflow

```bash
# 1. Place data files
#    eval/data/longmemeval_oracle.json
#    eval/data/longmemeval_s.json     (optional)
#    eval/data/longmemeval_m.json     (optional)

# 2. Upload to Langfuse (one-time per dataset variant)
uv run eval/eval.py upload --dataset oracle

# 3. Run experiment — oracle first
uv run eval/eval.py run --dataset oracle

# 4. Check experiment runs
uv run eval/eval.py status --dataset oracle

# 5. Print metrics table
uv run eval/eval.py metrics --dataset oracle

# 6. Iterate on Weavy, then run again — each run creates a new experiment
uv run eval/eval.py run --dataset oracle
```

For quick iteration while developing, use `--limit` and `--concurrency`:

```bash
uv run eval/eval.py run --dataset oracle --limit 20
uv run eval/eval.py run --dataset oracle --concurrency 4   # 4x faster
uv run eval/eval.py metrics --dataset oracle
```

To compare runs, open the Langfuse Datasets UI → select `longmemeval/oracle` → compare experiment runs side by side.

---

## Using Langfuse for Observability

Every ingestion and query call during an experiment creates a Langfuse trace automatically. Traces are linked to dataset items, and scores are attached by the evaluators.

**In the Langfuse UI:**

- **Datasets page** → `longmemeval/oracle` → **Runs tab** — see all experiment runs with aggregate scores. Click any run to see per-item results. Compare runs side by side.
- **Traces page** — filter by `longmemeval/correct = 0` to see every failing question. Drill into any trace to inspect the full agent reasoning: which tool calls were made, what the search queries looked like, what was retrieved.
- **Scores page** — aggregated pass rate per score name. `longmemeval/correct` shows overall, `longmemeval/temporal-reasoning` shows just that category.
- **Experiment comparison** — each `run` invocation is a distinct experiment run. The Langfuse UI shows score distributions, per-item diffs, and aggregates across runs.

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

| Variable                 | Purpose                                                |
| ------------------------ | ------------------------------------------------------ |
| `GEMINI_MODEL`           | Weavy agent model (default: `gemini/gemini-2.5-flash`) |
| `LANGFUSE_PUBLIC_KEY`    | Required for all commands                              |
| `LANGFUSE_SECRET_KEY`    | Required for all commands                              |
| `LANGFUSE_HOST`          | Langfuse server URL (default: `http://localhost:3100`) |
| `FALKORDB_HOST` / `PORT` | FalkorDB connection                                    |

The judge model (`--judge-model`) is set at the CLI, not via environment variable, so you can switch judge models between runs.

---

## Migration from Legacy Eval

The previous eval harness used local `.state/` JSONL files and separate `judge` / `score` CLI commands. The new harness replaces all of that with Langfuse Datasets + Experiments:

| Old                                                    | New                                             |
| ------------------------------------------------------ | ----------------------------------------------- |
| `run` (ingest + query, save to `.state/results.jsonl`) | `upload` + `run` (experiment with auto-tracing) |
| `judge` (LLM judge → `.state/eval_results.jsonl`)      | Built into `run` as item-level evaluator        |
| `score` (post scores to Langfuse traces)               | Built into `run` as evaluator output            |
| `metrics` (read from local `.state/`)                  | `metrics` (read from Langfuse scores)           |
| `status` (read from local `.state/`)                   | `status` (read from Langfuse dataset runs)      |
| `reset` (delete local `.state/` files)                 | `reset` (delete Langfuse dataset)               |
| Comparing runs by date-range filtering                 | Langfuse experiment comparison UI               |

The new harness calls `run_add` + `run_theme_update` directly (matching `Weavy.add()` behavior) instead of going through the SDK client.
