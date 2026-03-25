# Project Research Summary

**Project:** LifeOS
**Domain:** LLM-powered audio journaling personal memory system (backend)
**Researched:** 2026-03-25
**Confidence:** HIGH (stack verified against existing pyproject.toml; architecture HIGH; pitfalls HIGH; features MEDIUM)

## Executive Summary

LifeOS is a personal memory backend that converts audio journal entries into a queryable knowledge graph. The recommended approach treats the system as three memory layers: raw transcripts (Layer 1), a schema-free semantic graph (Layer 2), and a derived theme map (Layer 3). All three layers live in FalkorDB, which provides both native graph storage (Cypher queries) and native vector indexing — eliminating the need for a separate vector database. Gemini 2.5 Flash drives both reasoning and embedding generation via the `google-genai` SDK, while Groq Whisper handles transcription via `litellm`. The entire agent harness is a lightweight agentic loop (~50 lines of Python) using native function calling — no LangChain or agent framework needed.

The core differentiator is the LLM-defined schema: unlike mem0 or Zep, LifeOS lets the language model invent entity types that match the person's inner life, not a predefined taxonomy. This power requires a strong disambiguation gate — without it, the graph degrades into a tangle of near-duplicate nodes within a few sessions. The second-order differentiator is append-only node logs with token-budgeted compression, which preserves the arc of how thinking evolved rather than just current state. These two features (disambiguation + log compression) are the hardest and most critical pieces of the system, and both must ship in Phase 2 alongside initial graph writes.

The primary risks are entity proliferation (duplicate nodes), schema type drift, and log overflow — all of which are Phase 2 concerns that must be addressed from day one of graph writing, not patched later. Infrastructure risks (FalkorDB full scans without explicit indexes, stale embeddings after node updates) must be addressed in Phase 1 via atomic update functions and explicit index creation at setup. RAGAS evaluation scores can be misleading if the eval suite doesn't include temporal/evolution queries; hand-crafting 10-15 "how has X changed?" queries is essential alongside standard RAGAS metrics.

---

## Key Findings

### Recommended Stack

The stack is already in place — `falkordb`, `google-genai`, `litellm`, `ragas`, and `pydantic` are all installed and locked in `pyproject.toml`. No additional stack decisions are needed. FalkorDB's native vector index support means the architecture can run hybrid vector+graph queries in a single Cypher statement, making a separate vector database redundant. The `google-genai` 1.x SDK's native function calling (`types.Tool` + `types.FunctionDeclaration`) supports the agentic loop directly — avoid building on LangChain/LangGraph even though they appear as transitive RAGAS dependencies.

**Core technologies:**
- **FalkorDB 1.6.0:** Graph + vector storage — hybrid queries in single Cypher statement, Redis-compatible protocol
- **google-genai 1.68.0:** LLM reasoning + embeddings — Gemini 2.5 Flash, native function calling, single client for all roles
- **litellm 1.82.4:** Groq Whisper transcription — unified API wrapper for audio-to-text
- **ragas 0.4.3:** Query quality evaluation — faithfulness, relevance, groundedness scoring (requires manual Gemini config)
- **pydantic 2.12.5:** Data models — type-safe node, edge, and transcript models

**Do not use:** ChromaDB, Chonkie, LangChain/LangGraph for agent logic, SpaCy/fixed NER pipelines.

### Expected Features

The MVP must close the full memory loop: ingest an audio file, build a queryable graph, and answer questions about it with source citations. Node disambiguation is the hardest single piece — it must be a three-tier gate (exact alias match → fuzzy similarity → LLM reasoning) active from the first graph write.

**Must have (table stakes — P1):**
- Transcript ingestion (audio → Groq Whisper → stored text + timestamps)
- Semantic graph write with LLM-defined node/edge types (no hardcoded schema)
- Node disambiguation (alias dedup + fuzzy + LLM fallback gate)
- Episode span tracking on all graph writes (required for grounded retrieval)
- Append-only node/edge logs (required for temporal reasoning)
- Graph read/search tools (parameterized Cypher)
- Vector search across node summaries and episode summaries
- Basic query agent (agent-decides-strategy, not fixed pipeline)

**Should have (differentiators — P2, add after core validation):**
- Log compression with token budgeting (trigger when node logs exceed ~4K tokens)
- Theme layer with heat/salience scoring (requires populated graph)
- Memo agent with observer-voice prompt (requires theme layer)
- Hybrid vector+graph retrieval (add when pure retrieval shows clear gaps)
- RAGAS evaluation harness with temporal query suite

**Defer to v2+:**
- Incremental graph repair (retroactive duplicate merging)
- Temporal query support ("what was I thinking 3 months ago?")
- Cross-session theme drift detection
- REST/GraphQL API, multi-user support, real-time streaming

### Architecture Approach

The system is structured as experiment scripts → agent harness → tool router → memory layers → core infrastructure. Each experiment script (ingest.py, query.py, memo.py, eval.py) is a manual entry point that calls the agent harness with a role-specific system prompt. The harness owns the agentic loop, prompt construction, and tool dispatch budget. Memory layers (transcripts, graph, themes, vectors) are separate Python modules with clear ownership of their storage operations. All infrastructure routes through a shared LLM client and FalkorDB instance.

**Major components:**
1. **Agent Harness** (`agent/harness.py`) — agentic loop with hard tool-call budget; owns prompt construction and role dispatch
2. **Graph Store** (`memory/graph.py`) — all FalkorDB Cypher operations, disambiguation logic, node/edge logs
3. **Vector Store** (`memory/vectors.py`) — shared embedding storage and similarity search across all memory layers
4. **Transcript Store** (`memory/transcripts.py`) — raw transcript CRUD with episode span indexing
5. **Theme Store** (`memory/themes.py`) — theme CRUD, heat/salience management, theme embeddings
6. **LLM Client** (`core/llm.py`) — single Gemini client for reasoning + embeddings, shared across all roles

### Critical Pitfalls

1. **Entity proliferation (duplicate nodes)** — Three-tier disambiguation gate (alias → fuzzy → LLM) must be active from first graph write in Phase 2; it cannot be added retroactively without graph repair work.
2. **Schema type drift** — Inject a vocabulary registry of existing node/edge types into every ingestion prompt. LLM must prefer existing types and only create new ones when genuinely justified.
3. **FalkorDB full scans** — Create explicit indexes at initialization (`CREATE INDEX` on `name`, `aliases`, `type`, `transcript_id`). FalkorDB has no auto-indexing. Address in Phase 1 setup scripts.
4. **Stale embeddings** — Never expose separate "update summary" and "update embedding" operations. A single `update_node` function must re-embed atomically. Address in Phase 1 storage layer.
5. **Agentic loop without termination** — Hard tool-call budget (e.g., max 8 calls per query) must be enforced in harness code, not just prompts. Address in Phase 1 when the harness is built.
6. **Log overflow** — Token-budgeted compression must be co-located with log writing in Phase 2, not added later. Check token count after every log write and compress when over budget.
7. **RAGAS false confidence** — Standard RAGAS scores don't cover temporal/evolution queries. Build a hand-crafted suite of 10-15 "how has X changed?" queries as the primary eval signal.

---

## Implications for Roadmap

Based on the dependency graph and pitfall-to-phase mapping from research, five phases are recommended. The order is hard-constrained: you cannot query without ingested data, cannot extract themes without a populated graph, and cannot evaluate without working queries.

### Phase 1: Core Infrastructure + Storage Layer
**Rationale:** Every other phase depends on FalkorDB being correctly initialized, the LLM client being available, and storage functions being atomic. Infrastructure bugs discovered late are expensive.
**Delivers:** FalkorDB with explicit indexes, atomic node update functions (re-embed on every summary change), agent harness with hard tool-call budget, Groq Whisper transcription, `.env` config loading.
**Features from FEATURES.md:** Append-only log structure (not compression yet, just the log schema); episode span schema; FalkorDB index setup.
**Pitfalls addressed:** FalkorDB full scans (indexes at init), stale embeddings (atomic update functions), agentic loop termination (budget in harness code).
**Research flag:** Standard patterns — skip deeper research. FalkorDB Cypher and google-genai function calling are well-documented.

### Phase 2: Ingestion Agent + Graph Writing
**Rationale:** The memory loop starts here. This phase is the highest implementation risk — disambiguation and schema consistency must ship with graph writes from day one.
**Delivers:** Full ingestion pipeline (audio → transcript → graph nodes/edges → episode spans → embeddings), three-tier node disambiguation, vocabulary registry injection into ingestion prompt, log compression.
**Features from FEATURES.md:** Transcript ingestion, semantic graph write (schema-free), node disambiguation, episode span tracking, append-only logs, log compression.
**Pitfalls addressed:** Entity proliferation (disambiguation gate), schema type drift (vocabulary registry in prompt), log overflow (compression co-located with writes).
**Research flag:** Needs deeper research during planning. Disambiguation strategy (fuzzy threshold tuning, LLM fallback prompt design) and vocabulary registry design have nuances worth prototyping before committing to an interface.

### Phase 3: Query Agent + Retrieval
**Rationale:** With ingested data available, the query agent can be built and validated against real graph content. Vector search is introduced here because query retrieval requires it.
**Delivers:** Vector store (node + episode embeddings), query agent with agentic retrieval strategy, graph read/search tools (Cypher), transcript-grounded answer synthesis with citation.
**Features from FEATURES.md:** Graph read/search, vector search, basic query agent (agent-decides-strategy).
**Architecture components:** Vector Store, Query Role prompt, retrieval tools in Tool Router.
**Research flag:** Standard patterns for vector search setup. The agent prompt design for agentic retrieval may benefit from a short research spike on mem0/Zep query agent patterns.

### Phase 4: Theme Layer + Memo Agent
**Rationale:** Themes are derived from a populated graph — this phase cannot start until Phase 2 has produced sufficient graph data. The memo agent requires the theme layer to exist.
**Delivers:** Theme store (heat/salience, theme embeddings), memo agent (observer-voice prompt, periodic pattern detection), hybrid vector+graph retrieval seeded by theme map.
**Features from FEATURES.md:** Theme layer with heat/salience scoring, memo agent, hybrid vector+graph retrieval, theme-as-navigation-map for query agent.
**Pitfalls addressed:** Separate theme database anti-pattern — themes as special nodes or thin reference layer within FalkorDB, not a separate system.
**Research flag:** Needs deeper research during planning. Heat/salience decay functions, theme merging strategy, and memo agent prompt design are novel enough to warrant a planning research spike.

### Phase 5: Evaluation Harness
**Rationale:** Evaluation requires working queries and populated graph. Cannot evaluate what doesn't exist yet.
**Delivers:** RAGAS evaluation runner configured for Gemini (not OpenAI default), test transcript dataset, hand-crafted temporal/evolution query suite (10-15 queries), baseline quality scores.
**Features from FEATURES.md:** RAGAS evaluation harness, transcript-grounded retrieval verification.
**Pitfalls addressed:** RAGAS false confidence — temporal query suite is the primary signal, RAGAS is secondary.
**Research flag:** RAGAS 0.4.x Gemini configuration is non-obvious (requires manual LLM config override). Worth a quick research spike before implementation.

### Phase Ordering Rationale

- Phase 1 before everything: all other phases depend on stable infrastructure and atomic storage operations
- Phase 2 before Phase 3: cannot query without ingested data; disambiguation must be correct before the graph grows
- Phase 3 before Phase 4: theme layer needs a populated, clean graph — built and validated by Phase 3 queries
- Phase 4 before Phase 5: evaluation is most meaningful when the full system (including themes) is operational
- Compression in Phase 2 (not deferred): log overflow is a Phase 2 risk that gets harder to fix as the graph grows

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2:** Disambiguation strategy — fuzzy threshold values, LLM fallback prompt design, vocabulary registry schema. High implementation risk, worth prototyping.
- **Phase 4:** Theme layer design — heat/salience decay functions, theme merging, memo agent prompt. Novel enough to need a planning spike.
- **Phase 5:** RAGAS 0.4.x Gemini configuration — non-default setup, verify against RAGAS docs before implementing.

Phases with standard patterns (skip research-phase):
- **Phase 1:** FalkorDB init, google-genai client setup, devenv config — well-documented, existing patterns.
- **Phase 3:** Vector search setup and basic Cypher query tools — established patterns, existing codebase has FalkorDB experiments to reference.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Verified against existing `pyproject.toml` + `uv.lock`; all packages already installed |
| Features | MEDIUM | Based on training knowledge of mem0, Zep, cognee, MemGPT (August 2025 cutoff); no live competitor research available |
| Architecture | HIGH | Derived directly from PROJECT.md design philosophy + existing experiment code in the repo |
| Pitfalls | HIGH | Grounded in known failure modes of LLM graph systems and FalkorDB-specific behavior |

**Overall confidence:** HIGH

### Gaps to Address

- **FalkorDB vector index version:** The `latest` Docker tag was used — confirm the pulled image version has vector index support before Phase 1 closes.
- **google-genai 1.x tool definition format:** The legacy dict format does not work in 1.x; verify all tool definitions use `types.Tool` + `types.FunctionDeclaration`. Check during Phase 1.
- **RAGAS Gemini config:** RAGAS 0.4.x defaults to OpenAI. Requires manual LLM config override to use Gemini. Verify the exact config pattern before Phase 5.
- **Disambiguation threshold tuning:** Fuzzy similarity threshold for the second disambiguation tier (before LLM fallback) needs empirical calibration. Plan a short tuning experiment in Phase 2.
- **Feature confidence:** Competitor feature analysis was based on training knowledge only (no live research). The differentiator claims (especially vs. Zep/Graphiti) should be spot-checked during Phase 4 when the theme layer is built.

---

## Sources

### Primary (HIGH confidence)
- `PROJECT.md` (LifeOS repo) — design philosophy, memory layer design, scope constraints
- `pyproject.toml` + `uv.lock` (LifeOS repo) — verified stack versions
- `devenv.nix` (LifeOS repo) — FalkorDB Docker environment definition
- Existing experiment code in repo — confirmed FalkorDB connection patterns

### Secondary (MEDIUM confidence)
- Training knowledge of mem0, Zep/Graphiti, cognee, MemGPT architectures — competitor feature analysis, memory layer patterns
- Training knowledge of RAGAS 0.4.x evaluation framework — evaluation setup patterns
- Training knowledge of FalkorDB behavior — index requirements, full scan risks

### Tertiary (LOW confidence)
- Competitor feature claims — not verified against live docs; treat differentiator analysis as directional, not definitive

---
*Research completed: 2026-03-25*
*Ready for roadmap: yes*
