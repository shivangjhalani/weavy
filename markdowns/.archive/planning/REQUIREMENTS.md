# Requirements: Arakne

**Defined:** 2026-04-01
**Core Value:** When a user speaks, their words must be captured, understood, and made retrievable — so their thinking doesn't disappear.

## Requirements

### Transcription Pipeline

- [ ] **VOICE-01**: Recording timestamp extracted from audio filename prefix (format: `YYYY-MM-DDTHH-MM-SS`, e.g. `2021-02-03T03-16-21`); stored as datetime on transcript record; surfaced to agent as human-readable relative time
- [ ] **VOICE-02**: Whisper transcribes an audio file via LiteLLM with segment-level inline timestamps (`[MM:SS]` format, rendered from Groq segment boundaries); Groq currently returns word-level timestamps as well, but the system does not depend on them; all segments returned by Whisper are kept as-is

### Graph Storage

- [ ] **GRAPH-01**: FalkorDB stores nodes (id, aliases, summary, log) and edges (id, from, to, label, log) with the defined schema
- [ ] **GRAPH-02**: FalkorDB vector index initialized at DB startup — absence causes silent brute-force fallback; must be created before the first write
- [ ] **GRAPH-03**: Sequential token registry mints `node:N`, `edge:N`, `rec:N` IDs — tokens are never reused; agent never picks its own ID
- [ ] **GRAPH-04**: Bidirectional index: each transcript record stores `touched_nodes` and `touched_edges`; each node/edge log entry carries `transcript_id`
- [ ] **GRAPH-05**: Log compression: node/edge logs exceeding token budget are compressed to an inline arc summary entry; raw pre-compression entries moved to cold storage keyed by node/edge id

### Tool Layer

- [ ] **TOOL-01**: `search_graph(query, limit)` — hybrid keyword + semantic search; keyword matching covers aliases (not just embeddings); returns id, canonical name, one-line summary, edge count
- [ ] **TOOL-02**: `get_node_neighborhood(node_id, depth)` — returns target node (aliases, summary, last 2-3 log entries) plus each neighbor (edge label, id, canonical name, one-line summary)
- [ ] **TOOL-03**: `get_node(node_id)` — returns all aliases, full summary, all in-budget log entries, edge list with labels only
- [ ] **TOOL-04**: `get_node_log_archive(node_id)` — returns raw pre-compression entries from cold storage
- [ ] **TOOL-05**: `list_transcripts(date_range, limit)` — returns transcript records with human-readable relative timestamps
- [ ] **TOOL-06**: `get_transcript_span(transcript_id, start_offset, end_offset)` — returns exact transcript text for the given time range (seconds)
- [ ] **TOOL-07**: `get_theme(name)` — returns theme state and anchors for a cold-index theme
- [ ] **TOOL-08**: `create_node`, `update_node` (field-selective: summary, aliases, log entry), `create_edge`, `update_edge`, `delete_node`, `delete_edge` — all writes validated by harness for provenance
- [ ] **TOOL-09**: `create_theme`, `update_theme`, `retire_theme` — targeted theme updates (only touched fields change)

### Agent Harness

- [ ] **HARN-01**: Shared tool-calling loop (~80 lines) operates across ingestion, query, and theme modes via system prompt swap — no separate runtimes
- [ ] **HARN-02**: Harness mints sequential tokens at creation time; agent requests creation, harness assigns the next token
- [ ] **HARN-03**: Harness rejects writes without valid provenance: `(transcript_id, start_offset, end_offset)` where offsets are in-bounds, non-equal, and `get_transcript_span` returns non-empty text
- [ ] **HARN-04**: All LLM calls, including Whisper transcription via Groq, route through LiteLLM

### Ingestion Agent

- [ ] **INGEST-01**: Ingestion agent reads full transcript and builds/updates the semantic graph in one pass — no chunking
- [ ] **INGEST-02**: Every write carries provenance `(transcript_id, start_offset, end_offset)` — seconds into the recording
- [ ] **INGEST-03**: Node log entries include `note` (natural language: what changed, emotional nuance, certainty); previous summary auto-archived into log before any rewrite
- [ ] **INGEST-04**: `complete_ingestion()` is the termination signal; its payload simultaneously populates the bidirectional index

### Theme Agent

- [ ] **THEME-01**: Theme agent runs as an async background job after each ingestion — user never waits for it; multiple runs serialized (queued, not parallel)
- [ ] **THEME-02**: Theme schema: `name` (canonical identifier), `state` (1-2 sentences: current truth), `anchors` (node IDs), `status` (categorical: deep | active | emerging | dormant)
- [ ] **THEME-03**: Theme agent operates on delta only — reads `touched_nodes` from `complete_ingestion` payload, not the full graph
- [ ] **THEME-04**: Hot set rendered in full (k themes) + cold index of remaining theme names in every query/ingestion session context

### Query Agent

- [ ] **QUERY-01**: User can ask open-ended natural language questions about their recorded thoughts
- [ ] **QUERY-02**: Query agent uses progressive retrieval: hot themes → `search_graph` → `get_node_neighborhood` → `get_node` → `get_transcript_span`
- [ ] **QUERY-03**: All answers grounded in cited transcript spans — agent must call `get_transcript_span` and include exact quotes; if transcript evidence contradicts cached summaries, transcript wins
- [ ] **QUERY-04**: Agent handles empty-graph cold start gracefully (0 sessions) with appropriate messaging

### Privacy & Data

- [ ] **PRIV-01**: Journal data is stored in user-controlled first-party storage; model-provider traffic is limited to transcription and inference requests rather than third-party application storage
- [ ] **PRIV-02**: FalkorDB persistence configured with AOF for durability; data loss on crash is unacceptable for personal journal content

---

## Out of Scope

| Feature                                 | Reason                                                                                              |
| --------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Streaks / gamification                  | Explicitly anti-vision — no guilt mechanics; this is the antithesis of the product                  |
| Social / sharing features               | Private personal record only; multi-user violates the trust model                                   |
| Real-time streaming transcription       | Batch processing is sufficient; adds complexity without value                                       |
| Clinical / diagnostic features          | Not therapy; never frame as treatment or diagnosis                                                  |
| Checklists, deadlines, kanban           | This is not a task manager; no productivity mechanics                                               |
| Calendar integration / external events  | Inner life only; not a log of external events                                                       |
| Rigid note structure (folders, tags)    | Free-form; structure emerges from the graph, not user-imposed hierarchy                             |
| LangGraph / LangChain                   | Over-engineers the harness; conflicts with harness-owned provenance validation and token minting    |
| External vector DB (ChromaDB, Pinecone) | FalkorDB's native vector index eliminates dual-write sync hazard; already validated                 |
| Word-level timestamp dependence         | Groq currently returns word-level timestamps, but Arakne standardizes on segment boundaries anyway  |

---

## Traceability

| Requirement | Phase   | Status  |
| ----------- | ------- | ------- |
| VOICE-01    | Phase 3 | Pending |
| VOICE-02    | Phase 3 | Pending |
| GRAPH-01    | Phase 1 | Pending |
| GRAPH-02    | Phase 1 | Pending |
| GRAPH-03    | Phase 1 | Pending |
| GRAPH-04    | Phase 1 | Pending |
| GRAPH-05    | Phase 1 | Pending |
| TOOL-01     | Phase 1 | Pending |
| TOOL-02     | Phase 1 | Pending |
| TOOL-03     | Phase 1 | Pending |
| TOOL-04     | Phase 1 | Pending |
| TOOL-05     | Phase 1 | Pending |
| TOOL-06     | Phase 1 | Pending |
| TOOL-07     | Phase 1 | Pending |
| TOOL-08     | Phase 1 | Pending |
| TOOL-09     | Phase 1 | Pending |
| HARN-01     | Phase 1 | Pending |
| HARN-02     | Phase 1 | Pending |
| HARN-03     | Phase 1 | Pending |
| HARN-04     | Phase 1 | Pending |
| INGEST-01   | Phase 2 | Pending |
| INGEST-02   | Phase 2 | Pending |
| INGEST-03   | Phase 2 | Pending |
| INGEST-04   | Phase 2 | Pending |
| THEME-01    | Phase 2 | Pending |
| THEME-02    | Phase 2 | Pending |
| THEME-03    | Phase 2 | Pending |
| THEME-04    | Phase 2 | Pending |
| QUERY-01    | Phase 2 | Pending |
| QUERY-02    | Phase 2 | Pending |
| QUERY-03    | Phase 2 | Pending |
| QUERY-04    | Phase 2 | Pending |
| PRIV-01     | Phase 1 | Pending |
| PRIV-02     | Phase 1 | Pending |

**Coverage:**

- requirements: 34 total
- Mapped to phases: 34
- Unmapped: 0 ✓

---
