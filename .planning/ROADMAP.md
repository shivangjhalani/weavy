# Roadmap: Arachne

**Milestone:** v1
**Granularity:** Coarse (3 phases)
**Coverage:** 38/38 v1 requirements mapped

---

## Phases

- [ ] **Phase 1: Backend Foundation** - Storage schema, tool layer, and agent harness — everything agents sit on top of
- [ ] **Phase 2: Agent Pipeline** - Ingestion agent, theme agent, query agent, and log compression — the full intelligence layer
- [ ] **Phase 3: Transcription, API & Mobile** - Whisper pipeline, FastAPI backend, and React Native/Expo client — the user-facing surface

---

## Phase Details

### Phase 1: Backend Foundation
**Goal**: The storage schema, tool functions, and harness invariants are in place and independently tested — any agent can be wired up on top without revisiting this layer
**Depends on**: Nothing (first phase)
**Requirements**: GRAPH-01, GRAPH-02, GRAPH-03, GRAPH-04, GRAPH-05, TOOL-01, TOOL-02, TOOL-03, TOOL-04, TOOL-05, TOOL-06, TOOL-07, TOOL-08, TOOL-09, TOOL-10, HARN-01, HARN-02, HARN-03, HARN-04, HARN-05, PRIV-01, PRIV-02
**Success Criteria** (what must be TRUE):
  1. FalkorDB initializes with the correct schema (nodes, edges, themes, token registry, vector index) and all round-trip array field serialization tests pass — no silent data corruption
  2. Every tool function (`search_graph` through `complete_ingestion`) can be called against a live FalkorDB fixture and returns the correct shape; hybrid search matches aliases, not just embeddings
  3. The harness rejects any write that lacks valid provenance (null offsets, out-of-bounds, or span returning empty text) and mints sequential tokens the agent never picks itself
  4. Hard call budget (60 calls) and wall-clock timeout terminate a runaway loop with `partial=true` before any agent is wired in
  5. All data is local; FalkorDB AOF persistence is configured so a crash does not lose journal entries
**Plans**: TBD

**Key risks**:
- FalkorDB array field serialization bug (log entries double-serialized as JSON strings inside arrays) — invisible until query time; validate round-trip before writing any agent code
- Vector index silent fallback if not created before first write — create in DB init script; verify absence raises an error not a silently slower query
- REMOVE-before-SET required for vector property updates — carry forward from prior codebase


### Phase 2: Agent Pipeline
**Goal**: A real transcript can be ingested into the semantic graph, themes emerge in the background, and a user can ask a natural language question and receive an answer grounded in cited transcript spans
**Depends on**: Phase 1
**Requirements**: INGEST-01, INGEST-02, INGEST-03, INGEST-04, INGEST-05, INGEST-06, THEME-01, THEME-02, THEME-03, THEME-04, QUERY-01, QUERY-02, QUERY-03, QUERY-04
**Success Criteria** (what must be TRUE):
  1. Ingesting a real transcript populates the graph with nodes and edges, fires `complete_ingestion`, and populates the bidirectional index — the create:update ratio health metric is surfaced per session
  2. The ingestion agent searches before creating; a 5-transcript integration run shows no obvious duplicate nodes for the same concept across different surface forms
  3. After ingestion completes, the theme agent runs as a background job on `touched_nodes` only (not the full graph) and produces themes with the correct schema (`name`, `state`, `anchors`, `status`)
  4. A user question returns an answer that includes exact quoted transcript spans from `get_transcript_span` — the answer is grounded in real words, not hallucinated summaries
  5. Log compression fires when a node's log exceeds the token budget: raw entries move to cold storage and an inline arc summary replaces them; the query agent can still reconstruct the arc via the compression entry
**Plans**: TBD

**Key risks**:
- Node proliferation — ingestion agent creates duplicates instead of merging; mitigated by search-before-create discipline in the system prompt + create:update ratio metric + alias-boost in search_graph
- Prompt engineering underestimation — ingestion and query prompts each need 3-5 iteration rounds against real transcripts; plan iteration budget, do not treat these as one-shot deliverables
- Summary drift — node summaries become bland over time; enforced via prompt constraints on when rewrite is allowed


### Phase 3: Transcription, API & Mobile
**Goal**: A user can open the mobile app, tap to record a voice memo, and have it transcribed, ingested, and queryable — the complete end-to-end loop is accessible from an iOS device
**Depends on**: Phase 2
**Requirements**: VOICE-01, VOICE-02, VOICE-03
**Success Criteria** (what must be TRUE):
  1. User taps once to start recording on iOS; recording stops on second tap; the app shows a processing indicator and the transcript appears in the chronological entry list within a reasonable time
  2. Whisper transcription renders sentence-level timestamps in `[MM:SS]` format from segment boundaries; low-confidence segments and meta-tokens (`[MUSIC]`, `[APPLAUSE]`) are stripped; recordings under 5 seconds of non-silence are rejected before upload
  3. User types a natural language question in the app and receives a cited answer with exact transcript quotes displayed inline — the full loop (record → ingest → theme → query) is exercised end-to-end on a real device
**Plans**: TBD

**UI hint**: yes

**Key risks**:
- Expo SDK 53 background audio on iOS requires `UIBackgroundModes: audio` in `app.json` and `Audio.setAudioModeAsync` configuration — verify against current SDK docs before implementation; do not assume prior SDK behavior
- Whisper hallucination on silence and noise — confidence filtering and minimum duration gate must be in place before first real user session
- FastAPI not yet in `pyproject.toml` — add `fastapi>=0.120`, `uvicorn[standard]`, `python-multipart` before this phase begins

---

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Backend Foundation | 0/? | Not started | - |
| 2. Agent Pipeline | 0/? | Not started | - |
| 3. Transcription, API & Mobile | 0/? | Not started | - |

---
*Roadmap created: 2026-04-01*
*Last updated: 2026-04-01 after initial creation*
