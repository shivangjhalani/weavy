---
phase: 02-ingestion-agent
plan: "01"
subsystem: memory-models-graph
tags: [models, graph, pydantic, falkordb, schema-evolution]
dependency_graph:
  requires: []
  provides:
    - Node model with name field (no type)
    - Edge model with label field (no type)
    - EpisodeSpan model
    - Transcript model
    - graph.py delete_node, delete_edge
    - graph.py search_nodes_by_alias
    - graph.py set_node_log, set_edge_log
    - graph.py update_node/update_edge extended signatures
  affects:
    - 02-02-PLAN.md (agent tools use updated graph functions)
    - 02-03-PLAN.md (ingest.py uses Transcript model)
tech_stack:
  added: []
  patterns:
    - Dynamic Cypher SET clause construction for optional update params
    - Union-merge of aliases list (order-preserving, no duplicates)
    - set_node_log/set_edge_log as separate path from update (no re-embed)
key_files:
  created: []
  modified:
    - lifeos/memory/models.py
    - lifeos/memory/graph.py
    - tests/test_models.py
    - tests/test_graph.py
decisions:
  - "D-01 applied: Node.type removed, Node.name added — LLM names entities freely"
  - "D-01 applied: Edge.type removed, Edge.label added — LLM labels relationships freely"
  - "set_node_log/set_edge_log intentionally do NOT re-embed — compression pass only changes log, summary unchanged"
  - "update_node builds SET clause dynamically so optional params only appear when provided"
metrics:
  duration: "~4 minutes"
  completed: "2026-03-26"
  tasks_completed: 2
  files_modified: 4
---

# Phase 02 Plan 01: Data Model and Graph Layer Update Summary

Dropped the rigid `type` field from Node/Edge Pydantic models and replaced with `name`/`label` (LLM-free strings), added `EpisodeSpan` and `Transcript` models, and extended graph.py with delete operations, alias search, log compression helpers, and richer update signatures.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Update Pydantic models — drop type, add name/label, add Transcript and EpisodeSpan | 7367922 | lifeos/memory/models.py, tests/test_models.py |
| 2 | Update graph.py — remove type references, add delete/alias-search/set-log, extend update signatures | b11c867 | lifeos/memory/graph.py, tests/test_graph.py |

## What Was Built

### models.py

- `Node`: `type` field removed, `name: str` added as second field (canonical display label)
- `Edge`: `type` field removed, `label: str` added as second field (relationship descriptor)
- `EpisodeSpan`: new model with `start_offset`, `end_offset`, `summary`, `embedding=None`
- `Transcript`: new model with `id`, `recorded_at`, `text`, `segments=[]`, `episode_spans=[]`

### graph.py

- `init_graph`: removed `ON (n.type)` index, added `ON (r.label)` edge index
- `create_node`: uses `node.name` directly (no aliases fallback), removed `type` from Cypher
- `create_edge`: `label: $label` replaces `type: $type` in Cypher
- `update_node`: extended with `new_aliases` (union-merge), `new_refs` (append), `new_name`, `recorded_at`; dynamic SET clause
- `update_edge`: extended with `new_refs`, `recorded_at`; reads existing refs before appending
- `delete_node`: `DETACH DELETE` — removes node and all its relationships
- `delete_edge`: `DELETE` on relationship only — nodes intact
- `search_nodes_by_alias`: `$alias IN n.aliases` exact membership check, returns `[{id, name, aliases, summary}]`
- `set_node_log`: replaces log JSON without touching summary or embedding (compression pass)
- `set_edge_log`: same pattern for edges

### tests

- `tests/test_models.py`: 20 tests — all `type=` replaced with `name=`/`label=`; 3 new tests for EpisodeSpan and Transcript
- `tests/test_graph.py`: all Node/Edge constructions updated to use `name=`/`label=`; 5 new integration tests (delete_node, delete_edge, search_nodes_by_alias, set_node_log, update_node_with_new_aliases)

## Verification

```
pytest tests/test_models.py -m "not integration"  → 20 passed
pytest tests/test_graph.py -m "not integration"   → 13 deselected (all integration, need FalkorDB)
grep "type: str" lifeos/memory/models.py          → no matches
grep "\.type" lifeos/memory/graph.py              → no matches
grep "def delete_node\|def delete_edge\|def search_nodes_by_alias\|def set_node_log" graph.py → 4 functions found
```

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all models are fully wired. graph.py functions are complete implementations.

## Self-Check: PASSED

- lifeos/memory/models.py — FOUND
- lifeos/memory/graph.py — FOUND
- tests/test_models.py — FOUND
- tests/test_graph.py — FOUND
- Commit 7367922 — FOUND (feat(02-01): update Pydantic models)
- Commit b11c867 — FOUND (feat(02-01): update graph.py)
