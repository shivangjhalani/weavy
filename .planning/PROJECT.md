# LifeOS

## What This Is

LifeOS is an audio journaling backend — the memory engine that powers a system where users speak their thoughts and the system remembers. You record, it transcribes (Whisper via Groq), an LLM agent builds an evolving semantic graph of your inner life (FalkorDB), and you can query that graph conversationally. This project is the backend core: memory layers, agent harness, and evaluation — no UI, no API, just runnable Python scripts for experimentation.

## Core Value

The memory system must faithfully capture, organize, and retrieve a person's evolving inner life from spoken transcripts — without imposing rigid schemas or losing nuance over time.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Transcription pipeline: accept audio files, transcribe via Groq Whisper API, store transcripts with timestamps and episode spans
- [ ] Semantic graph layer: LLM-defined nodes and edges in FalkorDB — no rigid extraction schema, free-form types and relationships
- [ ] Node/edge structure: current summary, append-only log with recording timestamps, transcript references (transcript_id, start_offset, end_offset)
- [ ] Node disambiguation: alias sets (exact match) → fuzzy similarity → LLM reasoning for ambiguous cases
- [ ] Log compression: token-budgeted compression of node/edge logs, preserving arc of change
- [ ] Theme layer: derived memos with heat/salience scoring, always-in-context map for agent, embeddings via gemini-embedding-001
- [ ] Agent harness: single modular harness with role-specific system prompts for ingestion, query, and memo work — powered by Gemini 2.5 Flash
- [ ] Ingestion agent: reads full transcript, builds/updates graph, creates episode spans, exercises judgment on what's worth persisting
- [ ] Query agent: agentic retrieval across all memory layers — decides its own retrieval strategy per query, uses themes as map
- [ ] Memo agent: periodic theme extraction and maintenance — observer voice, pattern detection
- [ ] Agent tools: graph read/write/search/merge/delete, vector search across layers, transcript range retrieval, hybrid vector+graph tools
- [ ] Evaluation: RAGAS-based query quality evaluation — faithfulness, relevance, groundedness in transcripts
- [ ] Vector embeddings: gemini-embedding-001 for episode summaries, node/edge summaries, theme text

### Out of Scope

- Frontend / UI — backend experimentation only, no mobile or web interface
- REST/GraphQL API — no HTTP server, just runnable Python scripts
- CLI tool or SDK packaging — manual script execution for testing
- Notifications, streaks, gamification — anti-goals per vision
- Productivity features (checklists, due dates, kanban) — not a productivity tool
- Real-time streaming transcription — batch audio file processing only
- Multi-user / auth — single-user experimentation

## Context

- **Platform:** Python backend, runnable scripts for experimentation
- **Graph DB:** FalkorDB (Docker via devenv.nix, always running)
- **LLM:** Gemini 2.5 Flash via GEMINI_API_KEY
- **Transcription:** Whisper via Groq API (GROQ_API_KEY)
- **Embeddings:** gemini-embedding-001
- **Evaluation:** RAGAS for query quality (faithfulness, relevance, groundedness)
- **Environment:** NixOS with devenv, uv for Python deps, ruff for linting
- **Design philosophy:** LLM-defined semantic graph — no rigid schema, maximize expressiveness, let the LLM make all semantic decisions. General-purpose > human-engineered heuristics. The system becomes more powerful as models improve.
- **Memory architecture:** Three layers — (1) transcripts as source of truth, (2) LLM-built semantic graph in FalkorDB, (3) derived themes with heat/salience. All graph structure emerges from LLM judgment, not hardcoded constraints.
- **Key insight from vision:** "The mind is a poor witness to its own changes over time." LifeOS externalizes the arc of a person's thinking so they can see their own evolution.

## Constraints

- **Tech stack**: Python, FalkorDB, Gemini 2.5 Flash, Groq Whisper, gemini-embedding-001 — these are decided
- **Environment**: NixOS + devenv — no global package managers, use uv for Python
- **No rigid schema**: The graph schema must NOT be hardcoded — LLM defines node types, edge types, and all semantic structure
- **Transcript primacy**: Raw transcripts are the only canonical record; everything else is derived and reconstructable
- **Single agent harness**: One harness with role-specific prompts, not separate agent implementations

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| FalkorDB for graph storage | Already set up in devenv, Redis-compatible, supports Cypher queries | — Pending |
| Gemini 2.5 Flash as reasoning engine | Cost-effective, fast, good for experimentation phase | — Pending |
| LLM-defined graph schema | Avoids baking in assumptions about what questions will be asked; becomes more powerful as models improve | — Pending |
| Three-layer memory (transcripts → graph → themes) | Separates source of truth from derived structure from high-level patterns | — Pending |
| RAGAS for evaluation | Established framework for RAG quality evaluation — faithfulness, relevance, groundedness | — Pending |
| Backend-only, scripts for experimentation | Focus on getting the memory system right before building interfaces | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-25 after initialization*
