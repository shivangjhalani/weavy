---
phase: 07-agent-tool-capability-gaps-enrich-node-search-results-add-node-relations-and-log-inspection-tools
plan: 02
subsystem: agent
tags: [falkordb, tools, vector-search, graph-traversal, agent-tools]

# Dependency graph
requires:
  - phase: 07-agent-tool-capability-gaps-enrich-node-search-results-add-node-relations-and-log-inspection-tools
    plan: 01
    provides: "vector_search 5-tuples, get_node_edges, get_edge, vector_search_edges in graph.py"
provides:
  - "search_nodes_by_embedding enriched with name+aliases per D-01"
  - "get_node agent tool — reads full node state with embedding stripped, log/refs parsed per D-03/D-04"
  - "get_node_edges agent tool — returns all connected edges with direction field per D-05"
  - "search_edges_by_embedding agent tool — semantic KNN over edge summaries per D-06"
  - "get_edge agent tool — full edge state with parsed log/refs per D-07"
  - "build_tools factory returns 13 tools and 13 declarations (up from 9)"
affects: [agent-harness, ingestion-agent, phase-03-query-agent]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Inspector tools follow symmetric design: get_node/get_edge both strip internal storage artifacts (embedding) and parse JSON-string fields (log, refs) before returning to agent"
    - "Tool closures reference graph_module functions added in same phase — Plan 01 graph layer, Plan 02 agent tool layer"
    - "import json as _json inside closure to avoid any potential shadowing of module-level imports"

key-files:
  created: []
  modified:
    - lifeos/agent/tools.py

key-decisions:
  - "search_nodes_by_embedding now unpacks 5-tuples from vector_search — name and aliases exposed per D-01; breaking change handled transparently since graph.py changed in Plan 01"
  - "get_node tool strips embedding field before returning to agent — embedding is an internal FalkorDB artifact, meaningless to LLM per D-04"
  - "get_edge tool returns raw output from graph_module.get_edge — graph layer already parses log/refs so tool is a thin pass-through with None guard per D-07"
  - "Tools ordering in tools_dict: search_nodes_by_alias, search_nodes_by_embedding, get_node, search_edges_by_embedding, create_node, update_node, delete_node, get_node_edges, create_edge, update_edge, delete_edge, get_edge, create_episode_spans"

patterns-established:
  - "Read-only inspector tools (get_node, get_edge, get_node_edges) follow same closure-over-graph pattern as write tools"
  - "All tool closures return plain dicts — no Pydantic model objects exposed to agent"

requirements-completed: [TOOL-01, TOOL-02, TOOL-03, TOOL-04, TOOL-05]

# Metrics
duration: 3min
completed: 2026-03-27
---

# Phase 07 Plan 02: Agent Tool Capability Gaps (Tool Layer) Summary

**5 new/enriched agent tools closing ingestion blindspots: node/edge inspection, bidirectional edge traversal, and semantic edge search — build_tools now returns 13 tools**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-27T18:32:33Z
- **Completed:** 2026-03-27T18:35:43Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- `search_nodes_by_embedding` enriched to return name and aliases per match — agent can now identify nodes by name from vector search results
- Four new tools added: `get_node`, `get_node_edges`, `get_edge`, `search_edges_by_embedding` — agent can inspect full state before writing, traverse relationships, and search edges semantically
- `build_tools` factory upgraded from 9 to 13 tools with matching OpenAI-format declarations — all verified with mock patches

## Task Commits

Each task was committed atomically:

1. **Task 1: Enrich search_nodes_by_embedding and add get_node tool** - `3fcbc46` (feat)
2. **Task 2: Add get_node_edges, get_edge, search_edges_by_embedding tools and update counts** - `95efdb0` (feat)

**Plan metadata:** (docs commit — this summary)

## Files Created/Modified

- `lifeos/agent/tools.py` - 5 tool changes: search_nodes_by_embedding enriched, 4 new closures added, tools_dict and declarations updated, docstrings updated 9→13

## Decisions Made

- `import json as _json` placed inside `get_node` closure to avoid any shadowing of potential module-level json imports — cleaner than a top-level import given json is not currently imported at module scope
- `get_edge` tool is a thin pass-through to `graph_module.get_edge` because the graph layer already handles log/refs JSON parsing — only a None guard needed
- Tool ordering in `tools_dict` groups inspection tools near their related write tools: `get_node` near `search_nodes_by_embedding`, `get_node_edges` near `delete_node`/`create_edge`, `get_edge` near `delete_edge`

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All 13 tools registered and verified with mock patches
- Plan 03 (harness.py wiring) can now proceed — build_tools returns 13 tools + declarations, agent prompt can reference the new inspection tools
- Ruff passes with no lint errors

---
*Phase: 07-agent-tool-capability-gaps-enrich-node-search-results-add-node-relations-and-log-inspection-tools*
*Completed: 2026-03-27*
