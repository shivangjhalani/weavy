# Roadmap: LifeOS

## Overview

LifeOS builds a personal memory engine in five phases: lay the infrastructure foundation with atomic storage operations and an agent harness skeleton; wire up the full ingestion pipeline with disambiguation and log compression; add the query agent with vector search and grounded retrieval; derive the theme layer and memo agent on top of a populated graph; finally, evaluate the full system with RAGAS and a hand-crafted temporal query suite. Each phase is a hard dependency on the one before — no querying without ingested data, no themes without a clean graph, no meaningful evaluation without working queries.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Infrastructure** - Devenv, FalkorDB with indexes, atomic storage ops, LLM client, agent harness skeleton
- [ ] **Phase 2: Ingestion Agent** - Full audio-to-graph pipeline with disambiguation, vocabulary registry, and log compression
- [ ] **Phase 3: Query Agent** - Vector search, agentic retrieval strategy, transcript-grounded answer synthesis
- [ ] **Phase 4: Theme Layer + Memo Agent** - Derived theme map with heat/salience, memo agent pattern detection
- [ ] **Phase 5: Evaluation** - RAGAS harness configured for Gemini, test dataset, temporal query suite

## Phase Details

### Phase 1: Infrastructure
**Goal**: The project environment, storage layer, and agent harness skeleton are all in place — FalkorDB is running with correct indexes, every storage mutation re-embeds atomically, and the harness enforces a hard tool-call budget
**Depends on**: Nothing (first phase)
**Requirements**: INFR-01, INFR-02, INFR-03, INFR-04, GRPH-01, GRPH-05, HARN-01, HARN-03
**Success Criteria** (what must be TRUE):
  1. Running `devenv shell` loads the Python environment with all deps; FalkorDB is reachable and indexes exist on `name`, `aliases`, `type`, `transcript_id`
  2. A call to `update_node` re-embeds the node summary in the same operation — no separate embed step is possible
  3. The agent harness accepts a role, system prompt, and tool list; terminates after hitting the hard tool-call budget regardless of LLM output
  4. API keys load from `.env` and the Gemini client produces a completion; Groq client returns a transcription on a test audio file
**Plans**: 3 plans

Plans:
- [x] 01-01-PLAN.md — Project scaffold, deps cleanup, config, models, embeddings, transcript store
- [ ] 01-02-PLAN.md — FalkorDB graph init, indexes, atomic CRUD with auto-embedding, vector search
- [ ] 01-03-PLAN.md — Agent harness with budget enforcement, script stubs for all workflows

### Phase 2: Ingestion Agent
**Goal**: An audio file can be ingested end-to-end — transcribed, parsed by the ingestion agent, and written to the graph as typed nodes and edges with append-only logs, episode spans, and embedded summaries — with no duplicate nodes and controlled type drift
**Depends on**: Phase 1
**Requirements**: TRNS-01, TRNS-02, TRNS-03, GRPH-02, GRPH-03, GRPH-04, INGST-01, INGST-02, INGST-03, INGST-04, INGST-05, INGST-06, COMP-01, COMP-02, COMP-03, VECT-01
**Success Criteria** (what must be TRUE):
  1. Running `ingest.py` on an audio file produces a stored transcript with ID, recording timestamp, and full text
  2. The ingestion agent writes LLM-defined nodes and edges to FalkorDB — no hardcoded types — and each node/edge carries a current summary, append-only log, alias set, and transcript references
  3. Ingesting the same concept twice (with different surface forms) produces one node, not two — alias union and disambiguation work
  4. Episode spans (start_offset, end_offset, summary, embedding) are created as a side effect of graph writes and stored with transcript references
  5. When a node log exceeds the token budget, compression runs automatically and preserves inflection points and reversals while condensing older entries
**Plans**: TBD
**UI hint**: no

### Phase 3: Query Agent
**Goal**: A natural-language question about the ingested journal can be answered with source citations — the query agent autonomously decides its retrieval strategy across all three memory layers using vector similarity, graph traversal, and direct transcript access
**Depends on**: Phase 2
**Requirements**: VECT-02, VECT-03, HARN-02, HARN-04, QURY-01, QURY-02, QURY-03, QURY-04
**Success Criteria** (what must be TRUE):
  1. Running `query.py` with a question returns an answer grounded in specific transcript spans — the answer includes `transcript_id`, `start_offset`, and `end_offset` citations
  2. Vector similarity search across node summaries and episode summaries returns ranked results using FalkorDB native vector indexes
  3. The query agent makes its own tool-call sequence per query — different questions use different retrieval paths — no hardcoded retrieval pipeline is present
  4. Hybrid vector+graph retrieval is available: a vector search result can seed graph traversal in a single operation
**Plans**: TBD

### Phase 4: Theme Layer + Memo Agent
**Goal**: Recurring themes in the journal are identified, scored by current salience, and surfaced to the query agent as a navigation map — the memo agent periodically detects cross-session patterns and updates theme heat values
**Depends on**: Phase 3
**Requirements**: THME-01, THME-02, THME-03, THME-04, THME-05, MEMO-01, MEMO-02, MEMO-03
**Success Criteria** (what must be TRUE):
  1. Running `memo.py` produces themes stored in FalkorDB with text, embedding, heat value, and references to graph nodes and transcript spans
  2. A theme's heat value increases when a related query is run or a new recording touches that theme; heat decays between sessions without any recording activity
  3. The top themes by heat are automatically included in the query agent's system context — no explicit lookup required by the caller
  4. The memo agent creates, updates, and merges themes across multiple ingestion runs without requiring human direction
**Plans**: TBD

### Phase 5: Evaluation
**Goal**: The system's query quality is measurable and reproducible — RAGAS scores (faithfulness, relevance, groundedness) are computed using Gemini as the evaluator, and a hand-crafted temporal query suite covers the evolution/arc-of-change dimension that standard RAGAS misses
**Depends on**: Phase 4
**Requirements**: EVAL-01, EVAL-02, EVAL-03
**Success Criteria** (what must be TRUE):
  1. Running `eval.py` produces RAGAS faithfulness, relevance, and groundedness scores using Gemini (not OpenAI default) as the evaluator LLM
  2. A test transcript dataset is stored and loaded reproducibly — the same eval run on the same dataset produces the same scores
  3. A hand-crafted suite of 10-15 "how has X changed over time?" queries exists and runs through the evaluation harness alongside standard RAGAS metrics
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Infrastructure | 0/3 | Planning complete | - |
| 2. Ingestion Agent | 0/? | Not started | - |
| 3. Query Agent | 0/? | Not started | - |
| 4. Theme Layer + Memo Agent | 0/? | Not started | - |
| 5. Evaluation | 0/? | Not started | - |
