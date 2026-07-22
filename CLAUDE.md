- FalkorDB: sessions, semantic graph, themes, system counters
- LiteLLM: all model calls — completions and embeddings (configured via `LLM_MODEL` / `EMBEDDING_MODEL`)
- Langfuse: run traces and eval visibility

## Commands

```bash
docker compose --profile falkordb up -d   # start FalkorDB
docker compose --profile langfuse up -d   # start Langfuse (optional)
docker compose --profile falkordb --profile langfuse up -d  # start both

uv run pytest                        # all tests
uv run pytest tests/test_graph.py    # single file
uv run pytest -k "test_create_node"  # single test by name
uv run ruff check .
uv run ruff format .
```

Tests auto-mock `RunTracer` (Langfuse) and `fetch_prompt` (prompt files) — no real services needed.

### CLI

```bash
uv run python -m weavy.cli init-system
uv run python -m weavy.cli status
uv run python -m weavy.cli list-sessions [--limit N]
uv run python -m weavy.cli add <file_or_-> [--context "..."] [--timestamp ISO]
uv run python -m weavy.cli continue <session_id> <question>
uv run python -m weavy.cli update-themes
uv run python -m weavy.cli query [question]                 # omit question for REPL
```

## Architecture

### Core Contract

The memory layer is source-agnostic. `Weavy` in `weavy/client.py` is the public SDK:

```python
import weavy

w = weavy.Weavy()                                      # or Weavy("my_graph")
trace = w.add(text, timestamp=..., context=...)        # -> RunTrace
trace = w.query(question, context=..., query_time=...) # -> RunTrace
trace = w.continue_session(session_id, message)        # -> RunTrace
trace = w.update_themes()                              # -> RunTrace
w.reset()                                              # drop + reinit (benchmarks)
```

`application/` is the direct programmatic interface for internal callers that need
fine-grained control (pass explicit `graph: Graph`):

```python
from weavy.application.session_runs import run_add, run_query, run_session
from weavy.application.theme_runs import run_theme_update
from weavy.store.client import get_graph

graph = get_graph()           # or get_graph("my_graph") for isolation
run_add(text, graph, timestamp?, context?)           # -> RunTrace
run_query(question, graph, context?, query_time?)    # -> RunTrace
run_session(session_id, mode, graph, message?)       # -> RunTrace
run_theme_update(graph)                              # -> RunTrace
```

### Key Design Decisions

- **Session is state, mode is behavior.** A `Session` is just a message history — no mode attached. Mode (`ingestion`/`query`) selects system prompt and tool set at call time. Any session can be continued in any mode.
- **Themes are automatic at the SDK boundary.** `Weavy.add()` in `client.py` runs `run_theme_update` after every successful ingestion — the caller never manages it. `application/run_add` does not; internal callers (eval, CLI) own theme timing explicitly.
- **Source-agnostic ingestion.** The ingestion prompt has no source-specific framing. The agent reads the text and determines what it is. Optional `caller_context` (e.g., "These are chat logs") is injected into the `{{caller_context}}` prompt slot to steer interpretation.
- **Single harness, three modes.** `run()` in `harness/runner.py` is the one agent loop — LiteLLM completion + tool dispatch. Terminates on `is_completion=True`. Shared by ingestion, query, and theme.
- **Graph mutations tracked.** All writes flow through `services/memory.py` which enforces provenance and appends to `trace.touched_nodes`/`trace.touched_edges`.
- **IDs are system-minted.** `store/system.py:increment_counter` produces `s:N`, `node:N`, `edge:N`. The `System` singleton tracks counters.
- **Navigational graph memory (Model B).** The semantic graph (nodes + edges) is the *sole* search surface — `search_graph` returns only `kind="node"`/`kind="edge"`. Episodes are ground truth but are never independently searchable; they are reached only by navigation: `search_graph` → `get_node`'s `mentioned_by` (or an edge's `source_id`) → `get_session`. There is no RAG safety net — retrieval quality equals index quality, by design (see `openspec/changes/navigational-graph-memory`).
- **One node per entity is a storage invariant.** `create_node` refuses writes that collide with an existing entity (alias match, or embedding within `DUPLICATE_DISTANCE`) and names the candidates; `force=true` overrides for genuinely distinct same-name entities. Identity lives in aliases — embedding similarity only catches near-certain rephrasings.
- **A node carries exactly one embedding.** `embedding` is computed from aliases + current summary only — no log-note history folded in, no separate `identity_embedding`. Since past facts are recovered by navigating to episodes rather than by embedding note history, the same vector serves both search and `DUPLICATE_DISTANCE` dedup.
- **Domain refusals are results, not exceptions.** Tools return `ok=false` with a corrective message for agent-fixable conditions (duplicate node, missing edge endpoint); exceptions are reserved for system faults and count toward the run's error budget.

### Module Map

```
weavy/
  __init__.py        — exports Weavy and RunTrace
  client.py          — Weavy: graph resolution, init_system, method delegation
  config.py          — Settings from env (FALKORDB_*, LLM_MODEL, EMBEDDING_MODEL, LANGFUSE_*)
  cli.py             — argparse entry point; thin command handlers + REPL
  langfuse_client.py — lazy optional Langfuse client factory
  application/
    contracts.py     — app-level result DTOs shared across store/services/harness
    prompts.py       — prompt loading and theme-context rendering
    session_runs.py  — session creation, run orchestration, run finalization
    theme_runs.py    — theme-update orchestration and finalization
  models/
    canonical.py     — Session, ChatMessage, conversation_to_chat_messages
    graph.py         — SemanticNode, SemanticEdge, ProvenanceInput
    themes.py        — Theme
    traces.py        — RunTrace, Turn, TurnUsage, TouchedNode/Edge
  store/             — FalkorDB reads/writes (canonical, graph, themes, system)
    client.py        — FalkorDB client / graph access
  services/
    memory.py        — graph CRUD + provenance enforcement + touched-node tracking
    embedding.py     — embedding generation for semantic nodes (single vector: aliases + summary)
  harness/
    runner.py        — single agentic loop (LiteLLM completion + tool dispatch)
    actions.py       — ACTIONS registry; SESSION_ACTIONS / THEME_ACTIONS lists
    tracing.py       — Langfuse span wrapping (RunTracer, ChatSessionTracer)
    tool_models.py   — agent-only tool input contracts and completion schemas
  prompts/           — weavy-ingestion.md, weavy-query.md, weavy-theme.md
```

### Boundary Rules

- **`client.py` is the public SDK interface.** Wraps `application/` with graph
  resolution and `init_system`. No direct `store/` calls except `get_graph` and
  `init_system`. External library users import `Weavy` from here.
- **`cli.py` is the operational interface.** It imports from `application/`
  directly for full trace visibility and human-readable output.
- **`application/` owns orchestration and prompt assembly.** Session/theme run
  setup, prompt rendering, and run finalization live there. All `run_*`
  functions require an explicit `graph: Graph` argument — callers resolve the
  graph via `get_graph()` and pass it in.
- **Agent tool contracts belong only to the harness boundary.** Tool schemas live
  in `weavy/harness/tool_models.py` and are not the general application
  contract for `store/` or non-harness `services/`.
- **`store/` means persistence.** FalkorDB reads/writes stay there; prompt
  formatting and token-budget shaping do not.
- **Docs must match code.** When module boundaries change, update this file in
  the same refactor.

## Design Rules

- Sync-only execution
- Strict Pydantic validation on every tool input/output — invalid args fail immediately
- Provenance required on every semantic node write
- No silent fallbacks or hidden retries
- `Weavy` in `client.py` is the SDK entry point — self-bootstrapping, returns RunTrace
- `Weavy(graph_name)` provides graph-level isolation for benchmark scenarios
- Input boundary is text — pre-processing is the caller's responsibility
- Sessions are source-agnostic — no origin, audio_path, or segment fields in `store/canonical.py`
- Agent tool schemas are a harness concern — they should not be shared as the
  general application contract for `store/` and non-harness services
- `RunTrace` is the standard return type from all agent runs — no hiding
- Environment managed by `devenv.nix`; use `uv` for deps, `ruff` for linting
