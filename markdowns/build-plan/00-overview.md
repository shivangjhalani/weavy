# Weavy Build Plan Overview

## Objective

Build the system described in [Memory-v5](/home/shivang/shivang/projs/weavy/markdowns/Memory-v5.md) as a minimal happy-path Python backend that supports:

1. Canonical source storage for transcripts and chat sessions
2. Provenance-backed semantic graph writes in FalkorDB
3. Theme maintenance as an explicit derived workflow, with `weavy update-themes` available as a manual repair/rebuild path
4. Grounded query/chat retrieval with source citations
5. Agent eval infrastructure for measuring memory quality and answer quality

The system should be direct, explicit, and easy to reason about. Avoid silent fallbacks, hidden retries, speculative abstractions, and compatibility layers.

This document now describes the target state after the planned architectural simplification:
- keep FalkorDB
- keep the three workflows
- keep the reusable harness
- remove pass-through wrapper layers where they do not enforce invariants
- centralize workflow side effects in one shared finalizer

## Design Rules

- One Python codebase, one FalkorDB store, one reusable harness
- Synchronous execution only in v1
- Strict Pydantic validation for every tool input and output
- Explicit failures instead of degraded behavior
- Prefer composability over indirection
- Keep invariants at the mutation boundary, not in pass-through wrappers
- Workflow lifecycle must be explicit and shared across ingestion/query/theme
- No API layer in v1; use library modules plus CLI commands
- Rebuildability is a data-boundary guarantee, not an implemented workflow yet
- Eval infrastructure is first-class and should use real harness runs

## Phase Plan

### Phase 1: Repo Skeleton and Contracts

Create the core package layout and typed contracts.

Deliverables:
- `weavy/config.py`
- `weavy/models/`
- `weavy/store/`
- `weavy/harness/`
- `weavy/modes/`
- `weavy/cli.py`
- `weavy/evals/`

Success criteria:
- Project has a clear module boundary for config, store, harness, and evals
- All tool contracts are encoded as Pydantic models
- `System` node initialization is implemented and testable

### Phase 2: Canonical Sources

Implement transcript and chat session persistence before agentic graph writes.

Deliverables:
- Transcript create/list/get-span flow
- Chat session create/list/get-slice flow
- Canonical file-path conventions for audio and transcript artifacts

Success criteria:
- A transcript or chat session can be stored and retrieved deterministically
- Transcript and chat references can be cited later by exact span

### Phase 3: Semantic Graph CRUD and Logs

Implement the graph write layer with strict provenance and append-only node logs.

Deliverables:
- Node CRUD
- Edge CRUD
- Provenance validation by mode
- Summary-archive behavior on `update_node`

Success criteria:
- Every node write produces a valid log entry
- Invalid provenance causes the write to fail
- No hidden upserts or silent graph corrections exist

### Phase 4: Reusable Agent Harness

Build one loop engine used by ingestion, query, and theme modes.

Deliverables:
- Mode configuration
- Static action surface
- Run trace capture
- Completion handling
- Touched node/edge tracking

Success criteria:
- Ingestion, theme, and query all run through the same core loop
- Runs terminate only through their explicit completion tools
- Failures are visible in traces and not masked

### Phase 5: Ingestion Flow

Implement transcript-first ingestion as the first end-to-end system slice.

Deliverables:
- Ingestion runner
- Transcript read path
- Graph update path
- Shared post-run finalization
- Optional synchronous embedding update if implemented in the same phase

Success criteria:
- One transcript can create/update graph state and then update themes
- Result can be inspected through CLI/debug tooling

### Phase 6: Theme Layer

Implement the delta-driven theme map as a lightweight orientation layer.

Deliverables:
- Theme persistence
- Anchor edge management
- Hot-theme rendering
- Targeted theme updates

Success criteria:
- Theme updates happen from deltas, not full-graph sweeps
- Hot-theme rendering respects token budgets and priority order
- Query and ingestion remain correct even if themes are stale or absent

### Phase 7: Query and Chat

Add retrieval, source grounding, and chat-driven graph mutation.

Deliverables:
- Progressive disclosure read tools
- Query runner
- `deliver_response`
- Chat-driven semantic writes with `ChatSession` provenance

Success criteria:
- Answers cite transcripts or chats, not only graph summaries
- Query runs can mutate memory when the user adds or corrects context

### Phase 8: Eval Infrastructure

Build an agent-focused eval system using real harness runs and trace inspection.

Deliverables:
- Scenario format
- Eval runner
- Deterministic checks
- LLM judge scoring
- Regression reports

Success criteria:
- Prompt/model/tool changes can be compared against a stable suite
- Memory quality and answer quality are both measurable

### Phase 9: Architectural Simplification

Refactor the implementation toward a thinner service-oriented shape without changing the product boundary.

Deliverables:
- Shared workflow finalizer
- Consolidated memory service for graph mutation and retrieval
- Removal of pass-through wrapper layers that do not enforce invariants
- Explicit transcript run-state model
- Narrowed `System` responsibilities

Success criteria:
- The hot path is easier to trace end-to-end
- Ingestion and query cannot drift on lifecycle behavior
- Provenance and touched-entity tracking live next to the write path
- Docs, tests, and code agree on the workflow semantics

## Suggested Repo Shape

```text
weavy/
  config.py
  cli.py
  models/
    canonical.py
    graph.py
    themes.py
    tools.py
    traces.py
  store/
    client.py
    canonical.py
    graph.py
    themes.py
    system.py
  services/
    memory.py
    workflow.py
  harness/
    runner.py
    actions.py
    tracing.py
  modes/
    ingestion.py
    query.py
    theme.py
  evals/
    scenarios.py
    runner.py
    judges.py
    reports.py
tests/
```

## Milestones

### Milestone 1

Transcript in, graph updated, themes updated, run trace stored.

### Milestone 2

Query retrieves memory state and cites transcript spans.

### Milestone 3

Chat session updates graph state and themes correctly.

### Milestone 4

Eval suite can compare harness behavior across runs.

### Milestone 5

Architecture is simplified without changing the product surface or the FalkorDB-backed data model.
