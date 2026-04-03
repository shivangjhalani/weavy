# Arakne

## What This Is

Arakne is a Python backend that processes and stores audio recordings of spoken thoughts — ambitions, worries, decisions, emotions — and captures them into an evolving, queryable semantic graph. An audio file goes in, Whisper transcribes it, the ingestion agent builds the graph, and a query script answers questions like "what have I been struggling with most this quarter?" — answered directly from your own words.

## Core Value

When a user speaks, their words must be captured, understood, and made retrievable — so their thinking doesn't disappear.

## Requirements

### Validated

(None yet — ship to validate)

### Active

**Transcription Pipeline**

- [ ] VOICE-02: Whisper transcribes an audio file with inline segment-level timestamps derived from Groq segment boundaries (seconds into recording)

**Ingestion Agent**

- [ ] INGEST-01: Ingestion agent reads full transcript and builds/updates semantic graph in one pass
- [ ] INGEST-02: Agent creates nodes (concepts, emotions, decisions, questions, people) with sequential readable IDs (node:N)
- [ ] INGEST-03: Agent creates edges with free-form natural language labels and sequential IDs (edge:N)
- [ ] INGEST-04: Every write carries provenance: (transcript_id, start_offset, end_offset in seconds)
- [ ] INGEST-05: Node schema: id, aliases (aliases[0] = canonical), summary, append-only log
- [ ] INGEST-06: Harness mints sequential tokens — agent never picks its own IDs
- [ ] INGEST-07: Agent calls complete_ingestion(summary, touched_nodes, touched_edges) as termination signal
- [ ] INGEST-08: Old summary auto-archived into node log before any rewrite

**Semantic Graph (FalkorDB)**

- [ ] GRAPH-01: FalkorDB stores nodes and edges with log entries
- [ ] GRAPH-02: Bidirectional index: transcript → touched nodes/edges, and each log entry → transcript
- [ ] GRAPH-03: Log compression: entries exceeding token budget compressed to inline arc summary; raw entries moved to cold storage
- [ ] GRAPH-04: No type field on nodes — summary carries all semantic meaning

**Theme Agent**

- [ ] THEME-01: Theme agent runs async after each ingestion (background job)
- [ ] THEME-02: Theme schema: name (identifier), state (1-2 sentences), anchors (node IDs), status labels
- [ ] THEME-03: Status labels: deep | active | emerging | dormant (independent depth + recency dimensions)
- [ ] THEME-04: Agent operates on delta (touched nodes), not full graph
- [ ] THEME-05: Hot set rendering: k themes in full + cold index of remaining names in prompt
- [ ] THEME-06: Tools: update_theme, create_theme, retire_theme

**Query Agent**

- [ ] QUERY-01: User can ask open-ended questions about their recorded thoughts
- [ ] QUERY-02: Agent answers grounded in cited transcript spans (get_transcript_span)
- [ ] QUERY-03: Progressive retrieval: hot themes → search_graph → get_node_neighborhood → get_node → get_transcript_span
- [ ] QUERY-04: Agent discovers log archive only through inline compression entries (no separate schema pointer)

**Read Tools**

- [ ] READ-01: search_graph(query, limit) — hybrid keyword + semantic, returns id/name/summary/edge-count
- [ ] READ-02: get_node_neighborhood(node_id, depth) — node + neighbors with edge labels
- [ ] READ-03: get_node(node_id) — full aliases, summary, in-budget log entries, edge list
- [ ] READ-04: get_node_log_archive(node_id) — raw pre-compression entries
- [ ] READ-05: list_transcripts(date_range, limit) — temporal query support
- [ ] READ-06: get_transcript_span(transcript_id, start_offset, end_offset) — exact quote retrieval
- [ ] READ-07: get_theme(name) — on-demand theme fetch for cold-index themes

**Write Tools**

- [ ] WRITE-01: create_node, update_node (field-selective updates), create_edge, update_edge, delete_node, delete_edge
- [ ] WRITE-02: Harness validates provenance on every write (rejects writes without transcript + offsets)

### Out of Scope

- Checklists, deadlines, kanban boards — this is not a productivity/task manager
- Streaks, points, gamification — no guilt mechanics
- Clinical or diagnostic features — not therapy
- Audio-only archive without transcript retrieval or meaning surfacing — not a voice memo dump
- Multi-user / sharing features — private personal record only (v1)
- Real-time streaming transcription — batch processing is sufficient for v1

## Context

- **Language/runtime:** Python (uv), project initialized as `arakne`
- **Graph DB:** FalkorDB (already in devenv.nix)
- **Transcription:** Whisper via Groq (`whisper-large-v3-turbo`) — current API can return both word-level and segment-level timestamps, but Arakne standardizes on segment-level timestamps and keeps all segments as-is
- **LLM routing:** All LLM calls, including Whisper transcription via Groq, route through LiteLLM
- **Audio retention:** Source audio files stored alongside transcripts for playback and audit; the transcript remains the canonical record. Recording timestamp extracted from filename prefix (format: `YYYY-MM-DDTHH-MM-SS`, e.g. `2021-02-03T03-16-21`)
- **Prototype workflow:** Audio files in a local folder, ingested manually via Python scripts.
- **LLM:** Agentic loop — same harness across ingestion, query, and theme modes; different system prompts
- **ID scheme:** Sequential readable tokens per entity type (node:N, edge:N, rec:N) — no UUIDs; LLMs hallucinate high-entropy identifiers
- **Architecture:** Three memory layers — transcripts (canonical), semantic graph (derived cache), themes (derived orientation map). Graph and themes are rebuildable from transcripts.
- **Design docs:** `markdowns/Vision.md` (product vision), `markdowns/Memory-v5.md` (memory architecture spec)

## Constraints

- **Privacy**: Journal data is stored in user-controlled first-party storage; third-party model providers are used only for transcription and inference, not as the system of record
- **Rebuilding**: Graph and themes must be fully reconstructable from raw transcripts — no orphaned derived state
- **ID stability**: Sequential token IDs must never be reused or reordered after creation
- **LLM quality**: No rigid extraction schema — all semantic decisions delegated to LLM judgment

## Key Decisions

| Decision                                 | Rationale                                                                                                             | Outcome   |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | --------- |
| FalkorDB for graph storage               | Native graph traversal, already in devenv — avoids bolting graph onto relational DB                                   | — Pending |
| Sequential readable IDs (not UUIDs)      | LLMs hallucinate high-entropy identifiers; node:12 is unambiguous and memorable                                       | — Pending |
| No type field on nodes                   | Free-form types degrade over time (emotion/feeling/emotional-state for same concept); summary is the semantic carrier | — Pending |
| Store source audio alongside transcripts | Playback and audit matter, but transcripts remain canonical and queryable                                             | — Pending |
| Separate theme agent (not inline)        | Prevents every ingestion from doing full-graph re-analysis; delta-only operation scales                               | — Pending |
| One harness, three system prompts        | Derived memory stays live during chat; no batch-only pipeline                                                         | — Pending |
| LiteLLM for all LLM calls               | Unified interface across models including Whisper via Groq; simplifies provider swaps                                 | — Pending |

---
