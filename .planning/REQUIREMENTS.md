# Requirements: Arachne

**Defined:** 2026-04-01
**Core Value:** When a user speaks, their words must be captured, understood, and made retrievable — so their thinking doesn't disappear.

## v1 Requirements

### Transcription Pipeline

- [ ] **VOICE-02**: Whisper transcribes an audio file with sentence-level inline timestamps (`[MM:SS]` format, using segment boundaries — word-level timestamps are not available on `whisper-large-v3-turbo`)
- [ ] **VOICE-03**: Transcription strips low-confidence segments and meta-tokens (`[MUSIC]`, `[APPLAUSE]`); audio under 5 seconds of non-silence is rejected

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
- [ ] **TOOL-08**: `create_node`, `update_node` (partial: summary, aliases, log entry), `create_edge`, `update_edge`, `delete_node`, `delete_edge` — all writes validated by harness for provenance
- [ ] **TOOL-09**: `create_theme`, `update_theme`, `retire_theme` — targeted theme updates (only touched fields change)
- [ ] **TOOL-10**: `complete_ingestion(summary, touched_nodes, touched_edges)` — dual-purpose: terminates the ingestion loop AND populates the bidirectional index on the transcript record

### Agent Harness

- [ ] **HARN-01**: Shared tool-calling loop (~80 lines) operates across ingestion, query, and theme modes via system prompt swap — no separate runtimes
- [ ] **HARN-02**: Harness mints sequential tokens at creation time; agent requests creation, harness assigns the next token
- [ ] **HARN-03**: Harness rejects writes without valid provenance: `(transcript_id, start_offset, end_offset)` where offsets are in-bounds, non-equal, and `get_transcript_span` returns non-empty text
- [ ] **HARN-04**: Hard tool call budget (default 60 calls) and wall-clock timeout (2-3 minutes); graceful `partial=true` termination if budget exceeded without `complete_ingestion`
- [ ] **HARN-05**: Idempotent call detection — same tool + args three times in succession → inject termination

### Ingestion Agent

- [ ] **INGEST-01**: Ingestion agent reads full transcript and builds/updates the semantic graph in one pass — no chunking
- [ ] **INGEST-02**: Agent follows search-before-create discipline: searches for existing nodes before creating new ones; disambiguation decision rule in system prompt
- [ ] **INGEST-03**: Every write carries provenance `(transcript_id, start_offset, end_offset)` — seconds into the recording
- [ ] **INGEST-04**: Node log entries include `note` (natural language: what changed, emotional nuance, certainty); previous summary auto-archived into log before any rewrite
- [ ] **INGEST-05**: `complete_ingestion()` is the termination signal; its payload simultaneously populates the bidirectional index
- [ ] **INGEST-06**: Post-ingestion health metric: create:update ratio per session (tracks node proliferation drift)

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

- [ ] **PRIV-01**: All data stays local / user-controlled — no third-party storage of personal content
- [ ] **PRIV-02**: FalkorDB persistence configured with AOF for durability; data loss on crash is unacceptable for personal journal content

---

## v2 Requirements

### Pattern Surfacing
- **PATT-01**: System proactively surfaces patterns: "you've returned to this topic 7 times since January"
- **PATT-02**: Emotion shift detection across a topic over time

### Extended Platform
- **PLAT-01**: Android support (iOS first for v1)
- **PLAT-02**: Export to Markdown / Obsidian format
- **PLAT-03**: Multi-language transcription

### Advanced Memory
- **MEM-01**: Memo mode — observer agent that notices patterns and writes memos unprompted
- **MEM-02**: Bi-temporal graph versioning — query "what was true as of date X" structurally (Graphiti arxiv 2501.13956)

---

## Out of Scope

| Feature | Reason |
|---------|--------|
| Mobile app / frontend | Out of scope for this milestone — backend Python scripts only; designed to be callable as API later |
| HTTP API (FastAPI, uvicorn) | Not in this milestone — scripts are the interface; API layer added when frontend is ready |
| Streaks / gamification | Explicitly anti-vision — no guilt mechanics; this is the antithesis of the product |
| Social / sharing features | Private personal record only; multi-user violates the trust model |
| Real-time streaming transcription | Batch processing is sufficient; adds complexity without value |
| Clinical / diagnostic features | Not therapy; never frame as treatment or diagnosis |
| Checklists, deadlines, kanban | This is not a task manager; no productivity mechanics |
| Calendar integration / external events | Inner life only; not a log of external events |
| Rigid note structure (folders, tags) | Free-form; structure emerges from the graph, not user-imposed hierarchy |
| LangGraph / LangChain | Over-engineers the harness; conflicts with harness-owned provenance validation and token minting |
| External vector DB (ChromaDB, Pinecone) | FalkorDB's native vector index eliminates dual-write sync hazard; already validated |
| Word-level Whisper timestamps | `whisper-large-v3-turbo` returns null for word timestamps — use segment boundaries only |

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| VOICE-02 | Phase 3 | Pending |
| VOICE-03 | Phase 3 | Pending |
| GRAPH-01 | Phase 1 | Pending |
| GRAPH-02 | Phase 1 | Pending |
| GRAPH-03 | Phase 1 | Pending |
| GRAPH-04 | Phase 1 | Pending |
| GRAPH-05 | Phase 1 | Pending |
| TOOL-01 | Phase 1 | Pending |
| TOOL-02 | Phase 1 | Pending |
| TOOL-03 | Phase 1 | Pending |
| TOOL-04 | Phase 1 | Pending |
| TOOL-05 | Phase 1 | Pending |
| TOOL-06 | Phase 1 | Pending |
| TOOL-07 | Phase 1 | Pending |
| TOOL-08 | Phase 1 | Pending |
| TOOL-09 | Phase 1 | Pending |
| TOOL-10 | Phase 1 | Pending |
| HARN-01 | Phase 1 | Pending |
| HARN-02 | Phase 1 | Pending |
| HARN-03 | Phase 1 | Pending |
| HARN-04 | Phase 1 | Pending |
| HARN-05 | Phase 1 | Pending |
| INGEST-01 | Phase 2 | Pending |
| INGEST-02 | Phase 2 | Pending |
| INGEST-03 | Phase 2 | Pending |
| INGEST-04 | Phase 2 | Pending |
| INGEST-05 | Phase 2 | Pending |
| INGEST-06 | Phase 2 | Pending |
| THEME-01 | Phase 2 | Pending |
| THEME-02 | Phase 2 | Pending |
| THEME-03 | Phase 2 | Pending |
| THEME-04 | Phase 2 | Pending |
| QUERY-01 | Phase 2 | Pending |
| QUERY-02 | Phase 2 | Pending |
| QUERY-03 | Phase 2 | Pending |
| QUERY-04 | Phase 2 | Pending |
| PRIV-01 | Phase 1 | Pending |
| PRIV-02 | Phase 1 | Pending |

**Coverage:**
- v1 requirements: 37 total
- Mapped to phases: 37
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-01*
*Last updated: 2026-04-01 after initial definition*
