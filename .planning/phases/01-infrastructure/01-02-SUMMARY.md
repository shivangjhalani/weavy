---
phase: 01-infrastructure
plan: 02
subsystem: memory
tags: [python, falkordb, pydantic, gemini, vector-search, tdd, pytest]

requires:
  - 01-01  # lifeos package, models, embeddings

provides:
  - lifeos/memory/graph.py with init_graph, create_node, update_node, create_edge, update_edge, vector_search, get_node
  - FalkorDB initialized with 4 range indexes + 1 vector index
  - Atomic embedding guarantee: every node/edge mutation re-embeds (GRPH-05)
  - Vector KNN search over node summaries via db.idx.vector.queryNodes
  - 8 integration tests covering all graph operations

affects: [03-harness]

tech-stack:
  added:
    - ruff (dev dep — confirmed installed via uv add --dev)
    - pytest>=9.0.2 (dev dep — confirmed installed via uv add --dev)
  patterns:
    - REMOVE + SET pattern for updating FalkorDB vecf32 vector properties
    - JSON-serialized log/refs stored as string properties (FalkorDB primitive constraint)
    - init_graph() idempotent via try/except on CREATE INDEX calls
    - Module-scoped pytest fixtures with unique graph names (test_lifeos_{uuid})

key-files:
  created:
    - lifeos/memory/graph.py
    - tests/test_graph.py
  modified:
    - pyproject.toml

key-decisions:
  - "FalkorDB vecf32 vector property update requires REMOVE before SET — direct SET n.embedding = vecf32($e) silently keeps the old value"
  - "Log and refs stored as JSON strings in FalkorDB (not nested objects) — FalkorDB properties must be primitives or arrays of primitives"
  - "get_node() reads node via RETURN n and extracts node.properties — vecf32 values return as list[float] from FalkorDB Python client"
  - "Integration markers used for all tests requiring live FalkorDB — pytest.ini markers configured in pyproject.toml"

requirements-completed: [INFR-03, GRPH-01, GRPH-05]

duration: 4min
completed: 2026-03-25
---

# Phase 01 Plan 02: FalkorDB Graph Module Summary

**FalkorDB graph layer with 4 range indexes + cosine vector index, atomic CRUD with re-embedding on every mutation, and KNN vector search — GRPH-05 enforced by design**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-03-25T18:14:03Z
- **Completed:** 2026-03-25T18:18:00Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 3

## Accomplishments

- Created `lifeos/memory/graph.py` with all required exports: `init_graph`, `create_node`, `update_node`, `create_edge`, `update_edge`, `vector_search`, `get_node`
- `init_graph()` creates 4 range indexes (name, type, transcript_id, aliases) and 1 vector index (embedding, 3072d, cosine) — each wrapped in try/except for idempotency
- `create_node()` and `create_edge()` call `embed_text()` before storing — embedding is atomic with creation
- `update_node()` and `update_edge()` call `embed_text()` before updating — GRPH-05 satisfied by design; no separate embedding update path exists
- `vector_search()` calls `embed_query()` and uses `db.idx.vector.queryNodes` — returns `list[tuple[str, str, float]]`
- Log and refs serialized as JSON strings (FalkorDB property constraint)
- 8 integration tests covering init, idempotency, create/get node, update re-embed, vector search discovery, create edge, update edge re-embed, return format
- All 8 tests pass against live FalkorDB

## Task Commits

1. **TDD RED — test(01-02):** `e314da2` — failing integration tests + pyproject.toml markers
2. **TDD GREEN — feat(01-02):** `ae65ec6` — graph.py implementation, all tests passing

## Files Created/Modified

- `lifeos/memory/graph.py` — FalkorDB init, atomic CRUD, vector search (new)
- `tests/test_graph.py` — 8 integration tests for all graph operations (new)
- `pyproject.toml` — added integration pytest marker, pytest/ruff as dev deps

## Decisions Made

- **REMOVE before SET for vecf32:** FalkorDB 1.6.0 does not update a vector property with a direct `SET n.embedding = vecf32($e)` on an existing node — the old value is silently retained. Workaround: `MATCH (n:Node {id: $id}) REMOVE n.embedding` then `SET n.embedding = vecf32($e)` in a second query. Confirmed empirically.
- **JSON strings for nested structures:** FalkorDB properties are primitives or arrays of primitives. `log` (list of LogEntry) and `refs` (list of TranscriptRef) are serialized with `json.dumps(...)` before storage and must be deserialized on read.
- **Integration test scope:** All tests marked `@pytest.mark.integration` — require live FalkorDB and GEMINI_API_KEY. Module-scoped graph fixture uses unique name `test_lifeos_{uuid.hex[:8]}` and cleans up with `DETACH DELETE`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] FalkorDB vecf32 update requires REMOVE+SET pattern**
- **Found during:** Task 1 (GREEN phase — test_update_node_reembeds failing)
- **Issue:** `SET n.embedding = vecf32($embedding)` silently keeps the old vector value when updating an existing node; the update does not take effect
- **Fix:** Added `MATCH (n:Node {id: $id}) REMOVE n.embedding` before the SET in `update_node()` and `update_edge()`
- **Files modified:** `lifeos/memory/graph.py`
- **Commit:** `ae65ec6`

## Known Stubs

None — all graph operations are fully implemented and wired.

## Next Phase Readiness

- Plan 03 (agent harness) can import `lifeos.memory.graph` and use all 6 exported functions
- Vector search is functional — agents can use `vector_search(graph, query_text)` immediately
- Index creation is idempotent — `init_graph()` is safe to call at application startup in scripts

## Self-Check: PASSED

- `lifeos/memory/graph.py` — present and importable
- `tests/test_graph.py` — 8 integration tests present
- Commits `e314da2` (RED) and `ae65ec6` (GREEN) in git history
- All 8 tests passing against live FalkorDB

---
*Phase: 01-infrastructure*
*Completed: 2026-03-25*
