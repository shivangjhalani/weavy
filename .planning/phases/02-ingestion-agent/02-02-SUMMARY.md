---
phase: 02-ingestion-agent
plan: 02
subsystem: agent
tags: [gemini, falkordb, tools, function-calling, tdd, embeddings]

requires:
  - phase: 02-ingestion-agent
    plan: 01
    provides: "Updated Node/Edge models (name/label), extended graph.py signatures"

provides:
  - "AgentHarness without budget enforcement — loops until model stops calling tools"
  - "build_tools factory returning 9 tool callables and 9 FunctionDeclarations"
  - "9 ingestion agent tools: search_nodes_by_alias, search_nodes_by_embedding, create_node, update_node, delete_node, create_edge, update_edge, delete_edge, create_episode_spans"

affects:
  - 02-03-ingestion-prompt
  - 02-04-ingest-pipeline
  - 02-05-log-compression

tech-stack:
  added: []
  patterns:
    - "build_tools factory pattern: closures over graph/store, returns (tools_dict, declarations_list)"
    - "types.Schema for FunctionDeclarations (google-genai 1.68.0 — not dict format)"
    - "recording_timestamp param threads through build_tools to LogEntry.recorded_at"
    - "patch('lifeos.agent.tools.embed_text') for unit testing tools that call embed_text"

key-files:
  created:
    - lifeos/agent/tools.py
  modified:
    - lifeos/agent/harness.py
    - tests/test_harness.py
    - tests/test_tools.py

key-decisions:
  - "D-08 applied: removed budget param and calls_used counter from AgentHarness entirely — loop runs while True until no fc_parts"
  - "build_tools uses closures (not class) so graph/store/recording_timestamp are captured by value at call time"
  - "embed_text imported at module level in tools.py — patch as 'lifeos.agent.tools.embed_text' in tests, not 'lifeos.core.embeddings.embed_text'"
  - "update_node passes new_refs=None (not empty list) when no transcript coords provided — preserves existing refs"

patterns-established:
  - "Pattern 1 (tools factory): build_tools(graph, store, recording_timestamp) -> (dict, list) — all tools as closures"
  - "Pattern 2 (FunctionDeclaration): types.FunctionDeclaration(name, description, parameters=types.Schema(type=OBJECT, properties={...}, required=[...]))"
  - "Pattern 3 (patch location): always patch where the name is used, not where it is defined"

requirements-completed: [INGST-01, INGST-02, INGST-04]

duration: 4min
completed: 2026-03-26
---

# Phase 02 Plan 02: Agent Harness + 9 Ingestion Tools Summary

**Budget-free AgentHarness and build_tools factory with 9 graph manipulation tools using types.Schema FunctionDeclarations for google-genai 1.68.0**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-26T05:49:43Z
- **Completed:** 2026-03-26T05:53:43Z
- **Tasks:** 2 (+ 1 TDD RED commit)
- **Files modified:** 4

## Accomplishments

- Removed budget enforcement entirely from AgentHarness — loop runs until model emits no function calls
- Implemented build_tools factory returning 9 closures and 9 FunctionDeclarations
- All 9 tools verified: search (2), node CRUD (3), edge CRUD (3), create_episode_spans (1)
- TDD: 17 unit tests, all passing, with mocked graph and store

## Task Commits

Each task was committed atomically:

1. **Task 1: Remove budget enforcement from AgentHarness** - `6582bdc` (feat)
2. **Task 2 RED: Failing tests for build_tools** - `39cd798` (test)
3. **Task 2 GREEN: Implement build_tools factory** - `c164d98` (feat)

## Files Created/Modified

- `lifeos/agent/tools.py` - build_tools factory with 9 tool closures and 9 FunctionDeclarations
- `lifeos/agent/harness.py` - Budget enforcement removed; clean while-True dispatch loop
- `tests/test_harness.py` - Budget tests replaced with test_harness_runs_until_model_stops
- `tests/test_tools.py` - 17 unit tests for all 9 tools and factory counts

## Decisions Made

- Closures capture graph/store at build_tools call time — no class, no self
- recording_timestamp defaults to `datetime.now(timezone.utc)` inside each tool call if None
- `patch('lifeos.agent.tools.embed_text')` is the correct patch location (not the source module) — discovered during GREEN phase when embed_text mock wasn't being called

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test patch target for embed_text**
- **Found during:** Task 2 GREEN (test_create_episode_spans_embeds_summaries)
- **Issue:** Test patched `lifeos.core.embeddings.embed_text` but tools.py imports `embed_text` directly — the closure captured the original reference
- **Fix:** Changed patch target to `lifeos.agent.tools.embed_text` in both episode span tests
- **Files modified:** tests/test_tools.py
- **Verification:** All 17 tests pass
- **Committed in:** c164d98 (Task 2 feat commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — test patch location bug)
**Impact on plan:** Correctness fix — test was passing vacuously (mock not called). No scope creep.

## Issues Encountered

None — all implementation followed the plan specification.

## Known Stubs

None — all 9 tools are fully implemented and tested.

## Next Phase Readiness

- AgentHarness (no budget) + build_tools factory are ready for Plan 03 (ingestion prompt)
- tools_dict and declarations can be directly passed to AgentHarness in ingest.py
- recording_timestamp param ready to receive audio file mtime in Plan 04

---
*Phase: 02-ingestion-agent*
*Completed: 2026-03-26*
