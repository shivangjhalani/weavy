# Phase 2: Ingestion Agent - Context

**Gathered:** 2026-03-26
**Status:** Ready for planning

<domain>
## Phase Boundary

End-to-end audio-to-graph pipeline: transcribe an audio file, feed the full transcript to an LLM agent that builds/updates the semantic graph with disambiguation, episode spans, and log compression. No query logic, no theme layer, no evaluation — just ingestion.

</domain>

<decisions>
## Implementation Decisions

### Data Model Changes
- **D-01:** Drop `type` field from both Node and Edge models entirely. No types, no vocabulary registry (INGST-05 dropped). The Bitter Lesson: types are a categorization scheme imposed on data. The summary carries all semantic meaning.
- **D-02:** Node model: `id`, `name`, `summary`, `aliases`, `log`, `refs`, `embedding`. Keep an explicit `name` field as the canonical display label (separate from aliases list).
- **D-03:** Edge model: `id`, `source_id`, `target_id`, `label`, `summary`, `log`, `refs`, `embedding`. Rename `type` to `label` — a concise relationship descriptor ("father_of", "fears", "evolved_into"). Summary carries the full description.
- **D-04:** Create a Transcript Pydantic model with: `id`, `recorded_at` (datetime), `text` (str), `segments` (from Whisper verbose_json), `episode_spans` (list, added post-ingestion). Formalizes the record, consistent with Node/Edge models.

### Agent Tool Design
- **D-05:** Fine-grained individual tools: `search_nodes_by_alias`, `search_nodes_by_embedding`, `create_node`, `update_node`, `delete_node`, `create_edge`, `update_edge`, `delete_edge`, `create_episode_spans`. Agent decides exactly which operations to perform per transcript.
- **D-06:** No dedicated merge tool — agent composes merges from primitives (update one node's aliases/summary, re-point edges, delete the other).
- **D-07:** Delete tools included for both nodes and edges. Agent can remove graph state it judges wrong or redundant.
- **D-08:** Remove tool-call budget enforcement entirely. Let the agent call as many tools as it needs. Budgets can be reintroduced later if costs become a concern.
- **D-09:** Graph awareness via search tools only — no upfront graph snapshot injected into the system prompt. Agent discovers existing graph state by searching.

### Disambiguation
- **D-10:** Fully agent-driven disambiguation. The 3-tier flow (exact alias match -> embedding similarity -> LLM reasoning) is emergent from the agent's tool-calling behavior, guided by the system prompt. No code-driven gates.
- **D-11:** Fuzzy matching uses embedding similarity (vector search on node summaries, already built in graph.py). Not string distance.
- **D-12:** Search tools return candidates with similarity scores. Agent sees scores and makes all merge/create decisions itself.

### Episode Spans
- **D-13:** Episode spans stored in transcript JSON on disk (alongside raw text in TranscriptStore). Not in FalkorDB as separate nodes.
- **D-14:** Episode spans created after all graph writes complete. The agent first reads the transcript and builds/updates the full graph, then identifies coherent topic spans as a final step.

### Log Compression
- **D-15:** Post-ingestion compression pass — after the agent finishes all graph writes, Python code identifies over-budget logs and compresses them.
- **D-16:** Compression done by a separate standalone Gemini LLM call with a compression-specific prompt. Not the ingestion agent loop. No tools, just input log -> output compressed log.
- **D-17:** Token-count threshold triggers compression. Needs a token counting utility.

### Ingestion Prompt
- **D-18:** Minimal guardrails prompt — describe the graph structure (nodes with name/summary/log/aliases/refs, edges with label/summary/log/refs), list available tools, state the goal ("build a semantic graph of this person's inner life"). Let the LLM figure out the rest.
- **D-19:** Explicitly state selectivity (INGST-04): "Not everything is worth persisting. Use your judgment — only create or update nodes for things that matter to this person's evolving inner life."
- **D-20:** Recording timestamp passed in the user message: "Recording from [date]:\n\n[transcript text]". Agent sees it naturally alongside the content.

### Transcript Source
- **D-21:** Recording timestamp read from audio file metadata (filesystem creation/modification time). Falls back to current time if metadata missing.

### Ingest Script UX
- **D-22:** `ingest.py` accepts a single audio file path as argument. One file per run. Batch processing via shell loop.
- **D-23:** On completion, print a summary of changes: transcript ID, nodes created/updated/merged count, edges created/updated count, episode spans count.

### Claude's Discretion
- Token threshold value for log compression (research to determine a good starting point)
- Exact set of FalkorDB index changes needed after dropping type field
- Whether to use async or sync for the agent loop and compression pass
- Episode span embedding approach (embed the span summary for future retrieval)
- How to count tokens for compression threshold (tiktoken, simple word estimate, or Gemini tokenizer)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Memory Architecture
- `markdowns/Memory-v3.md` — Defines the three-layer memory architecture, node/edge structure, disambiguation approach, log compression, episode span design. Primary design document.
- `markdowns/Vision.md` — Product vision, user personas, anti-goals. Defines what LifeOS is NOT.

### Existing Code (Phase 1 output)
- `lifeos/memory/models.py` — Current Node, Edge, LogEntry, TranscriptRef Pydantic models (need type field removal + name/label additions)
- `lifeos/memory/graph.py` — FalkorDB init, atomic CRUD, vector search (need type field removal, index updates)
- `lifeos/memory/store.py` — TranscriptStore (save/load JSON, needs Transcript model integration)
- `lifeos/core/transcribe.py` — transcribe_file returning verbose_json with word/segment timestamps
- `lifeos/core/embeddings.py` — embed_text/embed_query (3072-dim, gemini-embedding-001)
- `lifeos/agent/harness.py` — AgentHarness with manual dispatch loop (budget enforcement to be removed)
- `scripts/ingest.py` — Stub ready for Phase 2 implementation
- `prompts/ingest.md` — Stub prompt ready for Phase 2

### Prior Phase Context
- `.planning/phases/01-infrastructure/01-CONTEXT.md` — Phase 1 decisions (D-04 through D-09)

### Research
- `.planning/research/STACK.md` — Confirmed stack, what to drop, verification notes
- `.planning/research/PITFALLS.md` — FalkorDB silent full scans (need indexes), stale embeddings (need atomic updates), agentic loop termination

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `lifeos/memory/graph.py` — create_node, update_node, create_edge, update_edge, vector_search, get_node all working. These become the backend for agent tools. Need type field removal.
- `lifeos/core/transcribe.py` — transcribe_file returns verbose_json with segments and word timestamps. Direct input to the pipeline.
- `lifeos/core/embeddings.py` — embed_text (RETRIEVAL_DOCUMENT) and embed_query (RETRIEVAL_QUERY). Used by graph.py and will be used for episode span embeddings.
- `lifeos/agent/harness.py` — AgentHarness with google-genai function calling. Budget logic to be removed. Tool dispatch pattern is the foundation.
- `lifeos/memory/store.py` — TranscriptStore with save/load/exists. Needs Transcript model integration and episode span storage.

### Established Patterns
- FalkorDB vecf32 requires REMOVE before SET for vector property updates (learned in Phase 1)
- Log and refs stored as JSON strings in FalkorDB node properties (primitives constraint)
- google-genai types.Part(function_response=types.FunctionResponse(id=fc.id)) for tool response — fc.id must be echoed
- Config singleton via get_config() loading from .env

### Integration Points
- `scripts/ingest.py` is the entry point — wires together transcribe -> agent -> graph -> compression
- FalkorDB on localhost:6379 (Redis protocol)
- Transcript JSON files in data/transcripts/

</code_context>

<specifics>
## Specific Ideas

- The Bitter Lesson is the core design principle — dropping types is a direct expression of this. No categorization, no vocabulary, no schema beyond the minimum structural requirements.
- Agent-driven disambiguation means the system prompt must guide the agent to search before creating, but the actual merge/create decision is pure LLM judgment.
- Log compression preserves the arc of change — inflection points, reversals, contradictions retained. Recent entries kept intact, older entries condensed.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-ingestion-agent*
*Context gathered: 2026-03-26*
