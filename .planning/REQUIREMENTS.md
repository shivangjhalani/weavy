# Requirements: LifeOS

**Defined:** 2026-03-25
**Core Value:** Faithfully capture, organize, and retrieve a person's evolving inner life from spoken transcripts — without imposing rigid schemas or losing nuance over time.

## Design Principle

**The Bitter Lesson:** No heuristics, no domain knowledge engineering, no hardcoded rules. Give the LLM minimal structural schemas and let it make all semantic decisions. The system gets better as models improve, not as we add more rules.

## v1 Requirements

### Transcription

- [x] **TRNS-01**: System accepts audio files and transcribes via Groq Whisper API
- [x] **TRNS-02**: Raw transcript stored with unique ID, recording timestamp, and full text
- [x] **TRNS-03**: Episode spans (start_offset, end_offset, summary, embedding) created during ingestion as a side effect of graph writing

### Graph Storage

- [x] **GRPH-01**: FalkorDB graph store initialized with proper indexes on frequently queried properties
- [ ] **GRPH-02**: Nodes carry: current summary, append-only log (timestamped entries), alias set, transcript references (transcript_id, start_offset, end_offset)
- [ ] **GRPH-03**: Edges carry: current summary, append-only log (timestamped entries), transcript references
- [ ] **GRPH-04**: Node and edge types are entirely LLM-defined — no hardcoded entity types or relationship types
- [x] **GRPH-05**: Atomic update operations: updating a node/edge summary always re-embeds in the same operation

### Ingestion Agent

- [x] **INGST-01**: Agent reads full transcript at once (no chunking) and builds/updates graph
- [x] **INGST-02**: Three-tier node disambiguation: exact alias match -> fuzzy similarity -> LLM reasoning
- [x] **INGST-03**: When nodes merge, alias sets are unioned; new surface forms added to existing alias sets
- [x] **INGST-04**: Agent exercises judgment on what's worth persisting — not every sentence becomes a node
- ~~**INGST-05**: Vocabulary registry of existing node/edge types injected into ingestion prompt to reduce type drift~~ — **Dropped (D-01)**: Types removed per Bitter Lesson. No vocabulary registry needed.
- [x] **INGST-06**: Log entries include recording timestamp and natural language note describing what changed or was reinforced

### Log Compression

- [x] **COMP-01**: Token-budgeted compression triggers when a node/edge log exceeds threshold
- [x] **COMP-02**: Compression preserves arc of change — inflection points, reversals, contradictions retained
- [x] **COMP-03**: Recent entries kept intact; older entries condensed into summary

### Vector Search

- [x] **VECT-01**: Embeddings generated via gemini-embedding-001 for node summaries, edge summaries, episode summaries, theme text
- [ ] **VECT-02**: Vector similarity search across all memory layers using FalkorDB native vector indexes
- [ ] **VECT-03**: Hybrid vector + graph retrieval: vector similarity seeds graph traversal, or graph neighbors enhance vector results

### Agent Harness

- [x] **HARN-01**: Single modular harness with agentic loop (LLM + tools + role-specific system prompt)
- [ ] **HARN-02**: Three roles with distinct system prompts: ingestion, query, memo
- [x] **HARN-03**: Hard tool-call budget enforced in harness code — agent forced to answer/complete after budget exhausted
- [ ] **HARN-04**: Tools for: graph read/write/search/merge/delete, vector search, transcript range retrieval

### Query Agent

- [ ] **QURY-01**: Agent decides its own retrieval strategy per query — no hardcoded retrieval pipeline
- [ ] **QURY-02**: Agent uses theme map as navigation context when available
- [ ] **QURY-03**: Answers grounded in transcript references — agent cites source material
- [ ] **QURY-04**: Agent can access all three memory layers (transcripts, graph, themes) via tools

### Theme Layer

- [ ] **THME-01**: Themes are derived memos with text, embeddings, and references to graph nodes + transcript spans
- [ ] **THME-02**: Each theme carries a heat value representing current salience
- [ ] **THME-03**: Heat increases when: user queries something related, new recording touches theme, memo agent reinforces
- [ ] **THME-04**: Heat decays over time naturally
- [ ] **THME-05**: Top themes (by heat) included in always-in-context map for agent; cooler themes accessible on demand

### Memo Agent

- [ ] **MEMO-01**: Memo agent runs with observer voice — detects patterns across graph nodes
- [ ] **MEMO-02**: Creates, updates, and merges themes based on graph state
- [ ] **MEMO-03**: Adjusts heat values and generates theme embeddings

### Evaluation

- [ ] **EVAL-01**: RAGAS evaluation harness configured to use Gemini (not default OpenAI)
- [ ] **EVAL-02**: Evaluates query quality: faithfulness, relevance, groundedness in transcripts
- [ ] **EVAL-03**: Test dataset management for reproducible evaluation runs

### Infrastructure

- [x] **INFR-01**: Python project with uv, ruff, devenv — no global package installs
- [x] **INFR-02**: Environment config via .env (GEMINI_API_KEY, GROQ_API_KEY)
- [x] **INFR-03**: FalkorDB running via Docker in devenv, with index creation at initialization
- [x] **INFR-04**: Runnable Python scripts for each workflow (ingest, query, memo, eval) — no API, no CLI

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Advanced Retrieval

- **ADVR-01**: Temporal query support ("what was I thinking about 3 months ago?")
- **ADVR-02**: Cross-session theme drift detection (change over time, not just heat)

### Graph Maintenance

- **GMNT-01**: Incremental graph repair — retroactively merge nodes discovered to be duplicates
- **GMNT-02**: Bi-temporal versioning on edges (t_valid, t_invalid) for "what was true as of date X" queries

### Evaluation Expansion

- **EVEX-01**: Hand-crafted temporal/evolution query suite alongside RAGAS
- **EVEX-02**: Ingestion quality evaluation (graph accuracy and completeness)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Frontend / UI | Backend experimentation only — validate memory engine first |
| REST/GraphQL API | No HTTP server — manual script execution |
| CLI tool or SDK | Premature abstraction before core is validated |
| Hardcoded NER / entity extraction | Violates Bitter Lesson — no domain knowledge engineering |
| Rigid graph schema (Person/Event/Place) | Forces inner life into categories that don't fit; LLM defines types |
| Fixed retrieval pipeline | Fails for complex multi-hop personal queries; agent decides strategy |
| Real-time streaming transcription | Unnecessary complexity for batch audio journaling |
| Multi-user / auth | Single-user experimentation scope |
| Notifications, streaks, gamification | Anti-goals per vision — not a productivity tool |
| Eval on every ingestion | RAGAS calls expensive; kills iteration speed |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFR-01 | Phase 1 | Complete |
| INFR-02 | Phase 1 | Complete |
| INFR-03 | Phase 1 | Complete |
| INFR-04 | Phase 1 | Complete |
| GRPH-01 | Phase 1 | Complete |
| GRPH-05 | Phase 1 | Complete |
| HARN-01 | Phase 1 | Complete |
| HARN-03 | Phase 1 | Complete |
| TRNS-01 | Phase 2 | Complete |
| TRNS-02 | Phase 2 | Complete |
| TRNS-03 | Phase 2 | Complete |
| GRPH-02 | Phase 2 | Pending |
| GRPH-03 | Phase 2 | Pending |
| GRPH-04 | Phase 2 | Pending |
| INGST-01 | Phase 2 | Complete |
| INGST-02 | Phase 2 | Complete |
| INGST-03 | Phase 2 | Complete |
| INGST-04 | Phase 2 | Complete |
| INGST-05 | Phase 2 | Dropped (D-01) |
| INGST-06 | Phase 2 | Complete |
| COMP-01 | Phase 2 | Complete |
| COMP-02 | Phase 2 | Complete |
| COMP-03 | Phase 2 | Complete |
| VECT-01 | Phase 2 | Complete |
| VECT-02 | Phase 3 | Pending |
| VECT-03 | Phase 3 | Pending |
| HARN-02 | Phase 3 | Pending |
| HARN-04 | Phase 3 | Pending |
| QURY-01 | Phase 3 | Pending |
| QURY-02 | Phase 3 | Pending |
| QURY-03 | Phase 3 | Pending |
| QURY-04 | Phase 3 | Pending |
| THME-01 | Phase 4 | Pending |
| THME-02 | Phase 4 | Pending |
| THME-03 | Phase 4 | Pending |
| THME-04 | Phase 4 | Pending |
| THME-05 | Phase 4 | Pending |
| MEMO-01 | Phase 4 | Pending |
| MEMO-02 | Phase 4 | Pending |
| MEMO-03 | Phase 4 | Pending |
| EVAL-01 | Phase 5 | Pending |
| EVAL-02 | Phase 5 | Pending |
| EVAL-03 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 43 total (1 dropped)
- Mapped to phases: 43
- Unmapped: 0

---
*Requirements defined: 2026-03-25*
*Last updated: 2026-03-26 after Phase 2 planning revision*
