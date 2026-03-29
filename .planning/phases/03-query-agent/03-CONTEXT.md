# Phase 3: Query Agent - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning

<domain>
## Phase Boundary

A natural-language question about the ingested journal can be answered with source citations. The query agent autonomously decides its retrieval strategy across all three memory layers using vector similarity, graph traversal, and direct transcript access. No hardcoded retrieval pipeline — the agent reasons about which tools to use per query.

Success criteria:
1. `query.py` with a question returns an answer grounded in specific transcript spans with `transcript_id`, `start_offset`, `end_offset` citations
2. Vector similarity search across node summaries and episode summaries returns ranked results using FalkorDB native vector indexes
3. The query agent makes its own tool-call sequence per query — different questions use different retrieval paths
4. Hybrid vector+graph retrieval is available: a vector search result can seed graph traversal in a single operation

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion

All implementation choices are at Claude's discretion — user explicitly requested autonomous execution with best architectural and agent harness engineering decisions. The following design ideology from Memory-v3.md guides all decisions:

**Core ideology:**
- "Design representation to be maximally expressive, and delegate query strategy entirely to the agent at query time"
- "Tell LLM what is available, and it will figure out how to find the answer"
- "No routing is hardcoded — the agent is told what layers exist and what each contains, and decides its own retrieval strategy per query"
- Citations required: "requiring the LLM to ground responses in cited source material reduces hallucination rates significantly"

**Key architectural constraints from Memory-v3.md:**
- Reuse the existing single agent harness with a query role-specific prompt
- The query agent gets READ-ONLY graph tools (search + inspect) plus transcript access — no write tools
- The prompt tells the agent what layers exist and what each contains; the agent decides strategy
- Hybrid retrieval: "vector search + graph traversal in a single call — returning semantically similar nodes _and_ their graph neighborhoods together"
- The themes layer is NOT yet built (Phase 4), so query agent works with only Layer 1 (transcripts) and Layer 2 (semantic graph) for now

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `AgentHarness` — single agentic loop, reuse as-is with query system prompt
- 13 existing tools in `build_tools()` — query agent needs search + read subset
- `graph.py` retrieval functions: `vector_search`, `vector_search_edges`, `get_node`, `get_node_edges`, `get_edge`, `search_nodes_by_alias`
- `TranscriptStore.load()` — retrieve raw transcript text by ID
- `EpisodeSpan` model with embeddings for transcript range navigation
- `JsonlTracer` for query debugging

### Established Patterns
- Tools built as closures via factory function (`build_tools`)
- OpenAI-format tool declarations (dicts, not SDK imports)
- litellm for LLM calls with `reasoning_effort` control
- `embed_query()` for retrieval-time embeddings vs `embed_text()` for storage

### Integration Points
- `scripts/query.py` — stub exists, needs full implementation
- `prompts/query.md` — stub exists, needs detailed instructions
- `lifeos/agent/tools.py` — may need query-specific tool subset factory or new tools (transcript retrieval, hybrid search)

</code_context>

<specifics>
## Specific Ideas

User explicitly requested adherence to Memory-v3.md ideologies:
- "General-Purpose > Human-Engineered with heuristics and constraints"
- "Agentic retrieval: Tell LLM what is available, and it will figure out how to find the answer"
- Themes layer (always-in-context map) deferred to Phase 4 — query agent starts "blind" and uses vector+graph search to find relevant information

</specifics>

<deferred>
## Deferred Ideas

- Theme layer integration (Phase 4) — always-in-context map for agent navigation
- Bi-temporal versioning for "what was true as of date X" queries (noted as future consideration in Memory-v3.md)
- Hybrid tools fusing vector+graph in single call (Memory-v3.md design note) — may implement as a new tool or as prompt guidance for the agent to chain existing tools

</deferred>
