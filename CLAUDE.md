# CLAUDE.md

This file provides guidance to AI agents when working with code in this repository.

## What This Is

Spoken thought is the primary tool for complex, abstract thought and self-reflection, yet it is, by design, fleeting and highly unstructured.

Challenge: How do you represent and store a human's evolving life in a structure that supports arbitrary, open-ended queries without encoding prior assumptions about how to store and what to store?

Weavy is a CLI-first personal memory layer. It accepts any text, runs an agent to ingest it into a semantic graph in FalkorDB, and answers grounded queries against that graph. Pre-processing (audio transcription, document parsing, chat formatting) is the caller's responsibility — by the time information reaches Weavy, it's text.

- FalkorDB: sessions, semantic graph, themes, system counters
- LiteLLM + Gemini: agent model calls (ingestion, query, theme)
- LiteLLM + Groq Whisper: audio transcription (pre-processing utility)
- Langfuse: run traces and eval visibility

## Commands

```bash
devenv up          # start FalkorDB
devenv shell       # enter dev environment

devenv shell -- uv run pytest                        # all tests
devenv shell -- uv run pytest tests/test_graph.py    # single file
devenv shell -- uv run pytest -k "test_create_node"  # single test by name
devenv shell -- ruff check .
devenv shell -- ruff format .
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

The memory layer is source-agnostic. Three operations:

- **`add(text, timestamp?, context?)`** — create a session, run ingestion, return trace
- **`query(question, context?)`** — create a session, run query agent, return answer
- **`continue(session_id, message)`** — resume any session in any mode

### Key Design Decisions

- **Session is state, mode is behavior.** A `Session` is just a message history — no mode attached. Mode (`ingestion`/`query`) selects system prompt and tool set at call time. Any session can be continued in any mode.
- **Source-agnostic ingestion.** The ingestion prompt has no source-specific framing. The agent reads the text and determines what it is. Optional `caller_context` (e.g., "These are chat logs") is injected into the `{{caller_context}}` prompt slot to steer interpretation.
- **Pre-processing is external.** `transcribe` converts audio to Whisper JSON — it has no dependency on the memory layer. The caller pipes its output to `add` when ready.
- **Single harness, three modes.** `run()` in `harness/runner.py` is the one agent loop — LiteLLM completion + tool dispatch. Terminates on `is_completion=True`. Shared by ingestion, query, and theme.
- **Graph mutations tracked.** All writes flow through `services/memory.py` which enforces provenance and appends to `trace.touched_nodes`/`trace.touched_edges`.
- **IDs are system-minted.** `store/system.py:increment_counter` produces `s:N`, `node:N`, `edge:N`. The `System` singleton tracks counters.

### Module Map

```
transcribe.py          — standalone Whisper transcription script (not part of weavy package)
weavy/
  config.py          — Settings from env (FALKORDB_*, GEMINI_MODEL, LANGFUSE_*)
  cli.py             — argparse entry point; thin command handlers
  models/
    canonical.py     — Session, ChatMessage, conversation_to_chat_messages
    graph.py         — SemanticNode, SemanticEdge, ProvenanceInput
    themes.py        — Theme, ThemeStatus
    tools.py         — Pydantic input/output contracts for every agent tool
    traces.py        — RunTrace, Turn, TurnUsage, TouchedNode/Edge
  store/             — FalkorDB reads/writes (canonical, graph, themes, system)
  services/
    memory.py        — graph CRUD + provenance enforcement + touched-node tracking
    workflow.py      — prompt loading, caller_context injection, run finalization
    embedding.py     — embedding generation for semantic nodes
  harness/
    runner.py        — single agentic loop (LiteLLM completion + tool dispatch)
    actions.py       — ACTIONS registry; SESSION_ACTIONS / THEME_ACTIONS lists
    tracing.py       — Langfuse span wrapping (RunTracer, ChatSessionTracer)
  modes/
    session.py       — run_add(), run_session(), run_ingest(), run_query(), run_chat_repl()
    theme.py         — run_theme_update()
  prompts/           — weavy-ingestion.md, weavy-query.md, weavy-theme.md
```

## Design Rules

- Sync-only execution
- Strict Pydantic validation on every tool input/output — invalid args fail immediately
- Provenance required on every semantic node write
- No silent fallbacks or hidden retries
- `System` node must be initialized before any operations (`init-system`)
- Input boundary is text — pre-processing is the caller's responsibility
- Sessions are source-agnostic — no origin, audio_path, or segment fields in `store/canonical.py`
- Environment managed by `devenv.nix`; use `uv` for deps, `ruff` for linting
