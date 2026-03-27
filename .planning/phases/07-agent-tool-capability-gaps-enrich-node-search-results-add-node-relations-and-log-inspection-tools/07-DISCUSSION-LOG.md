# Phase 7: Agent Tool Capability Gaps - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-27
**Phase:** 07-agent-tool-capability-gaps-enrich-node-search-results-add-node-relations-and-log-inspection-tools
**Areas discussed:** Search result enrichment, Node inspection tool, Node relations tools, Log inspection scope

---

## Search Result Enrichment

| Option | Description | Selected |
|--------|-------------|----------|
| Add name + aliases (Recommended) | Return node_id, name, aliases, summary, score. Minimal change, high impact. | ✓ |
| Full node data | Return everything: name, aliases, summary, refs, score. More data per search call. | |
| name only | Return node_id, name, summary, score. Enough to identify without aliases. | |

**User's choice:** Add name + aliases to search_nodes_by_embedding matches
**Notes:** Alias search (search_nodes_by_alias) kept as-is — current {id, name, aliases, summary} is sufficient.

---

## Node Inspection Tool

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — expose get_node(node_id) as a tool (Recommended) | Full node state readable by agent before deciding to update. | ✓ |
| No — enriched search results are enough | If search results include name + aliases, agent has enough context. | |

**User's choice:** Expose get_node as agent tool

| Option | Description | Selected |
|--------|-------------|----------|
| All fields except embedding (Recommended) | name, aliases, summary, refs, log entries, created_at, updated_at. Embedding is useless to LLM. | ✓ |
| Log size/count only | Summarize log as count + last N entries to protect context window. | |
| All fields including full log | Everything including full log text. Most complete. | |

**User's choice:** All fields except embedding

---

## Node Relations Tools

| Option | Description | Selected |
|--------|-------------|----------|
| get_node_edges(node_id) — single bidirectional tool (Recommended) | Returns all edges both outgoing and incoming. | ✓ |
| Two tools: get_outgoing_edges + get_incoming_edges | Separate tools for direction. More tool calls but more targeted. | |
| search_edges_by_embedding(query) only | Semantic search over edge summaries only, no structural traversal. | |

**User's choice:** Single bidirectional get_node_edges

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — add both get_node_edges and search_edges_by_embedding | Structural traversal + semantic search. Same pattern as nodes. | ✓ |
| No — get_node_edges is sufficient for Phase 7 | Edge semantic search is Phase 3/query agent concern. | |

**User's choice:** Add both tools

| Option | Description | Selected |
|--------|-------------|----------|
| edge_id, label, summary, source (id+name), target (id+name), direction (Recommended) | Full context for agent to understand and act on an edge. | ✓ |
| Full edge data including refs and log entries | Also include transcript refs and log history per edge. | |

**User's choice:** Recommended fields per edge in get_node_edges response

---

## Log Inspection Scope

| Option | Description | Selected |
|--------|-------------|----------|
| get_node covers node logs; add get_edge(edge_id) for edge inspection too (Recommended) | Symmetric design — mirrors get_node for edges. | ✓ |
| Node log only | Edges are simpler, agent doesn't need deep edge history. | |
| Separate get_node_log and get_edge_log tools | Dedicated log tools, no full inspection tools. | |

**User's choice:** Add get_edge(edge_id) as symmetric counterpart to get_node

| Option | Description | Selected |
|--------|-------------|----------|
| Parsed list of {recorded_at, note} objects (Recommended) | Human-readable history list for agent consumption. | ✓ |
| Raw JSON string as stored in FalkorDB | Agent has to parse it. Simpler implementation but messier for LLM. | |

**User's choice:** Parsed list

---

## Claude's Discretion

- Whether search_edges_by_embedding uses a FalkorDB vector index on edges or falls back to full-scan cosine computation — researcher to verify FalkorDB edge vector index support
- Exact parameter naming
- Test coverage approach

## Deferred Ideas

None — discussion stayed within phase scope
