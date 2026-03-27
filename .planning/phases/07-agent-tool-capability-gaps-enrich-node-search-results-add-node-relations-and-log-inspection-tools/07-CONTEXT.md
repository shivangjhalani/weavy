# Phase 7: Agent Tool Capability Gaps - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Close gaps in the ingestion agent's tool set exposed by running actual ingestion:
- Enrich what node search tools return (agent currently can't see node names from embedding search)
- Expose node inspection as an agent tool (agent can't read full node state before updating)
- Add graph traversal tools (agent can't see a node's existing edges before creating new ones)
- Add edge inspection tool (agent can't read edge state or log before updating)

No query agent work, no theme layer, no evaluation — pure ingestion agent tool improvements.

</domain>

<decisions>
## Implementation Decisions

### Search Result Enrichment
- **D-01:** `search_nodes_by_embedding` response enriched — each match now returns `{node_id, name, aliases, summary, score}`. Previously only returned `{node_id, summary, score}`, leaving the agent unable to identify what it found by name.
- **D-02:** `search_nodes_by_alias` response kept as-is — `{id, name, aliases, summary}` is sufficient for disambiguation. No refs or log needed in search results.

### Node Inspection Tool (new)
- **D-03:** Expose `get_node(node_id)` as a new agent tool. Agent needs to read full node state before deciding to update — current tools only support write operations against a node ID.
- **D-04:** `get_node` returns: `{name, aliases, summary, refs, log, created_at, updated_at}`. Embedding vector is excluded — it is an internal FalkorDB artifact with no meaning to the LLM. Log entries are returned as parsed `{recorded_at, note}` objects, not raw JSON strings.

### Node Relations Tools (new)
- **D-05:** `get_node_edges(node_id)` — single bidirectional tool returning all edges connected to a node (both outgoing and incoming). Per edge: `{edge_id, label, summary, source: {id, name}, target: {id, name}, direction}`. Direction is `"outgoing"` or `"incoming"` from the perspective of the queried node. Does NOT include per-edge refs or log (those come from `get_edge`).
- **D-06:** `search_edges_by_embedding(query, k)` — semantic search over edge summaries, same pattern as `search_nodes_by_embedding`. Needed for edge discovery without a node ID anchor. Researcher must verify whether FalkorDB supports a vector index on edge properties; if not, implementation falls back to full-scan cosine comparison.

### Edge Inspection Tool (new)
- **D-07:** `get_edge(edge_id)` — symmetric counterpart to `get_node`. Returns: `{edge_id, label, summary, source_id, target_id, refs, log, created_at, updated_at}`. Log entries returned as parsed `{recorded_at, note}` objects. Agent currently has `update_edge` and `delete_edge` but no way to read edge state first.

### Log Format
- **D-08:** All log fields returned by `get_node` and `get_edge` are parsed into a Python list of `{recorded_at, note}` dicts — not raw JSON strings as stored in FalkorDB. This applies consistently across both tools.

### Claude's Discretion
- Whether `search_edges_by_embedding` uses a FalkorDB vector index on edges (requires `init_graph` to add edge vector index) or falls back to full-scan cosine computation — researcher should confirm FalkorDB edge vector index support and recommend approach
- Exact parameter name for `get_node` tool: `node_id` (consistent with existing tools)
- Test coverage design for new tools

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing Tool Layer (being modified/extended)
- `lifeos/agent/tools.py` — Current 9-tool `build_tools` factory. New tools are added here as closures; D-01 is a change to the existing `search_nodes_by_embedding` closure.
- `lifeos/memory/graph.py` — FalkorDB query layer. New graph functions needed: `get_node_edges`, `get_edge`, `vector_search_edges`. `get_node` already exists and can be reused.

### Data Models
- `lifeos/memory/models.py` — `Node`, `Edge`, `LogEntry`, `TranscriptRef` Pydantic models. Tool responses must deserialize using these models (especially for log/refs JSON fields stored in FalkorDB).

### Prior Phase Context
- `.planning/phases/02-ingestion-agent/02-CONTEXT.md` — D-05 (fine-grained tools), D-06 (no dedicated merge tool), D-09 (graph awareness via search tools only). Phase 7 extends this tool set without contradicting these decisions.

### Memory Architecture
- `markdowns/Memory-v3.md` — Node/edge structure, log compression, episode span design. Informs what fields are meaningful to expose via agent tools.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `graph.get_node(graph, node_id)` — Already exists, returns `dict(node.properties)`. D-03 tool wraps this directly. Just needs embedding field stripped from response and log/refs fields parsed from JSON strings.
- `graph.vector_search(graph, query, k)` — Pattern for `search_edges_by_embedding`. Returns `(id, summary, score)` tuples from a `CALL db.idx.vector.queryNodes(...)` query. Edge version needs `db.idx.vector.queryRelationships(...)` or equivalent.
- `tools.py` `search_nodes_by_embedding` — D-01 is a one-line change to add `name` and `aliases` to the dict comprehension in the return value. `vector_search` in graph.py needs to be updated to return name + aliases or a separate enriched query needs to be used.

### Established Patterns
- All tools return plain dicts (not Pydantic models) — `model_dump(mode="json")` used when Pydantic objects need serialization
- Log and refs stored as JSON strings in FalkorDB properties — must parse with `json.loads()` before returning to agent
- FalkorDB vecf32 REMOVE-before-SET pattern for vector updates (not relevant for read-only tools)
- build_tools factory: all tools are closures over `graph` and `store` objects — new tools follow the same pattern

### Integration Points
- `build_tools(graph, store, recording_timestamp)` in `tools.py` is the only place agent tools are registered. New tools are added as closures here and appended to `tools_dict` and `declarations`.
- `init_graph()` in `graph.py` is where FalkorDB indexes are created. If edge vector index is added, it goes here with the same try/except pattern as the existing node vector index.

</code_context>

<specifics>
## Specific Ideas

- The missing `name` field in embedding search results is the most acute gap — the agent has been doing disambiguation against nameless node summaries
- `get_node_edges` direction field ("outgoing"/"incoming") is key for relationship understanding — agent needs to know "this node fears X" vs "X fears this node"
- `get_edge` mirrors `get_node` design intentionally — symmetric tool pair, same response structure philosophy

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 07-agent-tool-capability-gaps-enrich-node-search-results-add-node-relations-and-log-inspection-tools*
*Context gathered: 2026-03-27*
