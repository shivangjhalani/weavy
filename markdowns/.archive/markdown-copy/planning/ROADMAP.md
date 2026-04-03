# Roadmap: Arakne

**Milestone:** v1
**Granularity:** Coarse (3 phases)
**Coverage:** 34/34 v1 requirements mapped

---

## Phases

- [ ] **Phase 1: Backend Foundation** - Storage schema, tool layer, and agent harness — everything agents sit on top of
- [ ] **Phase 2: Agent Pipeline** - Ingestion agent, theme agent, query agent, and log compression — the full intelligence layer
- [ ] **Phase 3: Transcription Pipeline** - Whisper pipeline as a Python script — takes an audio file, returns a structured transcript ready for ingestion

---

## Phase Details

### Phase 1: Backend Foundation

**Goal**: The storage schema, tool functions, and harness invariants are in place and independently tested — any agent can be wired up on top without revisiting this layer
**Depends on**: Nothing (first phase)
**Requirements**: GRAPH-01, GRAPH-02, GRAPH-03, GRAPH-04, GRAPH-05, TOOL-01, TOOL-02, TOOL-03, TOOL-04, TOOL-05, TOOL-06, TOOL-07, TOOL-08, TOOL-09, HARN-01, HARN-02, HARN-03, HARN-04, PRIV-01, PRIV-02
**Success Criteria** (what must be TRUE):

1. FalkorDB initializes with the correct schema (nodes, edges, themes, token registry, vector index) and all round-trip array field serialization tests pass — no silent data corruption
2. Every v1 tool function plus the `complete_ingestion` control call can be called against a live FalkorDB fixture and returns the correct shape; hybrid search matches aliases, not just embeddings
3. The harness rejects any write that lacks valid provenance (null offsets, out-of-bounds, or span returning empty text) and mints sequential tokens the agent never picks itself; all LLM calls route through LiteLLM
4. Journal data is persisted in user-controlled storage; FalkorDB AOF persistence is configured so a crash does not lose journal entries
   **Plans**: TBD

**Key risks**:

- FalkorDB array field serialization bug (log entries double-serialized as JSON strings inside arrays) — invisible until query time; validate round-trip before writing any agent code
- Vector index silent fallback if not created before first write — create in DB init script; verify absence raises an error not a silently slower query
- REMOVE-before-SET required for vector property updates — carry forward from prior codebase

### Phase 2: Agent Pipeline

**Goal**: A real transcript can be ingested into the semantic graph, themes emerge in the background, and a user can ask a natural language question and receive an answer grounded in cited transcript spans
**Depends on**: Phase 1
**Requirements**: INGEST-01, INGEST-02, INGEST-03, INGEST-04, THEME-01, THEME-02, THEME-03, THEME-04, QUERY-01, QUERY-02, QUERY-03, QUERY-04
**Success Criteria** (what must be TRUE):

1. Ingesting a real transcript populates the graph with nodes and edges, fires `complete_ingestion`, and populates the bidirectional index
2. After ingestion completes, the theme agent runs as a background job on `touched_nodes` only (not the full graph) and produces themes with the correct schema (`name`, `state`, `anchors`, `status`)
3. A user question returns an answer that includes exact quoted transcript spans from `get_transcript_span` — the answer is grounded in real words, not hallucinated summaries
4. Log compression fires when a node's log exceeds the token budget: raw entries move to cold storage and an inline arc summary replaces them; the query agent can still reconstruct the arc via the compression entry
   **Plans**: TBD

**Key risks**:

- Node proliferation — ingestion agent creates duplicates instead of merging; mitigated by search-before-create discipline in the system prompt + alias-boost in search_graph
- Prompt engineering underestimation — ingestion and query prompts each need 3-5 iteration rounds against real transcripts; plan iteration budget, do not treat these as one-shot deliverables
- Summary drift — node summaries become bland over time; enforced via prompt constraints on when rewrite is allowed

### Phase 3: Transcription Pipeline

**Goal**: A Python script accepts an audio file path and produces a structured transcript (text with `[MM:SS]` sentence timestamps and `rec:N` ID) ready to be passed directly into the ingestion agent
**Depends on**: Phase 2
**Requirements**: VOICE-01, VOICE-02
**Success Criteria** (what must be TRUE):

1. Recording timestamp is correctly extracted from audio filename prefix (format: `YYYY-MM-DDTHH-MM-SS`)
2. Running `python ingest_audio.py <file.m4a>` produces a transcript with `[MM:SS]` sentence-level timestamps derived from Whisper segment boundaries, with all segments kept as returned by Whisper
3. The output transcript is passed end-to-end through the ingestion agent — the full pipeline (audio file → transcript → graph → themes) runs from a single script call
   **Plans**: TBD

**Key risks**:

- `whisper-large-v3-turbo` returns `words: null` despite accepting `timestamp_granularities=["word"]` — segment boundaries only; do not depend on word-level

---

## Progress

| Phase                     | Plans Complete | Status      | Completed |
| ------------------------- | -------------- | ----------- | --------- |
| 1. Backend Foundation     | 0/?            | Not started | -         |
| 2. Agent Pipeline         | 0/?            | Not started | -         |
| 3. Transcription Pipeline | 0/?            | Not started | -         |
