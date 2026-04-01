# Project Research Summary

**Project:** Arachne
**Domain:** AI-powered voice journaling with 3-layer semantic graph memory backend
**Researched:** 2026-04-01
**Confidence:** HIGH (stack and architecture fully validated against production-tested prior codebase in git history; features and pitfalls at MEDIUM from training data and architecture derivation)

## Executive Summary

Arachne is an AI voice journaling app with a genuinely novel technical architecture: a 3-layer memory system where the canonical record (raw transcripts with sentence-level timestamps) feeds a derived semantic graph (FalkorDB nodes and edges) which in turn feeds a derived orientation map (themes). The defining design insight is that the graph and themes are caches — they can be fully rebuilt from transcripts — which means the system is both inspectable and recoverable. No competitor combines voice-first capture, automatic relationship inference, and cited answers grounded in the user's exact words. The gap in the market is real; the technical challenge is proportionally significant.

The recommended approach is to build the backend pipeline in strict dependency order: storage schema and graph tooling first, then the shared agent harness, then each of the three agent modes (ingestion, theme, query) with their system prompts, then transcription, and finally the mobile client and API surface. The entire backend is Python with a custom tool-calling loop — no agent framework (LangGraph, LangChain) is needed or recommended. The stack is already decided and partially validated: FalkorDB 1.6.0 for the graph, litellm 1.82.4 as the unified LLM/embedding interface, Groq Whisper for transcription, Gemini embedding-001 for 3072-dimensional semantic embeddings, and React Native + Expo for the mobile client.

The most serious risks are not architectural but behavioral: the LLM-driven graph degrades if the ingestion agent creates duplicate nodes instead of merging (node proliferation), drifts node summaries toward blandness over time (summary drift), or writes provenance offsets that don't point to the text that justified the write (provenance gap). All three corrupt the "your own words" guarantee that is the product's core differentiator. These are prevented through harness-enforced invariants, disciplined prompt engineering, and post-ingestion health metrics — not through architectural changes. They must be addressed at ingestion phase, not retroactively.

---

## Key Findings

### Recommended Stack

The stack is largely settled by a prior working implementation (recoverable from git history through commit `e74f691`). FalkorDB 1.6.0 is the graph store with native vector index support (eliminating any need for a separate vector DB). litellm 1.82.4 provides a single interface across Gemini, OpenAI, and Groq, enabling provider swaps via environment variables. The transcription pipeline uses Groq's Whisper inference at ~200x realtime; critically, `whisper-large-v3-turbo` does not return word-level timestamps despite accepting the parameter — the architecture is correctly designed around segment-level boundaries. The mobile frontend is React Native + Expo (SDK ~53); the backend API needs FastAPI added as a direct dependency (not yet in `pyproject.toml`).

One non-obvious FalkorDB quirk was production-validated: updating a vector property requires `REMOVE n.embedding` before `SET n.embedding = vecf32(...)` — direct overwrite silently leaves the old vector in the index. This is already in the prior codebase and must be carried forward.

**Core technologies:**
- `falkordb` 1.6.0: Graph DB with native vector index — eliminates dual-write synchronization problem of external vector DBs; `vecf32()` property type for embedding storage; REMOVE-before-SET required for vector updates
- `litellm` 1.82.4: Unified LLM + embedding interface — single call across all providers; handles `task_type` for Gemini embedding distinction between RETRIEVAL_DOCUMENT and RETRIEVAL_QUERY
- `gemini-embedding-001`: 3072-dimensional embeddings — matches the vector index already specified; requires `task_type` parameter; cannot swap providers without rebuilding the index
- `groq/whisper-large-v3-turbo`: Transcription at ~200x realtime — returns segment-level timestamps; word-level timestamps are silently null and must not be relied upon
- `pydantic` 2.12.5: Data models and tool call schema validation — V2 required; `model_dump(mode="json")` for serialization to FalkorDB string properties
- `tiktoken` 0.12.0: Token budget counting — used for log compression trigger; must be the actual tokenizer, never approximations like whitespace splitting
- `FastAPI` (not yet in pyproject): Backend HTTP API — async-native; handles multipart audio upload and streaming SSE for query responses; add via `uv add "fastapi>=0.120" "uvicorn[standard]" "python-multipart"`
- `React Native + Expo SDK ~53`: Mobile client — `expo-av` for audio recording to M4A; background recording permission required for the core use case of recording while commuting/walking

### Expected Features

The feature landscape is unusually clear because no competitor covers the full combination: voice-first + auto semantic graph + cited answers. Each individual capability exists in isolation elsewhere (Rewind for passive capture, Reflect for backlink graphs, Mem for AI search) but nobody combines them.

**Must have (table stakes):**
- One-tap voice recording from mobile — primary capture surface; all downstream value is gated on this
- Whisper transcription with sentence-level timestamps — canonical record; every downstream feature depends on it
- Chronological entry list with transcript view — trust signal; users need to see recordings were captured
- Hybrid keyword + semantic search — fallback navigation for users who can't form a natural language query
- Privacy / local data control — prerequisite for user trust with intimate personal content

**Should have (competitive differentiators — all P1 for MVP):**
- Ingestion agent that builds semantic graph from transcripts — the core intelligence; without this Arachne is just a voice memo app
- Theme agent (async, background) — orientation layer; query agent cold-starts blind without themes
- Natural language query with cited answers (exact transcript spans) — the "aha" moment; validates the core value prop; no competitor does this with provenance to the second
- Pattern surfacing across time — "you've returned to this 7 times since January" — emerges from sustained use; v1.x

**Defer (v2+):**
- Android support (iOS first for quality control)
- Export to markdown / Obsidian
- Multi-language transcription
- Memo mode (observer agent)
- Bi-temporal graph versioning (Graphiti arxiv 2501.13956)
- Calendar integration / event logging (explicitly out of scope — inner life, not external events)

**Explicit anti-features (never build):**
- Streaks, gamification, guilt mechanics
- Social / sharing features
- Real-time streaming transcription (batch is sufficient)
- Clinical / diagnostic features
- Rigid note structure (folders, tags, hierarchies)

### Architecture Approach

The architecture is a layered monolith with strict component boundaries. The core is a single Python tool-calling loop (~30 lines) that serves three agent modes by swapping system prompts — not three separate runtimes. The loop is the entire differentiating logic: it manages the message array, intercepts write calls for provenance validation and token minting before storage is touched, and detects the `complete_ingestion()` termination signal that seeds background jobs. This loop is not a framework; LangGraph and LangChain both add abstraction that conflicts with the harness's need to own provenance validation and token minting at dispatch time.

**Major components:**
1. **Agent Harness** (`src/harness/`) — the shared tool-calling loop; owns provenance validation, sequential token minting, and termination detection; shared across ingestion, query, and theme modes via system prompt swap; ~80 lines total; most testable component in isolation
2. **Tool Layer** (`src/tools/`) — pure Python functions over FalkorDB and transcript store; independently testable; harness never writes Cypher directly; tiered read tools (search → neighborhood → full node → archive) preserve context budget
3. **Storage Layer** (`src/storage/`) — FalkorDB client and all Cypher queries isolated here; transcript store (append-only canonical text); cold storage for pre-compression log entry archives; nothing outside this module writes Cypher
4. **Background Jobs** (`src/jobs/`) — theme agent and log compression run async after ingestion; serialized (no parallel theme runs); user never waits on them; theme job is another harness call with a different system prompt, not special code
5. **Backend API** (`src/api/`) — FastAPI routes for `/record` and `/query`; does not contain agent logic; delegates immediately to harness; handles multipart audio upload and streaming SSE
6. **Mobile Client** (separate Expo app) — voice recording with one-tap start; waveform feedback during recording; fire-and-forget feel after stop; entry list with first-sentence transcript previews

**Key architectural patterns:**
- Harness-owned invariants: provenance validation and token minting happen at dispatch, not in tool functions or LLM output
- Termination via special tool call: `complete_ingestion()` is both audit log and background job trigger
- Progressive disclosure: tiered read tools (Tier 1 hot themes → Tier 2 search → Tier 3 neighborhood → Tier 4 full node → Archive) preserve token budget for reasoning
- Hot/cold orientation map: k themes rendered in full at session start; cold index provides names of remainder; agent never starts blind

### Critical Pitfalls

Ten pitfalls were identified; the following five are the most consequential and must be prevented before they occur — retroactive repair is expensive or impossible for all of them.

1. **Node proliferation** — the graph accumulates semantic duplicates ("career anxiety", "work stress", "job pressure" as five separate nodes) because the ingestion agent creates rather than merges when search doesn't surface existing nodes. Prevention: enforce search-before-create discipline in the ingestion prompt; include current node count in context; build a create:update ratio health metric; ensure `search_graph` matches aliases and partial forms, not just embeddings.

2. **Provenance gap** — writes execute with fabricated or reused offsets that don't point to the text that justified the write, silently corrupting the citation chain. Prevention: harness must reject writes with null, out-of-bounds, or equal start/end offsets; additionally verify that `get_transcript_span(transcript_id, start, end)` returns non-empty text before accepting a write; enforce offset diversity (clustering on same offsets is a signal of fabrication).

3. **Agentic loop runaway** — the ingestion agent enters an infinite disambiguation loop on ambiguous transcripts (same concept referred to by multiple surface forms), burns the token budget without calling `complete_ingestion`, and leaves the transcript partially ingested with the bidirectional index unpopulated. Prevention: hard tool call budget (e.g., 60 calls) and wall-clock timeout (2-3 minutes) in the harness from day one; explicit disambiguation decision rule in the prompt; idempotent write detection.

4. **FalkorDB array field serialization** — log entries stored as complex nested structures in array properties may round-trip incorrectly (double-serialized as JSON strings inside arrays), causing silent data corruption that's invisible until query time. Prevention: decide at schema design time whether log entries are JSON strings or separate nodes, document it, and validate round-trip serialization in the first integration test before any agent code is written.

5. **Whisper hallucination on silence and noise** — Whisper generates plausible-sounding text for silence, background noise, and filler audio, which enters the ingestion pipeline as real statements and ends up in the graph as nodes with provenance pointing to silence spans. Prevention: confidence-filter segments before ingestion; strip meta-tokens (`[MUSIC]`, `[APPLAUSE]`); enforce minimum recording and non-silence durations.

---

## Implications for Roadmap

Based on the architecture's hard dependency chain and the pitfall landscape, a 6-phase build order is strongly indicated. Each phase has a clear deliverable that the next phase depends on.

### Phase 1: Graph Storage Foundation

**Rationale:** All other components write to or read from FalkorDB. The schema and data access layer must be established first. Array field serialization bugs (Pitfall 7) are cheapest to prevent here and catastrophically expensive to fix after agent code is written on top of bad schema decisions.

**Delivers:** FalkorDB schema (nodes, edges, themes, token registry, vector index, alias range index), transcript store, cold storage, and a data access layer (DAL) that abstracts all serialization. Round-trip tests for all array fields. Vector index creation in the DB init script (absence causes silent brute-force fallback).

**Addresses:** GRAPH-01 through GRAPH-04 (node/edge schema, bidirectional index, log compression schema, no type field)

**Avoids:** FalkorDB array serialization pitfall (Pitfall 7); vector index silent fallback; O(n) node lookups without alias index

**Research flags:** Standard patterns; no additional research needed. FalkorDB client specifics are fully documented in STACK.md from production-validated source code.

---

### Phase 2: Tool Layer

**Rationale:** Tools are pure functions over storage. They must exist and be independently tested before the harness can dispatch to them. This phase is also where hybrid search precision is validated — alias-match boosting (Pitfall 9) must be implemented before the query agent is built on top of a broken search surface.

**Delivers:** All 13 tool functions with correct schemas: `search_graph` (hybrid keyword + semantic with alias boost), `get_node_neighborhood`, `get_node`, `get_node_log_archive`, `list_transcripts`, `get_transcript_span`, `get_theme`, `create_node`, `update_node`, `create_edge`, `update_edge`, `delete_node`, `delete_edge`, `create_theme`, `update_theme`, `retire_theme`, `complete_ingestion`. Each tool independently tested against a live FalkorDB fixture.

**Addresses:** READ-01 through READ-07, WRITE-01, WRITE-02 (provenance validation happens at harness level in Phase 3, but tool contracts are defined here), THEME-06

**Avoids:** Hybrid search missing proper nouns (Pitfall 9) — keyword alias-match boosting implemented and tested with 50-node fixture including named people before query agent is built

**Research flags:** Standard patterns. The `db.idx.vector.queryNodes` syntax is verified in STACK.md from pre-reset production code.

---

### Phase 3: Agent Harness Core

**Rationale:** The harness is the most architecturally critical component. It owns the invariants that prevent the most expensive failure modes. Provenance validation (Pitfall 3) and token minting must be harness-enforced, not LLM-trusted. The tool call budget that prevents loop runaway (Pitfall 4) is a harness concern. This component must be correct and tested in isolation before any agent mode is wired up.

**Delivers:** The shared tool-calling loop (~80 lines): message array management, tool dispatch, provenance guard (reject writes without valid transcript_id + non-null non-equal in-bounds offsets + non-empty span text), sequential token minting via token registry in FalkorDB, termination detection on `complete_ingestion()`, tool call budget enforcement (configurable N, defaults to 60), wall-clock timeout with graceful `partial=true` termination, idempotent call detection (same tool+args 3x → inject termination).

**Addresses:** INGEST-04 (provenance on every write), INGEST-06 (harness mints tokens), INGEST-07 (complete_ingestion as termination), WRITE-02 (provenance validation)

**Avoids:** Provenance gap (Pitfall 3); agentic loop runaway (Pitfall 4)

**Research flags:** Standard patterns. The loop structure is documented in ARCHITECTURE.md with concrete pseudocode from Memory-v5.md.

---

### Phase 4: Ingestion Agent

**Rationale:** Ingestion is the write path — everything in the graph comes from here. The theme agent and query agent both depend on a correctly populated graph. This is also where node proliferation (Pitfall 1) and summary drift (Pitfall 2) are either prevented or not. The ingestion system prompt is as critical as the harness code.

**Delivers:** Ingestion system prompt (search-before-create discipline, disambiguation decision rule, provenance-quoting-before-write instruction, summary-rewrite constraint), end-to-end test (real transcript → graph writes → `complete_ingestion` → bidirectional index populated), health metric: create:update ratio per session, background job queue trigger wired to ingestion completion.

**Addresses:** INGEST-01 through INGEST-08, GRAPH-02 (bidirectional index populated by complete_ingestion payload)

**Avoids:** Node proliferation (Pitfall 1) through prompt design + search-before-create + health metric; summary drift (Pitfall 2) through prompt constraints on rewrite conditions

**Research flags:** Needs prompt engineering iteration. The prompt is not a one-shot design — expect 3-5 rounds of refinement against real transcripts before proliferation and drift are under control. Plan iteration budget in this phase.

---

### Phase 5: Theme and Query Agents + Log Compression

**Rationale:** Theme agent depends on a working ingestion path (it reads `touched_nodes` from `complete_ingestion`). Query agent requires a populated graph to return useful answers. Log compression is a non-agentic background job that can be built alongside theme agent since both are background jobs. This phase completes the full backend loop: speak → ingest → theme → query.

**Delivers:** Theme system prompt (delta-only operation on `touched_nodes`, hot-set selection with freshness rule, cold theme staleness metric), theme agent background job (serialized, async, triggered by ingestion completion), log compression job (non-agentic, single LLM call, real tokenizer via `tiktoken`, pre-compression cold storage write verified before inline entry replacement, arc summary prompt that preserves chronology and contradictions), query system prompt (progressive retrieval discipline, citation grounding requirement), end-to-end test: ingest 5 transcripts → themes emerge → ask question → get cited answer with exact transcript span quotes.

**Addresses:** THEME-01 through THEME-06, QUERY-01 through QUERY-04, GRAPH-03 (log compression), INGEST-08 (old summary archived before rewrite — enforced in update_node tool)

**Avoids:** Theme hot set going stale (Pitfall 6) through freshness rule in hot-set selection; log compression destroying the arc (Pitfall 5) through arc-aware prompt and cold storage verification; token counter drift (Pitfall 10) through real tokenizer

**Research flags:** Query system prompt needs iteration against real multi-session data. Cold-start experience (empty graph) needs UX design: what does the query agent say when there are 0 sessions? Set expectations in the system prompt response for this case.

---

### Phase 6: Transcription Pipeline, API, and Mobile Client

**Rationale:** The transcription pipeline (Whisper via Groq) and API surface come last because they are the input to the backend, not the backend itself. Building API before the backend is correct is a common mistake. The mobile client is last because it is a thin client that calls the API.

**Delivers:** Whisper integration with Groq (`groq/whisper-large-v3-turbo` via litellm), sentence-level timestamp rendering (segment `start`/`end` → `[MM:SS]` inline markers), confidence filtering (strip low-probability segments and meta-tokens like `[MUSIC]`), minimum duration gating (5 seconds non-silence), `rec:N` token minting on transcript write. FastAPI backend with `/record` (multipart audio upload → transcription → ingestion) and `/query` (text → query agent → cited answer) routes. React Native + Expo mobile app: one-tap record button, background audio permission, waveform feedback, fire-and-forget stop, processing indicator, chronological entry list with first-sentence transcript preview, query input with cited answer display.

**Addresses:** VOICE-01, VOICE-02; all API surface requirements; mobile UX patterns from FEATURES.md

**Avoids:** Whisper hallucination on silence (Pitfall 8) through confidence filtering and minimum duration gating; word-level timestamp dependency (silently null on `whisper-large-v3-turbo` — use segment boundaries only)

**Research flags:** Mobile background audio recording on iOS requires careful permission handling. Expo's `expo-av` with background mode needs `UIBackgroundModes: audio` in `app.json`. Verify current Expo SDK 53 API for this — the pattern is established but SDK versions affect exact configuration. May need a brief research spike before implementation.

---

### Phase Ordering Rationale

- Storage before tools, tools before harness, harness before agents: the architecture has an explicit hard dependency chain that cannot be shortcut without breaking test isolation. Each layer is independently testable only if the layer below it exists.
- Ingestion before query: the query agent has nothing to work with until ingestion has run. Building query before ingestion produces an empty-graph agent that can only validate loop behavior, not answer quality.
- Ingestion before theme: the theme agent is triggered by `complete_ingestion()`. End-to-end theme testing requires a working ingestion path.
- Theme and query in the same phase: once ingestion is solid, theme and query can be built in parallel. Both depend on a populated graph but not on each other.
- Transcription and mobile last: the API and mobile client are thin wrappers over the backend. Building them before the backend is correct creates integration work that reveals bugs that should have been caught in unit and integration tests.
- The biggest risk to this ordering is prompt engineering underestimation. The ingestion prompt (Phase 4) and query prompt (Phase 5) each require iteration against real data. Plan for this; don't treat prompts as one-shot deliverables.

### Research Flags

**Phases needing deeper research during planning:**
- **Phase 4 (Ingestion Agent):** Prompt engineering for search-before-create discipline and disambiguation is not a solved problem. Plan 3-5 iteration rounds. The pre-reset codebase has examples to start from (recoverable from git history) but those prompts have not been validated against the v5 architecture's stricter provenance requirements.
- **Phase 6 (Mobile):** Expo SDK 53 background audio recording on iOS — verify current `app.json` configuration for `UIBackgroundModes` and Expo's `Audio.setAudioModeAsync` API for background recording. The pattern is standard but SDK-version-specific.

**Phases with standard patterns (skip research-phase):**
- **Phase 1 (Storage):** FalkorDB schema and DAL patterns are fully documented in STACK.md from production-validated source code. No additional research needed.
- **Phase 2 (Tool Layer):** Pure Python functions over FalkorDB. All Cypher syntax verified. Standard Python patterns.
- **Phase 3 (Harness):** The loop structure is documented in ARCHITECTURE.md with concrete pseudocode. ~80 lines. No framework research needed.
- **Phase 5 (Theme/Query/Compression):** System prompt patterns are derivable from Memory-v5.md. The log compression job is non-agentic and mechanical.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All core dependencies locked in `uv.lock`; falkordb 1.6.0, litellm 1.82.4, pydantic 2.12.5 verified against installed package metadata; key quirks (REMOVE-before-SET for vector, `words: null` on turbo model) empirically validated from pre-reset production code and real transcript outputs |
| Features | MEDIUM | Competitor analysis from training data (cutoff Aug 2025); product decisions from authoritative project docs (Vision.md, PROJECT.md) which are HIGH confidence; feature priorities reflect project team's explicit design philosophy |
| Architecture | HIGH | Primary source is Memory-v5.md, the project's own authoritative architecture spec; build order and component boundaries confirmed by prior working implementation; LangGraph/LangChain dismissal is MEDIUM (training data, not live docs) but the conclusion is robust |
| Pitfalls | HIGH (architecture-derived) / MEDIUM (ecosystem) | Pitfalls 1-6 and 9-10 derived directly from Memory-v5.md ambiguities and known LLM behavior patterns — HIGH confidence. Pitfalls 7 (FalkorDB array serialization) and 8 (Whisper hallucination) are MEDIUM — based on Redis module behavior patterns and well-documented Whisper community reports |

**Overall confidence:** HIGH for backend architecture and stack; MEDIUM for feature prioritization and mobile implementation details.

### Gaps to Address

- **Ingestion prompt quality:** The prior codebase has ingestion prompts in git history but they were not validated against the v5 architecture's provenance requirements. Start from those prompts but plan explicit iteration. The create:update ratio health metric is the empirical signal.
- **Theme agent hot-set selection policy:** Memory-v5.md specifies the hot-set concept but the selection policy (what makes a theme hot) is editorial, not algorithmic. This requires a design decision before Phase 5 implementation. Suggested default: recency + depth score combination, with a freshness floor that forces re-evaluation of any theme not touched in 3+ sessions.
- **Cold-start user experience:** A new user with 0 sessions gets a query agent with nothing to retrieve. The messaging for this state needs explicit design — either in the system prompt (query agent gracefully handles empty graph) or in the mobile UX (onboarding flow sets expectations). Not an architectural gap but a UX gap that could affect early-user retention.
- **FalkorDB AOF persistence configuration:** The devenv.nix Docker image uses `appendonly yes` by default. Fast container kills can corrupt the AOF before rewrite completes. For personal data, evaluate `fsync=always` policy or volume mounting strategy during Phase 1.
- **FastAPI dependency:** Not yet in `pyproject.toml`. Add in Phase 6: `uv add "fastapi>=0.120" "uvicorn[standard]>=0.30" "python-multipart>=0.0.9"`.

---

## Sources

### Primary (HIGH confidence)
- `/home/shivang/shivang/projs/arachne/pyproject.toml` and `uv.lock` — locked dependency versions
- `/home/shivang/shivang/projs/arachne/markdowns/Memory-v5.md` — authoritative architecture spec (primary source for ARCHITECTURE.md and PITFALLS.md)
- `/home/shivang/shivang/projs/arachne/.planning/PROJECT.md` — product requirements and constraints
- `git show 0883904:lifeos/memory/graph.py` — pre-reset FalkorDB production layer; validated REMOVE-before-SET quirk and `vecf32` usage
- `git show 0883904:lifeos/core/embeddings.py` — validated litellm embedding calls with `task_type`
- `/home/shivang/shivang/projs/arachne/private/transcripts/*.json` — real Groq Whisper output; confirmed `words: null` on turbo model
- `falkordb-1.6.0.dist-info/METADATA` — installed package metadata; confirmed Python 3.10-3.14 support, MIT license, redis>=7.1 dep

### Secondary (MEDIUM confidence)
- Training data on competitor products (Day One, Reflect, Mem, Rewind, Obsidian, Roam, Notion AI) through Aug 2025 cutoff — feature analysis
- Training data on LangGraph and LangChain architecture — framework dismissal rationale
- Training data on FalkorDB array property behavior — Pitfall 7 basis
- Training data on Whisper hallucination patterns on sparse audio — Pitfall 8 basis
- Graphiti (arxiv 2501.13956) — referenced in Memory-v5.md for bi-temporal versioning context

### Tertiary (LOW confidence — needs validation during implementation)
- Expo SDK 53 background audio recording configuration on iOS — API may have changed; verify during Phase 6
- FalkorDB server AOF `fsync` policy options — verify against current Docker image documentation before Phase 1 storage decisions

---
*Research completed: 2026-04-01*
*Ready for roadmap: yes*
