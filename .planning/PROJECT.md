# LifeOS

## What This Is

LifeOS is an audio journaling backend — the memory engine that powers a system where users speak their thoughts and the system remembers. You record, it transcribes (Whisper via Groq), an LLM agent builds an evolving semantic graph of your inner life (FalkorDB), and you can query that graph conversationally. This project is the backend core: memory layers, agent harness, and evaluation — no UI, no API, just runnable Python scripts for experimentation.

## Core Value

The memory system must faithfully capture, organize, and retrieve a person's evolving inner life from spoken transcripts — without imposing rigid schemas or losing nuance over time.

## Requirements

### Validated

- [x] Transcription pipeline: accept audio files, transcribe via Groq Whisper API — Validated in Phase 1: Infrastructure (transcribe module refactored, config loads API keys)
- [x] Semantic graph layer: LLM-defined nodes and edges in FalkorDB — Validated in Phase 1: Infrastructure (FalkorDB graph init with indexes, atomic CRUD)
- [x] Node/edge structure: current summary, append-only log with recording timestamps, transcript references — Validated in Phase 1: Infrastructure (Pydantic models + graph CRUD)
- [x] Agent harness: single modular harness with role-specific system prompts — Validated in Phase 1: Infrastructure (AgentHarness with budget enforcement); budget removed in Phase 2 per D-08
- [x] Vector embeddings: gemini-embedding-001 for node/edge summaries — Validated in Phase 1: Infrastructure (embed_text/embed_query + atomic re-embedding in graph ops)
- [x] Transcription pipeline: store transcripts with timestamps and episode spans — Validated in Phase 2: Ingestion Agent (Transcript model, EpisodeSpan model, ingest.py stores full pipeline output)
- [x] Semantic graph layer: no rigid extraction schema, free-form types and relationships — Validated in Phase 2: Ingestion Agent (Node.name/Edge.label replace type field, ingest prompt has no hardcoded types)
- [x] Node/edge structure: episode spans with start_offset, end_offset, summary, embedding — Validated in Phase 2: Ingestion Agent (EpisodeSpan model, create_episode_spans tool)
- [x] Node disambiguation: alias sets (exact match) + semantic similarity search — Validated in Phase 2: Ingestion Agent (search_nodes_by_alias + search_nodes_by_embedding tools, prompt guidance)
- [x] Log compression: token-budgeted compression preserving arc of change — Validated in Phase 2: Ingestion Agent (compress.py, 2000-token threshold, last-3-intact, inflection/reversal preservation)
- [x] Ingestion agent: reads full transcript, builds/updates graph, creates episode spans, exercises judgment — Validated in Phase 2: Ingestion Agent (9 tools, ingest prompt with selectivity guidance)
- [x] Agent tools: 9 graph tools (search, create, update, delete for nodes/edges + episode spans) — Validated in Phase 2: Ingestion Agent (build_tools factory)
- [x] Agent tools: enriched search results with name+aliases; 4 new inspection tools (get_node, get_node_edges, get_edge, search_edges_by_embedding) — Validated in Phase 7: Agent Tool Capability Gaps (13 tools total; edge vector index added)

### Active

- [ ] Theme layer: derived memos with heat/salience scoring, always-in-context map for agent, embeddings via gemini-embedding-001
- [ ] Agent harness: extend with query and memo role-specific tool sets (ingestion tools done Phase 2, query/memo in Phase 3-4)
- [ ] Query agent: agentic retrieval across all memory layers — decides its own retrieval strategy per query, uses themes as map
- [ ] Memo agent: periodic theme extraction and maintenance — observer voice, pattern detection
- [ ] Evaluation: RAGAS-based query quality evaluation — faithfulness, relevance, groundedness in transcripts
- [ ] Vector embeddings: gemini-embedding-001 for theme text (node/edge/episode embedding done)

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
- **LLM:** Gemini 2.5 Flash via litellm (provider-agnostic, per-run cost tracking)
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
| FalkorDB for graph storage | Already set up in devenv, Redis-compatible, supports Cypher queries | Validated Phase 1 — indexes, atomic CRUD, vector search working |
| Gemini 2.5 Flash as reasoning engine | Cost-effective, fast, good for experimentation phase | Validated Phase 1 — harness built, embeddings confirmed; Phase 6 migrated to litellm for provider-agnostic calls |
| litellm as LLM abstraction layer | Provider-agnostic API, per-run cost tracking, OpenAI-format tool calling | Validated Phase 6 — zero google-genai imports, cost tracking via completion_cost() |
| LLM-defined graph schema | Avoids baking in assumptions about what questions will be asked; becomes more powerful as models improve | Validated Phase 2 — Node.name/Edge.label are free strings, no hardcoded types in prompt |
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
*Last updated: 2026-03-27 after Phase 7 (agent tool capability gaps) completion*
