# Project Research Summary

**Project:** Arakne
**Domain:** AI-powered voice journaling with 3-layer semantic graph memory backend
**Researched:** 2026-04-01
**Confidence:** HIGH for backend architecture and stack; MEDIUM for prompt and operational details

## Executive Summary

Arakne is an AI voice journaling system with a genuinely novel technical architecture: a 3-layer memory system where the canonical record (raw transcripts with segment-level timestamps) feeds a derived semantic graph (FalkorDB nodes and edges) which in turn feeds a derived orientation map (themes). Source audio is retained for audit, but the transcript remains canonical. The defining design insight is that the graph and themes are caches — they can be fully rebuilt from transcripts — which means the system is inspectable and recoverable.

The recommended approach is to build the backend pipeline in strict dependency order: storage schema and graph tooling first, then the shared agent harness, then the three agent modes (ingestion, theme, query), then transcription, and finally thin script entry points. The backend is Python with a custom tool-calling loop — no agent framework is needed.

The most serious risks are behavioral rather than architectural: node proliferation, summary drift, provenance corruption, and low-quality prompt behavior. Those failures degrade the "your own words" guarantee that is the product's core differentiator. They must be handled through harness-enforced invariants, careful prompt iteration, and operational checks.

---

## Key Findings

### Recommended Stack

The stack is largely settled by prior implementation work and the current workspace dependencies.

- `falkordb` 1.6.0: graph store with native vector index support
- `litellm` 1.82.4: unified LLM / embedding / transcription interface
- `gemini-embedding-001`: 3072-dimensional embedding model for semantic search
- `groq/whisper-large-v3-turbo`: transcription model for audio → transcript
- `pydantic` 2.12.5: tool schema and data model validation
- `tiktoken` 0.12.0: real token counting for log compression thresholds

One non-obvious FalkorDB quirk was production-validated: updating a vector property requires `REMOVE n.embedding` before `SET n.embedding = vecf32(...)` or the index can retain stale values.

A live workspace check against `private/shania/shania_audio_diary/2021-01-01T00-00-00 01 - This diary belongs to.....mp3` confirmed that Groq's OpenAI-compatible API currently returns both a populated `segments[]` array and a populated `words[]` array for `whisper-large-v3-turbo`. Even so, Arakne should standardize on segment-level timestamps for transcript rendering and provenance because word-level granularity is unnecessary for the current architecture.

### Expected Features In Scope

Must-have backend capabilities for the current scope:

- Local audio-file ingestion via Python scripts
- Whisper transcription with segment-level timestamps
- Ingestion agent that builds the semantic graph from transcripts
- Theme agent that maintains the hot/cold orientation map asynchronously
- Natural-language query with citations grounded in transcript spans
- Hybrid keyword + semantic search
- Privacy and user-controlled storage boundaries

The current main plan should stay strictly backend-first and avoid adding extra product surfaces.

### Architecture Approach

The architecture is a layered monolith with strict component boundaries.

1. **Agent Harness** — shared tool-calling loop with provenance validation, token minting, and termination detection.
2. **Tool Layer** — pure Python functions over FalkorDB and transcript storage.
3. **Storage Layer** — FalkorDB queries, transcript store, and cold storage for archived log entries.
4. **Background Jobs** — theme agent runs and log compression after ingestion.
5. **Script Entry Points** — thin wrappers like `ingest_audio.py`, `ingest_transcript.py`, `query_memory.py`, and `inspect_graph.py`.

Key architectural patterns:

- Harness-owned invariants: provenance validation and token minting happen at dispatch, not in tool functions.
- Termination via special tool call: `complete_ingestion()` doubles as audit log and background-job trigger.
- Progressive disclosure: search → neighborhood → full node → archive.
- Hot/cold orientation map: themes keep the agent from starting blind.

### Critical Pitfalls

The most consequential risks are:

1. **Node proliferation** — duplicate semantic nodes accumulate when ingestion creates instead of merging.
2. **Provenance gap** — writes carry wrong or fabricated offsets, breaking the citation chain.
3. **Agentic loop runaway** — ingestion burns tool budget without terminating cleanly.
4. **FalkorDB serialization drift** — arrays / log entries round-trip incorrectly if storage format is not nailed down early.
5. **Whisper hallucination on silence/noise** — bad transcript segments become bad graph facts.

---

## Implementation Focus

The active build plan should stay inside the current v1 backend scope:

1. **Phase 1: Backend Foundation** — deliver FalkorDB schema, transcript store, cold storage, token registry, vector index initialization, tool functions, and harness invariants with round-trip and live integration coverage.
2. **Phase 2: Agent Pipeline** — deliver ingestion, theme, and query behavior on top of that foundation, including prompt iteration, transcript-grounded answers, and log compression.
3. **Phase 3: Transcription Pipeline** — deliver the Groq Whisper script path that extracts recording timestamps, renders segment-level transcript markers, and runs end-to-end into ingestion.

Ordering remains strict: storage before tools, tools before harness, harness before agents, and transcription/scripts after the graph-backed memory system is already working from transcript fixtures.

---

## Confidence Assessment

| Area         | Confidence | Notes                                                                                                                                             |
| ------------ | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Stack        | HIGH       | Locked dependencies and live workspace evidence validate the core backend stack.                                                                  |
| Features     | MEDIUM     | Core v1 scope is clear, but prompt quality and operational behavior still need validation against real transcripts.                               |
| Architecture | HIGH       | Primary source is `Memory-v5.md`; current planning now aligns with backend-only scope.                                                           |
| Pitfalls     | HIGH/MED   | Core failure modes are architecture-derived; some ecosystem details still need implementation-time validation.                                    |

### Gaps to Address

- **Ingestion prompt quality:** prior prompts exist historically but need iteration against the current provenance rules.
- **Theme hot-set policy:** `Memory-v5.md` defines the concept, but the editorial rule for what stays hot still needs explicit design.
- **Cold-start query behavior:** the system must respond well when the graph is empty.
- **FalkorDB AOF durability policy:** personal data durability deserves explicit testing, not assumptions.

---

## Sources

### Primary

- `/home/shivang/shivang/projs/arakne/markdowns/Memory-v5.md`
- `/home/shivang/shivang/projs/arakne/markdowns/planning/PROJECT.md`
- `/home/shivang/shivang/projs/arakne/pyproject.toml`
- `/home/shivang/shivang/projs/arakne/uv.lock`
- Historical project code referenced in git history for FalkorDB and embedding behavior
- Live workspace Groq transcription experiment on `private/shania/shania_audio_diary/2021-01-01T00-00-00 01 - This diary belongs to.....mp3`

### Secondary

- Training data on competitor products through Aug 2025
- Training data on LangGraph / LangChain tradeoffs
- Training data on Whisper hallucination behavior and graph-maintenance pitfalls
