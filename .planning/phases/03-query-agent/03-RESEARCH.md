# Phase 3: Query Agent - Research

**Researched:** 2026-03-29
**Domain:** Agentic retrieval over FalkorDB (vector + graph), litellm function calling, transcript citation
**Confidence:** HIGH

## Summary

Phase 3 completes the read-side of LifeOS. An `AgentHarness` with a query-role system prompt receives a natural-language question and autonomously decides its retrieval strategy using a READ-ONLY subset of existing tools plus two new tools that are missing from the current toolkit: `get_transcript_span` (retrieve raw transcript text for a given span) and `hybrid_search` (vector search seeding immediate graph neighborhood traversal in one call). The agent returns a grounded answer citing `transcript_id`, `start_offset`, and `end_offset`.

The codebase is extremely well-prepared for this phase. `AgentHarness`, `build_tools`, all graph retrieval functions, `TranscriptStore`, and the `EpisodeSpan` model are fully implemented. The `scripts/query.py` and `prompts/query.md` stubs exist and are ready to be filled in. The primary work is: (1) adding two missing tools, (2) writing the query system prompt, (3) implementing `query.py`, and (4) writing tests that mirror the established Nyquist pattern.

**Primary recommendation:** Build a `build_query_tools` factory returning only READ tools plus two new tools (`get_transcript_span`, `hybrid_search`). Wire it into a query `AgentHarness` in `query.py`. Write the query prompt using the same structure as `prompts/ingest.md`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
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

### Claude's Discretion
All implementation choices — tool design, prompt structure, query.py structure, test coverage — are left to Claude's best judgment.

### Deferred Ideas (OUT OF SCOPE)
- Theme layer integration (Phase 4) — always-in-context map for agent navigation
- Bi-temporal versioning for "what was true as of date X" queries
- Hybrid tools fusing vector+graph in single call — noted as possible; implement as new tool OR as prompt guidance
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| VECT-02 | Vector similarity search across all memory layers using FalkorDB native vector indexes | `vector_search` (nodes, 5-tuples) and `vector_search_edges` (edges, 3-tuples) already implemented and tested. `EpisodeSpan.embedding` stored in transcript JSON — needs a new `vector_search_episodes` function or the query tool can load spans and rank inline. |
| VECT-03 | Hybrid vector + graph retrieval: vector similarity seeds graph traversal | Implement as a new `hybrid_search` tool that calls `vector_search` then immediately calls `get_node_edges` on the top-K results, returning nodes + their neighborhood in one call. |
| HARN-02 | Three roles with distinct system prompts: ingestion, query, memo | `prompts/ingest.md` exists and is complete. `prompts/query.md` stub exists — needs detailed instructions. `prompts/memo.md` stub exists — deferred to Phase 4. Query prompt is Phase 3 work. |
| HARN-04 | Tools for: graph read/write/search/merge/delete, vector search, transcript range retrieval | Write tools already exist in `build_tools`. Phase 3 adds `get_transcript_span` (transcript range retrieval) and exposes the query-role tool subset. |
| QURY-01 | Agent decides its own retrieval strategy per query — no hardcoded retrieval pipeline | Fulfilled by giving the agent all read tools + clear prompt about what each layer contains. The harness loop executes whatever tool sequence the model chooses. |
| QURY-02 | Agent uses theme map as navigation context when available | Theme layer not yet built (Phase 4). For Phase 3: prompt notes that the theme layer is not yet populated; agent navigates via search only. Requirement is partially deferred but the hook is documented in the prompt. |
| QURY-03 | Answers grounded in transcript references — agent cites source material | Prompt must instruct agent to include `transcript_id`, `start_offset`, `end_offset` in the final answer. `get_transcript_span` tool enables fetching the exact text span for verification. |
| QURY-04 | Agent can access all three memory layers (transcripts, graph, themes) via tools | Phase 3: Layer 1 (transcripts via `get_transcript_span`) + Layer 2 (graph via search/inspect tools). Theme layer tools deferred to Phase 4. |
</phase_requirements>

---

## Standard Stack

### Core (Already Installed — No New Dependencies Required)
| Library | Version | Purpose | Why Used |
|---------|---------|---------|----------|
| litellm | >=1.82.1 | LLM calls via `AgentHarness` | Already wired; OpenAI-format function calling |
| falkordb | >=1.6.0 | Graph + vector storage | `vector_search`, `get_node_edges` already working |
| google-genai | >=1.14.0 | Embeddings via `embed_query` | `embed_query` uses RETRIEVAL_QUERY task type, already in `embeddings.py` |
| pydantic | >=2.12.5 | `EpisodeSpan`, `TranscriptRef` models | Models already defined |
| pytest | >=9.0.2 | Test framework | 90 existing tests; same patterns apply |

**No new dependencies needed for Phase 3.**

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| json (stdlib) | — | Parse stored `log`/`refs` JSON strings | Already used in `get_node`, `get_edge` tools |
| pathlib (stdlib) | — | `Path` for reading prompt files | Same pattern as `ingest.py` |

---

## Architecture Patterns

### Recommended Project Structure — New Files Only
```
lifeos/
└── agent/
    └── tools.py          # ADD build_query_tools factory alongside build_tools

prompts/
└── query.md              # FILL IN — detailed query system prompt

scripts/
└── query.py              # IMPLEMENT — query.py main()

tests/
└── test_query_tools.py   # NEW — unit tests for build_query_tools
```

No new directories. All new code slots into existing structure.

### Pattern 1: Query Tool Subset Factory (`build_query_tools`)
**What:** A new factory function in `tools.py` that returns only READ-ONLY tools plus two new tools. It mirrors `build_tools` in structure but omits all write/delete/create tools.
**When to use:** Instantiated in `query.py` to give the query agent its tool set.

```python
# In lifeos/agent/tools.py

def build_query_tools(
    graph: Any,
    store: TranscriptStore,
) -> tuple[dict, list]:
    """Build and return query agent tools (READ-ONLY subset + 2 new tools).

    Returns (tools_dict, declarations_list).
    Tools exposed:
      - search_nodes_by_alias      (existing)
      - search_nodes_by_embedding  (existing)
      - get_node                   (existing)
      - get_node_edges             (existing)
      - search_edges_by_embedding  (existing)
      - get_edge                   (existing)
      - get_transcript_span        (NEW)
      - hybrid_search              (NEW)
    """
    # ... re-declare closures from build_tools (or factor shared helpers)
    # ... add two new closures
```

**Reuse strategy:** The existing closure implementations in `build_tools` cannot be directly shared without refactoring. The cleanest approach is to factor the shared read-only closures into module-level helpers, then call them from both factories. Alternatively (simpler) duplicate the 6 read-only closures in `build_query_tools` — the file is already ~545 lines and this adds ~150 lines total with clear separation.

### Pattern 2: `get_transcript_span` Tool (New)
**What:** Loads a transcript from `TranscriptStore` by ID and returns the raw text slice between `start_offset` and `end_offset`. Since Whisper returns `segments` with `start`/`end` timestamps, this can reconstruct text within a time range.

**Key decision:** `start_offset`/`end_offset` are in **seconds** (float/int) — they are Whisper segment timestamps, not character offsets. The retrieval extracts all segments whose `start` falls within the range and concatenates their `text` fields.

```python
def get_transcript_span(
    transcript_id: str,
    start_offset: float,
    end_offset: float,
) -> dict:
    """Retrieve the raw text for a transcript time range.

    Loads the transcript from TranscriptStore, finds all Whisper segments
    within [start_offset, end_offset] seconds, and returns their concatenated text.

    Returns {"transcript_id": ..., "start_offset": ..., "end_offset": ..., "text": ..., "found": True}
    or {"error": "transcript not found"} if the ID is unknown.
    """
    data = store.load(transcript_id)
    if data is None:
        return {"error": "transcript not found"}
    segments = data.get("segments", [])
    # Collect segments within the time window
    span_texts = [
        seg["text"]
        for seg in segments
        if seg.get("start", 0) >= start_offset and seg.get("start", 0) <= end_offset
    ]
    # Fallback: if no segments found (e.g., no Whisper segments stored), return full text slice
    if not span_texts and data.get("text"):
        # Can't slice by time without segments — return full text with note
        return {
            "transcript_id": transcript_id,
            "start_offset": start_offset,
            "end_offset": end_offset,
            "text": data["text"],
            "note": "No segment-level timestamps available; returning full transcript text.",
            "found": True,
        }
    return {
        "transcript_id": transcript_id,
        "start_offset": start_offset,
        "end_offset": end_offset,
        "text": " ".join(span_texts).strip(),
        "found": True,
    }
```

### Pattern 3: `hybrid_search` Tool (New)
**What:** Runs `vector_search` for nodes, then calls `get_node_edges` on each result to return both semantically similar nodes AND their graph neighborhoods in one tool call. Reduces the number of turns needed for graph-augmented retrieval.

```python
def hybrid_search(query: str, k: int = 5) -> dict:
    """Vector search over nodes, enriched with each node's graph edges.

    Returns top-k semantically similar nodes (by embedding) plus the
    edges connected to each — allowing the agent to navigate the graph
    neighborhood without a second tool call.

    Useful for: "what is related to X?" — gets both the concept node and its
    neighbors in one call.
    """
    node_results = graph_module.vector_search(graph, query, k=k)
    enriched = []
    for node_id, name, aliases, summary, score in node_results:
        edges = graph_module.get_node_edges(graph, node_id)
        enriched.append({
            "node_id": node_id,
            "name": name,
            "aliases": aliases,
            "summary": summary,
            "score": score,
            "edges": edges,
        })
    return {"matches": enriched}
```

### Pattern 4: `query.py` Script
**What:** Same structure as `ingest.py`. Accepts a question string, runs the query agent, prints the answer. Optionally supports `--verbose` for JSONL tracing.

```python
# scripts/query.py

def main():
    parser = argparse.ArgumentParser(...)
    parser.add_argument("question", type=str)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    config = get_config()
    graph = init_graph(config.falkordb_host, config.falkordb_port, config.graph_name)
    store = TranscriptStore(config.transcript_dir)

    tracer = None
    if args.verbose:
        from lifeos.agent.tracer import JsonlTracer
        tracer = JsonlTracer()

    tools, declarations = build_query_tools(graph, store)
    harness = AgentHarness(
        model=config.gemini_model,
        tools=tools,
        declarations=declarations,
        tracer=tracer,
        reasoning_effort=config.reasoning_effort,
    )
    system_prompt = Path("prompts/query.md").read_text(encoding="utf-8")
    answer = harness.run(system_prompt=system_prompt, user_message=args.question)
    print(answer)
    print(f"\n[query] Cost: ${harness.last_run_cost:.4f}")
```

### Pattern 5: Query System Prompt Structure
**What:** `prompts/query.md` should follow the same structure as `prompts/ingest.md` — purpose, graph structure description, available tools, working method, and grounding requirements.

**Key sections needed:**
1. **Purpose** — answer questions about the journal using search + graph traversal
2. **Memory layers available** — Layer 1 (raw transcripts), Layer 2 (semantic graph). Theme layer not yet built.
3. **Available tools** — list all 8 tools with when to use each
4. **Working method** — start with a search, follow edges, fetch transcript spans to verify, cite sources
5. **Citation format** — MUST include `transcript_id`, `start_offset`, `end_offset` for every claim
6. **Grounding requirement** — never assert something without a supporting node or transcript span

### Anti-Patterns to Avoid
- **Giving the query agent write tools:** The agent must receive only read tools. Passing `build_tools` (which includes create/update/delete) to the query harness would allow accidental mutation.
- **Hardcoded retrieval routing:** Do not add `if "emotion" in question: use_vector_search()` logic. The agent decides strategy based on prompt instructions.
- **Character-offset confusion:** `start_offset`/`end_offset` are **seconds** (Whisper timestamps), not character positions. `get_transcript_span` must use segment-level time filtering, not string slicing.
- **Episode span vector search via FalkorDB:** Episode spans are stored in the `TranscriptStore` JSON files, not in FalkorDB. There is no FalkorDB index for episode span embeddings. To search episode spans by vector, the agent must retrieve spans via tool and rank inline, OR a new FalkorDB index must be added. **Simplest Phase 3 approach:** expose episode spans as part of `get_transcript_span` response or a separate `search_episode_spans` tool that loads all spans from a transcript and ranks by cosine similarity inline (no new FalkorDB index needed).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Agentic loop | Custom while-loop with tool dispatch | `AgentHarness.run()` | Already implemented, tested (9 tests), handles cost tracking, tracing |
| LLM calls | Direct litellm.completion | `AgentHarness` | Handles message history, multi-turn, tool role messages |
| Node vector search | Custom cosine ranking | `graph_module.vector_search` | FalkorDB native index, already returns 5-tuples |
| Edge vector search | Custom cosine ranking | `graph_module.vector_search_edges` | FalkorDB native index with cosine fallback |
| Config loading | Re-read .env | `get_config()` | Singleton, already tested |
| Transcript loading | File I/O | `TranscriptStore.load()` | Already handles JSON parsing |

---

## Common Pitfalls

### Pitfall 1: Episode Spans Not in FalkorDB
**What goes wrong:** Planner assumes `vector_search` can find episode spans. It cannot — episode spans are stored only in `TranscriptStore` JSON files.
**Why it happens:** Node and edge embeddings live in FalkorDB with proper vector indexes. Episode span embeddings were generated and stored in JSON but no FalkorDB index exists for them.
**How to avoid:** The `search_episode_spans` tool (if added) must load spans from `TranscriptStore` and rank them in Python using cosine similarity (the `vector_search_edges` fallback shows this pattern). Alternatively: skip episode span vector search in Phase 3 — the agent can use `hybrid_search` to find nodes, then follow refs to get `transcript_id`/`start_offset`/`end_offset`, then call `get_transcript_span`.
**Warning signs:** Any code that calls `db.idx.vector.queryNodes` for episode span data will fail.

### Pitfall 2: Passing `build_tools` to the Query Harness
**What goes wrong:** Query agent can call `create_node`, `update_node`, `delete_node` etc. — mutates the graph during a query.
**Why it happens:** Reusing `build_tools` directly is tempting (DRY). But it exposes all write tools.
**How to avoid:** `build_query_tools` returns only the 8 read-only tools. Never pass `build_tools` output to a query harness.

### Pitfall 3: `start_offset`/`end_offset` are Seconds, Not Character Offsets
**What goes wrong:** `get_transcript_span` slices the `text` string by index instead of filtering segments by time.
**Why it happens:** The `TranscriptRef` model documents them as `int | None` without clarifying units. `ingest.md` says "approximate start/end offsets (in seconds)".
**How to avoid:** In `get_transcript_span`, filter `segments` by `seg["start"]` and `seg["end"]` time values. Always include a fallback for transcripts that lack segment-level timestamps.

### Pitfall 4: No Grounding Without `get_transcript_span`
**What goes wrong:** Agent returns an answer citing `transcript_id`/offsets but never fetches the actual text to verify. Answer may hallucinate.
**Why it happens:** The agent can infer offsets from node `refs` without actually reading the transcript.
**How to avoid:** Query prompt's working method must require the agent to call `get_transcript_span` on at least one cited ref before returning the final answer. This is a prompt-level enforcement, not a code-level constraint.

### Pitfall 5: Forgetting `embed_query` vs `embed_text`
**What goes wrong:** A new tool accidentally calls `embed_text` for search-time queries instead of `embed_query`. Retrieval quality degrades because the wrong task type is used.
**Why it happens:** Both functions exist in `embeddings.py`. `vector_search` already uses `embed_query` internally — but any new search that calls the embedding API directly must also use `embed_query`.
**How to avoid:** `hybrid_search` calls `graph_module.vector_search` which internally calls `embed_query`. No direct embedding call needed in new tools.

---

## Code Examples

### How `vector_search` Returns Data (Phase 7 change — 5-tuple)
```python
# Source: lifeos/memory/graph.py — vector_search
# Returns list of (node_id, name, aliases, summary, score) tuples
results = graph_module.vector_search(graph, "anxiety about career", k=5)
# → [("uuid-1", "career anxiety", ["career worry", "work stress"], "She fears...", 0.91), ...]
```

### How `search_nodes_by_embedding` Tool Unpacks 5-tuples
```python
# Source: lifeos/agent/tools.py — search_nodes_by_embedding
results = graph_module.vector_search(graph, query, k=k)
return {
    "matches": [
        {"node_id": r[0], "name": r[1], "aliases": r[2], "summary": r[3], "score": r[4]}
        for r in results
    ]
}
```

### How `get_node_edges` Returns Neighborhood
```python
# Source: lifeos/memory/graph.py — get_node_edges
# Returns list of dicts: {edge_id, label, summary, source: {id, name}, target: {id, name}, direction}
edges = graph_module.get_node_edges(graph, node_id)
# Agent traverses: follow "outgoing" edges to find what this node connects to
```

### How `TranscriptStore.load()` Returns Segment Data
```python
# Source: lifeos/memory/store.py + Transcript model
data = store.load(transcript_id)
# data = {"id": ..., "recorded_at": ..., "text": "...", "segments": [...], "episode_spans": [...]}
# segments: [{"start": 0.0, "end": 4.5, "text": "..."}, ...]  ← Whisper verbose_json format
```

### How litellm `AgentHarness` Is Wired (from ingest.py)
```python
# Source: scripts/ingest.py
tools, declarations = build_tools(graph, store, recording_timestamp=recorded_at)
harness = AgentHarness(
    model=config.gemini_model,
    tools=tools,
    declarations=declarations,
    tracer=tracer,
    reasoning_effort=config.reasoning_effort,
)
result = harness.run(system_prompt=system_prompt, user_message=user_message)
# Query version: same pattern, use build_query_tools, user_message = the question
```

### Existing Test Pattern for Tool Unit Tests
```python
# Source: tests/test_tools.py
def make_graph():
    return MagicMock()

def make_store(transcript_data=None):
    store = MagicMock()
    store.load.return_value = transcript_data or {"id": "t1", "text": "hello", "episode_spans": []}
    return store

@patch("lifeos.agent.tools.graph_module.vector_search")
def test_search_nodes_by_embedding_enriched(mock_vector_search):
    mock_vector_search.return_value = [("id1", "anxiety", ["worry"], "She feels...", 0.9)]
    from lifeos.agent.tools import build_tools
    tools_dict, _ = build_tools(make_graph(), make_store())
    result = tools_dict["search_nodes_by_embedding"](query="anxiety", k=5)
    assert result["matches"][0]["name"] == "anxiety"
```

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=9.0.2 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `devenv shell -- uv run python -m pytest tests/test_query_tools.py -x -q` |
| Full suite command | `devenv shell -- uv run python -m pytest tests/ -q` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VECT-02 | `search_nodes_by_embedding` returns scored node results | unit | `pytest tests/test_query_tools.py::test_search_nodes_by_embedding_returns_matches -x` | ❌ Wave 0 |
| VECT-02 | `search_edges_by_embedding` returns scored edge results | unit | `pytest tests/test_query_tools.py::test_search_edges_by_embedding_returns_matches -x` | ❌ Wave 0 |
| VECT-02 | `search_episode_spans` (if added) returns ranked spans | unit | `pytest tests/test_query_tools.py::test_search_episode_spans_returns_ranked -x` | ❌ Wave 0 |
| VECT-03 | `hybrid_search` calls vector_search then get_node_edges | unit | `pytest tests/test_query_tools.py::test_hybrid_search_enriches_with_edges -x` | ❌ Wave 0 |
| HARN-02 | `prompts/query.md` is non-stub (len > 200 chars) | unit | `pytest tests/test_query_tools.py::test_query_prompt_is_substantive -x` | ❌ Wave 0 |
| HARN-04 | `build_query_tools` returns exactly 8 (or N) read-only tools | unit | `pytest tests/test_query_tools.py::test_build_query_tools_count -x` | ❌ Wave 0 |
| HARN-04 | `build_query_tools` does NOT expose write tools | unit | `pytest tests/test_query_tools.py::test_build_query_tools_no_write_tools -x` | ❌ Wave 0 |
| HARN-04 | `get_transcript_span` returns text for valid transcript | unit | `pytest tests/test_query_tools.py::test_get_transcript_span_returns_text -x` | ❌ Wave 0 |
| HARN-04 | `get_transcript_span` handles missing transcript_id | unit | `pytest tests/test_query_tools.py::test_get_transcript_span_not_found -x` | ❌ Wave 0 |
| HARN-04 | `get_transcript_span` handles no-segments fallback | unit | `pytest tests/test_query_tools.py::test_get_transcript_span_no_segments_fallback -x` | ❌ Wave 0 |
| QURY-01 | Agent harness with query tools dispatches tool calls | unit (harness mock) | `pytest tests/test_query_tools.py::test_query_harness_dispatches_tools -x` | ❌ Wave 0 |
| QURY-03 | `query.py` main() runs without error (smoke, mocked) | unit | `pytest tests/test_query_tools.py::test_query_script_runs_smoke -x` | ❌ Wave 0 |
| QURY-03 | `hybrid_search` declarations list tool with correct name | unit | `pytest tests/test_query_tools.py::test_query_declarations_include_hybrid_search -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `devenv shell -- uv run python -m pytest tests/test_query_tools.py -x -q`
- **Per wave merge:** `devenv shell -- uv run python -m pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_query_tools.py` — covers all VECT-02, VECT-03, HARN-02, HARN-04, QURY-01, QURY-03 unit tests listed above

*(Existing `tests/conftest.py` covers fixtures — no changes needed. `tests/test_tools.py` pattern is the reference for all new tool tests.)*

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|---------|
| FalkorDB (Docker) | Graph + vector reads | ✓ (via devenv) | runs on port 6379 | — |
| litellm | AgentHarness | ✓ | >=1.82.1 in pyproject | — |
| google-genai | `embed_query` | ✓ | >=1.14.0 in pyproject | — |
| pytest | Test suite | ✓ | >=9.0.2 in pyproject | — |
| GEMINI_API_KEY | LLM + embeddings | ✓ | in .env | — |

**No missing dependencies.** Phase 3 requires no new packages.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `vector_search` returned 3-tuples (id, summary, score) | Returns 5-tuples (id, name, aliases, summary, score) | Phase 7 | `build_query_tools` must unpack 5-tuples |
| `search_nodes_by_embedding` in tools.py returned only `node_id`/`summary`/`score` | Now returns `name` and `aliases` too | Phase 7 | Agent has richer identification info |
| No edge vector index | EDGE vector index added in `init_graph` | Phase 7 | `search_edges_by_embedding` can use native index |

**Key active decisions from STATE.md relevant to Phase 3:**
- `vector_search` returns 5-tuples — unpack as `(node_id, name, aliases, summary, score)` everywhere
- Tool results use `role:tool` messages with `tool_call_id` — handled by `AgentHarness`, transparent to tool implementations
- `reasoning_effort` string parameter (not `thinking_budget` integer) — set via `config.reasoning_effort`
- Cost tracking is best-effort (`try/except`) — already in harness, no action needed

---

## Open Questions

1. **Episode span vector search strategy**
   - What we know: `EpisodeSpan.embedding` is stored in transcript JSON. No FalkorDB index for spans.
   - What's unclear: Should Phase 3 expose `search_episode_spans` as a tool (inline cosine ranking in Python, no new FalkorDB index), or should the agent just follow node refs to find transcript spans?
   - Recommendation: Add a lightweight `search_episode_spans` tool that accepts a `transcript_id` (optional) and query string, loads all spans, ranks by dot product inline. This is ~20 lines of Python using the same cosine fallback pattern as `vector_search_edges`. This directly satisfies VECT-02 ("across all memory layers").

2. **Number of tools in `build_query_tools`**
   - What we know: 6 existing read-only tools + 2 new tools = 8. If `search_episode_spans` is added = 9.
   - What's unclear: Whether episode span search is strictly required for Phase 3 or can be added as part of `hybrid_search` prompt guidance.
   - Recommendation: Add `search_episode_spans` for completeness (VECT-02 requires "all memory layers"). 9 tools total. Tests should check for this exact count.

3. **`query.py` argument format**
   - What we know: The phase success criterion says "running `query.py` with a question".
   - What's unclear: Should the question be a positional argument or `--question` flag?
   - Recommendation: Positional argument (`python scripts/query.py "What am I anxious about?"`) — matches natural shell invocation, mirrors `ingest.py audio_file` pattern.

---

## Project Constraints (from CLAUDE.md)

| Directive | Impact on Phase 3 |
|-----------|-------------------|
| NixOS + devenv: `devenv shell -- uv run` | All script invocations: `devenv shell -- uv run python scripts/query.py "question"` |
| No global package managers | No `pip install` — all deps in `pyproject.toml` already |
| Python: use `uv`, linting: `ruff` | Run `devenv shell -- uv run ruff check lifeos/agent/tools.py` after changes |
| Tech stack locked: FalkorDB, Gemini 2.5 Flash, litellm | No alternative LLM providers, no ChromaDB, no LangChain |
| No rigid schema | Query tools must not enforce any node/edge type filters |
| Single agent harness | Use existing `AgentHarness` — do not create a `QueryHarness` subclass |
| GSD workflow | No direct file edits outside a GSD workflow |

---

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection: `lifeos/agent/harness.py`, `lifeos/agent/tools.py`, `lifeos/memory/graph.py`, `lifeos/memory/store.py`, `lifeos/memory/models.py`, `lifeos/core/config.py`
- `scripts/ingest.py` — reference implementation for query.py structure
- `prompts/ingest.md` — reference for query prompt structure
- `tests/test_harness.py`, `tests/test_tools.py` — established test patterns
- `.planning/STATE.md` — Phase 6/7 decisions affecting current API shapes
- `.planning/phases/03-query-agent/03-CONTEXT.md` — locked design decisions

### Secondary (MEDIUM confidence)
- `pyproject.toml` — package versions verified as installed minimums

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages confirmed in pyproject.toml, no new deps needed
- Architecture: HIGH — derived directly from existing code patterns, not speculation
- New tools design: HIGH — `get_transcript_span` and `hybrid_search` follow established closure/declaration patterns exactly
- Pitfalls: HIGH — episode span storage in JSON (not FalkorDB) confirmed by reading store.py and models.py; offset-in-seconds confirmed by ingest.md
- Test patterns: HIGH — 90 existing tests provide exact patterns to follow

**Research date:** 2026-03-29
**Valid until:** 2026-04-29 (stable codebase; only invalidated by further phase completions that add new tools or change APIs)
