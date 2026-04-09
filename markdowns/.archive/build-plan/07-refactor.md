# Architecture Simplification Plan

## Goal

Make Weavy easier to read, debug, and evolve without changing its external product shape.

Keep:
- FalkorDB
- the CLI
- canonical transcripts and chats
- the derived semantic graph
- the three workflows: ingestion, query, theme

Reduce:
- pass-through abstractions
- duplicated lifecycle logic
- hidden workflow state

## Target Shape

The target runtime path should be:

```text
mode -> harness -> static action map -> memory service -> FalkorDB
                                      -> workflow finalizer
```

Not:

```text
mode -> harness -> registry -> tool wrapper -> store wrapper -> store
```

## Principles

- Preserve behavior before expanding flexibility
- Put invariants next to the writes that enforce them
- Keep workflow side effects in one place
- Treat themes as auxiliary orientation state, not correctness-critical state
- Prefer deletion of layers over adding smarter adapters

## Planned Changes

### 1. Introduce a Shared Workflow Finalizer

Create one shared finalization path for all workflows.

It should own:
- run completion status
- canonical persistence derived from the run
- touched-node and touched-edge interpretation
- transcript run-state transitions
- conditional theme updates
- failure cleanup

Effect:
- ingestion and query stop drifting on post-run behavior
- lifecycle bugs become structural, not incidental

### 2. Consolidate Graph Mutation Behind One Memory Service

Move provenance validation, id minting, embedding refresh, and touched-entity tracking into one service layer around semantic graph writes.

Effect:
- one write path to inspect
- fewer places where graph invariants can diverge
- less need for wrapper modules that only forward calls

### 3. Consolidate Read Operations Behind the Same Service Boundary

Keep the agent-facing read surface static, but route reads through one coherent service module instead of multiple thin wrappers.

Effect:
- clearer boundary between agent interface and persistence
- easier testing of domain behavior without harness setup

### 4. Narrow the `System` Node

Keep counters and theme-specific graph state in `System`, but move runtime policy back to config unless the value must be stored in FalkorDB.

Effect:
- less hidden global mutable state
- clearer distinction between store state and runtime configuration

### 5. Replace `ingestion_status` With an Explicit Run State

Move transcript ingestion tracking from an ambiguous `0/1` flag to an explicit lifecycle:

```text
pending | running | completed | failed
```

Effect:
- easier debugging
- better recovery semantics
- less accidental conflation of "already ingested" and "currently running"

### 6. Keep Themes, But Demote Them Architecturally

Themes remain persisted in FalkorDB and updated synchronously after graph-mutating runs, but they are auxiliary.

Rules:
- a stale or missing theme map must not make ingestion or query incorrect
- manual `update-themes` remains available as a repair/rebuild path

Effect:
- fewer correctness assumptions tied to the theme subsystem
- cleaner failure boundaries

### 7. Remove Dead Wrapper Layers Last

Only remove or merge files such as thin tool wrappers after the new service/finalizer path is in place and covered by tests.

Effect:
- low migration risk
- easier diffs and rollback during the refactor

## Rollout Order

1. Add the shared workflow finalizer and route query + ingestion through it.
2. Add explicit transcript run-state handling.
3. Move graph write invariants into one memory service.
4. Move read operations behind the same service boundary.
5. Shrink or remove pass-through wrappers and registry-only metadata that no longer adds value.
6. Update tests to assert workflow invariants through the finalizer.
7. Remove stale docs and dead code paths.

## Non-Goals

- Replace FalkorDB
- Rebuild the product around a web API
- Remove themes entirely
- Change the canonical-vs-derived data model
- Introduce async workers or queues

## Success Criteria

- A new engineer can trace ingestion or query end-to-end in a small number of files
- Lifecycle behavior is identical across workflows unless intentionally different
- Graph invariants are enforced in one place
- Theme maintenance is explicit and non-magical
- The docs describe the same architecture the code is moving toward
