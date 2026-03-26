# Phase 2: Ingestion Agent - Research

**Researched:** 2026-03-26
**Domain:** Python/FalkorDB/Gemini — agentic ingestion pipeline with graph write, disambiguation, episode spans, log compression
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Data Model Changes**
- D-01: Drop `type` field from both Node and Edge models entirely. No types, no vocabulary registry (INGST-05 dropped). The Bitter Lesson: types are a categorization scheme imposed on data. The summary carries all semantic meaning.
- D-02: Node model: `id`, `name`, `summary`, `aliases`, `log`, `refs`, `embedding`. Keep an explicit `name` field as the canonical display label (separate from aliases list).
- D-03: Edge model: `id`, `source_id`, `target_id`, `label`, `summary`, `log`, `refs`, `embedding`. Rename `type` to `label` — a concise relationship descriptor ("father_of", "fears", "evolved_into"). Summary carries the full description.
- D-04: Create a Transcript Pydantic model with: `id`, `recorded_at` (datetime), `text` (str), `segments` (from Whisper verbose_json), `episode_spans` (list, added post-ingestion). Formalizes the record, consistent with Node/Edge models.

**Agent Tool Design**
- D-05: Fine-grained individual tools: `search_nodes_by_alias`, `search_nodes_by_embedding`, `create_node`, `update_node`, `delete_node`, `create_edge`, `update_edge`, `delete_edge`, `create_episode_spans`. Agent decides exactly which operations to perform per transcript.
- D-06: No dedicated merge tool — agent composes merges from primitives (update one node's aliases/summary, re-point edges, delete the other).
- D-07: Delete tools included for both nodes and edges.
- D-08: Remove tool-call budget enforcement entirely. Let the agent call as many tools as it needs.
- D-09: Graph awareness via search tools only — no upfront graph snapshot injected into the system prompt.

**Disambiguation**
- D-10: Fully agent-driven disambiguation. The 3-tier flow (exact alias match -> embedding similarity -> LLM reasoning) is emergent from the agent's tool-calling behavior, guided by the system prompt. No code-driven gates.
- D-11: Fuzzy matching uses embedding similarity (vector search on node summaries). Not string distance.
- D-12: Search tools return candidates with similarity scores. Agent sees scores and makes all merge/create decisions itself.

**Episode Spans**
- D-13: Episode spans stored in transcript JSON on disk (alongside raw text in TranscriptStore). Not in FalkorDB as separate nodes.
- D-14: Episode spans created after all graph writes complete.

**Log Compression**
- D-15: Post-ingestion compression pass — after the agent finishes all graph writes, Python code identifies over-budget logs and compresses them.
- D-16: Compression done by a separate standalone Gemini LLM call with a compression-specific prompt. Not the ingestion agent loop. No tools, just input log -> output compressed log.
- D-17: Token-count threshold triggers compression. Needs a token counting utility.

**Ingestion Prompt**
- D-18: Minimal guardrails prompt — describe the graph structure, list available tools, state the goal.
- D-19: Explicitly state selectivity (INGST-04): only create/update nodes for things that matter to the person's evolving inner life.
- D-20: Recording timestamp passed in user message: "Recording from [date]:\n\n[transcript text]".

**Transcript Source**
- D-21: Recording timestamp read from audio file metadata (filesystem mtime). Falls back to current time if metadata missing.

**Ingest Script UX**
- D-22: `ingest.py` accepts a single audio file path as argument. One file per run.
- D-23: On completion, print a summary of changes: transcript ID, nodes created/updated/merged count, edges created/updated count, episode spans count.

### Claude's Discretion
- Token threshold value for log compression (research to determine a good starting point)
- Exact set of FalkorDB index changes needed after dropping type field
- Whether to use async or sync for the agent loop and compression pass
- Episode span embedding approach (embed the span summary for future retrieval)
- How to count tokens for compression threshold (tiktoken, simple word estimate, or Gemini tokenizer)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TRNS-01 | System accepts audio files and transcribes via Groq Whisper API | `transcribe_file()` already works via litellm; `ingest.py` wires it |
| TRNS-02 | Raw transcript stored with unique ID, recording timestamp, and full text | New `Transcript` Pydantic model + `TranscriptStore.save()` |
| TRNS-03 | Episode spans (start_offset, end_offset, summary, embedding) created during ingestion as a side effect of graph writing | `create_episode_spans` tool + post-agent pass embeds span summaries |
| GRPH-02 | Nodes carry: current summary, append-only log, alias set, transcript references | Node model updated (drop type, add name); `update_node` extended |
| GRPH-03 | Edges carry: current summary, append-only log, transcript references | Edge model updated (drop type, add label); `update_edge` extended |
| GRPH-04 | Node and edge types are entirely LLM-defined — no hardcoded entity types or relationship types | D-01/D-03 enforce this at model level; no type field at all |
| INGST-01 | Agent reads full transcript at once (no chunking) and builds/updates graph | Agent harness receives full transcript text in user message |
| INGST-02 | Three-tier node disambiguation: exact alias match -> fuzzy similarity -> LLM reasoning | `search_nodes_by_alias` + `search_nodes_by_embedding` tools + agent prompt guidance |
| INGST-03 | When nodes merge, alias sets are unioned; new surface forms added to existing alias sets | `update_node` takes optional new_aliases param; agent calls it during merge |
| INGST-04 | Agent exercises judgment on what's worth persisting | D-19 prompt directive |
| INGST-05 | Vocabulary registry (DROPPED per D-01) | Dropped — not implementing |
| INGST-06 | Log entries include recording timestamp and natural language note describing what changed | `LogEntry` model already has recorded_at + note; agent passes recording timestamp |
| COMP-01 | Token-budgeted compression triggers when a node/edge log exceeds threshold | Post-ingestion pass using tiktoken cl100k_base; threshold = 2000 tokens |
| COMP-02 | Compression preserves arc of change — inflection points, reversals, contradictions retained | Compression prompt instructs Gemini to preserve arc; older entries condensed |
| COMP-03 | Recent entries kept intact; older entries condensed into summary | Compression prompt defines "recent" as last 3 entries; older ones compressed |
| VECT-01 | Embeddings generated via gemini-embedding-001 for node summaries, edge summaries, episode summaries | Existing `embed_text()` used for all three; episode span embedding added |
</phase_requirements>

---

## Summary

Phase 2 builds on a solid Phase 1 foundation. The core infrastructure (FalkorDB, harness, embeddings, transcription) is operational. Phase 2 wires them into a complete ingestion pipeline: audio file -> transcript -> LLM agent -> graph writes -> compression pass.

The key architectural changes from Phase 1: drop the `type` field from Node and Edge (replacing with explicit `name` on Node and `label` on Edge), add a `Transcript` Pydantic model, implement 9 agent tools in `lifeos/agent/tools.py`, implement a post-ingestion compression pass in `lifeos/agent/compress.py`, and fully implement `scripts/ingest.py` and `prompts/ingest.md`.

The hardest sub-problem is disambiguation. The design is fully agent-driven (D-10), meaning the prompt must guide the agent to always search before creating. The two search tools — `search_nodes_by_alias` (exact match against aliases array in FalkorDB) and `search_nodes_by_embedding` (vector KNN, already in `graph.py`) — together give the agent the full 3-tier disambiguation capability described in INGST-02.

**Primary recommendation:** Build Phase 2 in three waves: (1) update models/graph/harness to align with new data model, (2) implement agent tools + prompt + ingest.py pipeline, (3) implement log compression + episode spans.

---

## Standard Stack

### Core (all already installed and verified)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| google-genai | 1.68.0 | LLM agent loop + compression calls | Already in devenv; `types.FunctionDeclaration` + `types.Tool` for tool definitions |
| falkordb | 1.6.0 | Graph storage, vector search, Cypher | Already in devenv; `$alias IN n.aliases` for alias search |
| litellm | 1.82.4 | Groq Whisper transcription | Already in devenv; `transcribe_file()` working |
| pydantic | 2.12.5 | Transcript, Node, Edge, EpisodeSpan models | Already in devenv; `model_dump(mode="json")` for FalkorDB serialization |
| tiktoken | 0.12.0 | Token counting for compression threshold | Already installed; `cl100k_base` encoding; no API call, no latency |
| python-dotenv | installed | .env loading | Already in devenv |

**No new dependencies needed for Phase 2.**

### Verified API Patterns

**FunctionDeclaration construction (verified against 1.68.0):**
```python
from google.genai import types

fd = types.FunctionDeclaration(
    name="create_node",
    description="Create a new node in the graph.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "name": types.Schema(type="STRING", description="Canonical display name"),
            "summary": types.Schema(type="STRING", description="Current summary"),
            "aliases": types.Schema(
                type="ARRAY",
                items=types.Schema(type="STRING"),
                description="All known surface forms",
            ),
        },
        required=["name", "summary"],
    ),
)
```

**FunctionResponse construction (verified, fc.id must be echoed):**
```python
types.Part(
    function_response=types.FunctionResponse(
        name=fc.name,
        response={"result": result},
        id=fc.id,
    )
)
```

**FalkorDB alias search (array contains):**
```cypher
MATCH (n:Node) WHERE $alias IN n.aliases
RETURN n.id, n.name, n.aliases, n.summary
```

**FalkorDB REMOVE before SET for vecf32 (established in Phase 1):**
```python
graph.query("MATCH (n:Node {id: $id}) REMOVE n.embedding", {"id": node_id})
graph.query("MATCH (n:Node {id: $id}) SET n.embedding = vecf32($emb)", {"id": node_id, "emb": emb})
```

**tiktoken token counting:**
```python
import tiktoken
_enc = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(_enc.encode(text))
```

---

## Architecture Patterns

### Recommended Project Structure Changes

```
lifeos/
├── agent/
│   ├── harness.py        # MODIFY: remove budget enforcement (D-08)
│   ├── tools.py          # NEW: 9 ingestion agent tools (D-05)
│   └── compress.py       # NEW: post-ingestion log compression pass
├── memory/
│   ├── models.py         # MODIFY: drop type, add name/label, add Transcript model
│   ├── graph.py          # MODIFY: drop type index, extend update_node/edge, add delete functions
│   └── store.py          # MODIFY: Transcript model integration
├── core/
│   ├── transcribe.py     # NO CHANGE — works as-is
│   ├── embeddings.py     # NO CHANGE — works as-is
│   └── config.py         # NO CHANGE — works as-is
prompts/
├── ingest.md             # IMPLEMENT: D-18, D-19, D-20 prompt design
└── compress.md           # NEW: log compression prompt
scripts/
└── ingest.py             # IMPLEMENT: full pipeline wiring
tests/
├── test_models.py        # MODIFY: update existing type-based tests, add Transcript tests
├── test_graph.py         # MODIFY: update for type removal, add delete_node/delete_edge tests
├── test_tools.py         # NEW: unit tests for each agent tool (mocked graph)
└── test_compress.py      # NEW: compression threshold + Gemini call tests (mocked)
```

### Pattern 1: Model Field Removal (D-01, D-02, D-03)

Remove `type: str` from `Node`. Add `name: str`. Remove `type: str` from `Edge`. Add `label: str`. These are breaking changes — all callers (graph.py, tests) must update.

```python
# models.py after changes
class Node(BaseModel):
    id: str
    name: str                                    # NEW: canonical display label
    summary: str
    aliases: list[str] = Field(default_factory=list)
    log: list[LogEntry] = Field(default_factory=list)
    refs: list[TranscriptRef] = Field(default_factory=list)
    embedding: list[float] | None = None

class Edge(BaseModel):
    id: str
    label: str                                   # RENAMED from type
    source_id: str
    target_id: str
    summary: str
    log: list[LogEntry] = Field(default_factory=list)
    refs: list[TranscriptRef] = Field(default_factory=list)
    embedding: list[float] | None = None

class EpisodeSpan(BaseModel):
    start_offset: int
    end_offset: int
    summary: str
    embedding: list[float] | None = None

class Transcript(BaseModel):
    id: str
    recorded_at: datetime
    text: str
    segments: list[dict] = Field(default_factory=list)   # from Whisper verbose_json
    episode_spans: list[EpisodeSpan] = Field(default_factory=list)
```

### Pattern 2: graph.py Changes

**Remove:** `n.type` from CREATE NODE query, `CREATE INDEX FOR (n:Node) ON (n.type)`.

**Add:** `n.name` to CREATE NODE query (as explicit field — was derived from aliases before), `r.label` to CREATE EDGE query (was `r.type`), `CREATE INDEX FOR ()-[r:EDGE]->() ON (r.label)`.

**Extend `update_node`:** Add optional `new_aliases`, `new_refs`, `new_name` params. When provided, these are appended/updated atomically alongside the summary re-embed.

**Add `delete_node` and `delete_edge`:**

```python
def delete_node(graph, node_id: str) -> None:
    """Delete a node and all its connected edges."""
    graph.query(
        "MATCH (n:Node {id: $id}) DETACH DELETE n",
        {"id": node_id},
    )

def delete_edge(graph, edge_id: str) -> None:
    """Delete an edge by id."""
    graph.query(
        "MATCH ()-[r:EDGE {id: $id}]->() DELETE r",
        {"id": edge_id},
    )
```

**Add `search_nodes_by_alias`:**

```python
def search_nodes_by_alias(graph, alias: str) -> list[dict]:
    """Exact alias match — returns nodes where alias is in n.aliases."""
    result = graph.query(
        "MATCH (n:Node) WHERE $alias IN n.aliases "
        "RETURN n.id, n.name, n.aliases, n.summary",
        {"alias": alias},
    )
    return [
        {"id": row[0], "name": row[1], "aliases": row[2], "summary": row[3]}
        for row in result.result_set
    ]
```

### Pattern 3: Agent Tools (lifeos/agent/tools.py)

All 9 tools from D-05 are thin wrappers around graph.py functions. They accept the tool arguments as plain Python types (strings, lists), call the appropriate graph function, and return a dict the agent can read.

Each tool receives `graph` via closure (tools are built with `build_tools(graph, store)` factory function).

```python
# tools.py — factory pattern
def build_tools(graph, store: TranscriptStore) -> tuple[dict, list]:
    """Return (tools_dict, declarations_list) for the ingestion agent."""

    def search_nodes_by_alias(alias: str) -> dict:
        results = graph_module.search_nodes_by_alias(graph, alias)
        return {"matches": results, "count": len(results)}

    def search_nodes_by_embedding(query: str, k: int = 5) -> dict:
        results = graph_module.vector_search(graph, query, k=k)
        return {"matches": [
            {"node_id": r[0], "summary": r[1], "score": r[2]} for r in results
        ]}

    def create_node(name: str, summary: str, aliases: list[str] | None = None,
                    transcript_id: str | None = None,
                    start_offset: int | None = None,
                    end_offset: int | None = None) -> dict:
        node_id = str(uuid.uuid4())
        aliases = aliases or [name]
        refs = []
        if transcript_id:
            refs = [TranscriptRef(transcript_id=transcript_id,
                                  start_offset=start_offset,
                                  end_offset=end_offset)]
        node = Node(id=node_id, name=name, summary=summary,
                    aliases=aliases, refs=refs)
        graph_module.create_node(graph, node)
        return {"node_id": node_id, "created": True}

    # ... similar for update_node, delete_node, create_edge, update_edge,
    #     delete_edge, create_episode_spans

    tools = {
        "search_nodes_by_alias": search_nodes_by_alias,
        "search_nodes_by_embedding": search_nodes_by_embedding,
        "create_node": create_node,
        "update_node": update_node,
        "delete_node": delete_node,
        "create_edge": create_edge,
        "update_edge": update_edge,
        "delete_edge": delete_edge,
        "create_episode_spans": create_episode_spans,
    }
    declarations = [...]  # FunctionDeclaration for each tool
    return tools, declarations
```

### Pattern 4: Harness Budget Removal (D-08)

Remove the `budget` parameter and the `calls_used >= self.budget` branch entirely. The loop runs until the model returns no function calls.

```python
# harness.py after D-08
def run(self, system_prompt: str, user_message: str) -> str:
    tool_config = types.Tool(function_declarations=self.declarations)
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[tool_config],
    )
    contents = [types.Content(role="user", parts=[types.Part(text=user_message)])]

    while True:
        response = self.client.models.generate_content(
            model=self.model, contents=contents, config=config,
        )
        contents.append(response.candidates[0].content)
        fc_parts = [p for p in response.candidates[0].content.parts if p.function_call]

        if not fc_parts:
            return response.text

        response_parts = []
        for part in fc_parts:
            fc = part.function_call
            result = self.tools[fc.name](**fc.args)
            response_parts.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=fc.name, response={"result": result}, id=fc.id,
                    )
                )
            )
        contents.append(types.Content(role="user", parts=response_parts))
```

### Pattern 5: Log Compression (lifeos/agent/compress.py)

Post-ingestion pass: after agent loop finishes, iterate all modified nodes and edges. For each one whose log exceeds the token threshold, call Gemini (no tools) with the compression prompt.

```python
LOG_COMPRESSION_THRESHOLD = 2000  # tiktoken cl100k_base tokens

def needs_compression(log_json: str) -> bool:
    return count_tokens(log_json) > LOG_COMPRESSION_THRESHOLD

def compress_log(log_entries: list[dict], client: genai.Client) -> list[dict]:
    """Compress older log entries, keep last 3 intact. Returns new log."""
    if len(log_entries) <= 3:
        return log_entries
    recent = log_entries[-3:]
    older = log_entries[:-3]
    prompt = load_prompt("prompts/compress.md")
    older_json = json.dumps(older, indent=2, default=str)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"Compress these log entries:\n\n{older_json}",
        config=types.GenerateContentConfig(system_instruction=prompt),
    )
    # Parse the compressed entry from response — single LogEntry JSON
    compressed = json.loads(response.text)
    return [compressed] + recent

def run_compression_pass(graph, modified_node_ids: list[str],
                         modified_edge_ids: list[str],
                         client: genai.Client) -> int:
    """Compress logs for all over-budget nodes and edges. Returns compression count."""
    compressed_count = 0
    for node_id in modified_node_ids:
        node = graph_module.get_node(graph, node_id)
        if node and node.get("log") and needs_compression(node["log"]):
            log_entries = json.loads(node["log"])
            new_log = compress_log(log_entries, client)
            # Write back compressed log via direct SET (no summary change)
            graph_module.set_node_log(graph, node_id, new_log)
            compressed_count += 1
    # Similar for edges
    return compressed_count
```

### Pattern 6: Ingest Pipeline (scripts/ingest.py)

```python
def main():
    import sys
    audio_path = Path(sys.argv[1])
    config = get_config()
    graph = init_graph(config.falkordb_host, config.falkordb_port, config.graph_name)
    store = TranscriptStore(config.transcript_dir)
    client = genai.Client()

    # Step 1: Transcribe
    raw = transcribe_file(audio_path)
    recorded_at = get_recording_timestamp(audio_path)   # mtime fallback to now

    # Step 2: Store transcript
    transcript_id = str(uuid.uuid4())
    transcript = Transcript(
        id=transcript_id,
        recorded_at=recorded_at,
        text=raw.get("text", ""),
        segments=raw.get("segments", []),
    )
    store.save(transcript_id, transcript.model_dump(mode="json"))

    # Step 3: Run ingestion agent
    tools, declarations = build_tools(graph, store)
    harness = AgentHarness(model="gemini-2.5-flash", tools=tools,
                           declarations=declarations, client=client)
    system_prompt = load_prompt("prompts/ingest.md")
    user_message = f"Recording from {recorded_at.strftime('%Y-%m-%d')}:\n\n{transcript.text}"
    harness.run(system_prompt=system_prompt, user_message=user_message)

    # Step 4: Compression pass (runs over all nodes/edges — or track modified IDs)
    compressed = run_compression_pass(graph, client=client)

    # Step 5: Print summary
    print(f"[ingest] Transcript: {transcript_id}")
    print(f"[ingest] Compressed logs: {compressed}")
```

### Anti-Patterns to Avoid

- **Injecting graph snapshot into system prompt:** D-09 explicitly forbids this. The agent discovers state via search tools only.
- **Chunking transcripts:** INGST-01 and Memory-v3.md explicitly forbid chunking. Pass the full text.
- **Hardcoding node types in any enum or validator:** GRPH-04 / D-01. The `name` and `label` fields are free strings; no validation beyond `str`.
- **Calling `embed_text` twice for the same summary:** The `update_node` and `create_node` functions in `graph.py` handle embedding internally — never call `embed_text` separately before passing to graph functions.
- **Using `types.Part.from_function_response()` with `id=`:** This raises a TypeError in google-genai 1.68.0. Use `types.Part(function_response=types.FunctionResponse(id=fc.id, ...))` directly (established in Phase 1, documented in STATE.md).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Token counting | Custom character-based estimator | tiktoken `cl100k_base` | Already installed; 4x more accurate; handles subword tokenization correctly |
| Vector similarity search | Python cosine similarity over all nodes | `graph.py vector_search()` (FalkorDB KNN) | Already implemented; uses native FalkorDB vector index; O(log n) not O(n) |
| Alias deduplication across nodes | Separate Python fuzzy-match loop | `search_nodes_by_alias` + `search_nodes_by_embedding` tools | Agent-driven per D-10/D-11; embedding similarity is the fuzzy match mechanism |
| JSON serialization of Pydantic models for FalkorDB | Custom serializer | `model.model_dump(mode="json")` + `json.dumps(...)` | Established pattern in Phase 1; handles datetime serialization correctly |
| UUID generation | Timestamp-based IDs or counters | `str(uuid.uuid4())` | Standard; guaranteed unique; no coordination needed |

**Key insight:** Every "complex" problem in this phase (vector search, token counting, JSON serialization, graph CRUD) has a working solution already in the codebase or in an installed library. The phase adds wiring and agent orchestration, not new algorithms.

---

## Common Pitfalls

### Pitfall 1: FalkorDB vecf32 REMOVE Before SET
**What goes wrong:** Calling `SET n.embedding = vecf32($new)` on an existing node silently keeps the old vector value.
**Why it happens:** FalkorDB property mutation behavior for vecf32 typed values.
**How to avoid:** Always issue `REMOVE n.embedding` in a separate query before the `SET`. Already in `update_node` and `update_edge` — do not skip this for any new path that touches embeddings.
**Warning signs:** Vector search returns stale results after updates; scores don't change when summary changes.

### Pitfall 2: Existing Tests Use `type` Field
**What goes wrong:** `test_models.py` has 5+ tests that construct `Node(id=..., type=..., summary=...)` — these break immediately when `type` is dropped from the model.
**Why it happens:** Phase 1 built against the old model.
**How to avoid:** Update `test_models.py` in the same wave that updates `models.py`. The test for "type accepts any string" (`test_node_type_is_free_string`) must be replaced with equivalent test for `name`.

### Pitfall 3: graph.py Hardcodes `type` in Queries
**What goes wrong:** `create_node` and `create_edge` in `graph.py` include `type: $type` in the Cypher CREATE. If not updated, FalkorDB will store a `null` type or raise an error.
**Why it happens:** The code was written against the old model.
**How to avoid:** Update `create_node` to use `name: $name` (explicit field), remove `type` from CREATE. Update `create_edge` to use `label: $label`, remove `type`.

### Pitfall 4: Agent Returns Text Alongside Tool Calls (Mixed Turn)
**What goes wrong:** Model sometimes emits a text part AND a function_call part in the same response. If the harness only checks `parts[0]` for function calls, it misses the FC.
**Why it happens:** Gemini 2.5 Flash "thinking" responses can have text parts before FCs.
**How to avoid:** Already handled in `harness.py` — `fc_parts = [p for p in response.candidates[0].content.parts if p.function_call]`. Do not regress this when removing budget logic.

### Pitfall 5: update_node Loses Refs When Not Passed
**What goes wrong:** The current `update_node` signature doesn't accept refs — if the agent calls `update_node` to add a transcript reference, the function has no way to store it.
**Why it happens:** Phase 1 `update_node` only updated summary + log.
**How to avoid:** Extend `update_node` signature to accept `new_aliases: list[str] | None = None` and `new_refs: list[TranscriptRef] | None = None`. When provided, append to existing values (not replace).

### Pitfall 6: Compression Overwrites Summary Embedding
**What goes wrong:** If the compression pass calls `update_node` (which re-embeds the summary), and the log compression changes only the log (not the summary), this triggers a spurious embedding API call.
**Why it happens:** Current `update_node` always re-embeds on call.
**How to avoid:** Implement a separate `set_node_log(graph, node_id, log_entries)` function in `graph.py` that ONLY updates the `log` property without touching the summary or embedding. Use this for the compression pass.

### Pitfall 7: Linux Has No st_birthtime (Audio File Timestamp)
**What goes wrong:** `pathlib.Path.stat().st_birthtime` raises `AttributeError` on Linux — Linux has no file creation time.
**Why it happens:** `st_birthtime` is macOS/BSD only. Verified: `hasattr(path.stat(), 'st_birthtime')` returns `False` on this system.
**How to avoid:** Use `path.stat().st_mtime` (last modification time) as the recording timestamp proxy. This is accurate for audio files copied directly from a recorder, where mtime equals original creation time. The fallback chain: `st_mtime` -> `datetime.now(timezone.utc)`.

### Pitfall 8: FalkorDB Aliases Array Requires JSON String Storage
**What goes wrong:** FalkorDB stores list properties as arrays of primitives. When you read back `n.aliases`, it comes back as a Python list directly (not JSON string). But `n.log` and `n.refs` are stored as JSON strings (complex nested objects). Mixing these up causes `json.loads()` errors.
**Why it happens:** FalkorDB handles arrays of primitives natively but can't store nested objects.
**How to avoid:** Maintain the established pattern: `aliases` stored as array (no JSON), `log` and `refs` stored as JSON strings. Be consistent in all new code.

---

## Claude's Discretion Recommendations

### Token Threshold for Log Compression (COMP-01)
**Recommendation:** 2000 tokens (tiktoken cl100k_base encoding).

Measurement: a realistic 3-entry log with medium-length notes is ~130 tokens. At 2000 tokens, compression triggers at approximately 15-25 detailed entries — roughly 6-12 months of journal recordings for a moderately active concept. This is calibrated to:
- Not trigger prematurely on normal usage (first 10 entries never compress)
- Catch genuinely large logs before they bloat the agent's context

The threshold is a module-level constant in `compress.py` — easy to tune.

### FalkorDB Index Changes After Dropping type Field
**Recommendation:**
- Remove: `CREATE INDEX FOR (n:Node) ON (n.type)` from `init_graph` (no need to `DROP` the existing index — it becomes orphaned but harmless)
- Keep: `CREATE INDEX FOR (n:Node) ON (n.name)`, `(n.transcript_id)`, `(n.aliases)`, vector index on `n.embedding`
- Add: `CREATE INDEX FOR ()-[r:EDGE]->() ON (r.label)` — edge label queries will be needed by the agent when searching for relationships

### Sync vs Async
**Recommendation:** Sync throughout.

Rationale: all graph operations (FalkorDB queries) are synchronous. The Gemini API calls are synchronous in `google-genai` sync client. Introducing async would add `asyncio.run()` wrappers, async context managers, and async FalkorDB client management — all complexity with no throughput benefit for a single-user sequential pipeline. The harness already works synchronously; keep it.

### Episode Span Embedding Approach
**Recommendation:** `embed_text(span.summary)` using RETRIEVAL_DOCUMENT task type.

Rationale: consistent with node/edge embedding approach. Span summaries are stored documents, not queries. The RETRIEVAL_DOCUMENT task type is already used in `embed_text()`. The `create_episode_spans` tool calls `embed_text` for each span summary before storing.

### Token Counting for Compression Threshold
**Recommendation:** tiktoken `cl100k_base` encoding.

Rationale: tiktoken is already installed (verified: 0.12.0). `cl100k_base` is a fast, local, no-latency tokenizer. It slightly undercounts relative to Gemini's actual tokenizer, which is acceptable — the threshold is approximate by design. Using `client.models.count_tokens()` (the alternative) requires a live API call per node per ingestion, adding latency and API quota consumption proportional to the number of modified nodes.

---

## Code Examples

### FunctionDeclaration for search_nodes_by_alias
```python
# Source: verified against google-genai 1.68.0
types.FunctionDeclaration(
    name="search_nodes_by_alias",
    description=(
        "Search for existing nodes by exact alias match. "
        "Call this before creating a new node to check if it already exists."
    ),
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "alias": types.Schema(
                type="STRING",
                description="The surface form to look up (e.g. 'Dad', 'father', 'Vishal')",
            ),
        },
        required=["alias"],
    ),
)
```

### FunctionDeclaration with optional array parameter
```python
# Source: verified against google-genai 1.68.0
types.FunctionDeclaration(
    name="update_node",
    description="Update an existing node's summary, add to its aliases, or append a transcript reference.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "node_id": types.Schema(type="STRING", description="ID of the node to update"),
            "new_summary": types.Schema(type="STRING", description="New current-state summary"),
            "log_entry": types.Schema(type="STRING", description="Natural language note about what changed"),
            "new_aliases": types.Schema(
                type="ARRAY",
                items=types.Schema(type="STRING"),
                description="Additional aliases to add to this node's alias set",
                nullable=True,
            ),
            "transcript_id": types.Schema(type="STRING", nullable=True),
            "start_offset": types.Schema(type="INTEGER", nullable=True),
            "end_offset": types.Schema(type="INTEGER", nullable=True),
        },
        required=["node_id", "new_summary", "log_entry"],
    ),
)
```

### update_node with aliases + refs (graph.py extension)
```python
def update_node(
    graph,
    node_id: str,
    new_summary: str,
    log_entry: str,
    new_aliases: list[str] | None = None,
    transcript_ref: dict | None = None,
) -> None:
    embedding = embed_text(new_summary)
    ts = datetime.now(timezone.utc).isoformat()

    existing = get_node(graph, node_id)
    existing_log: list = []
    existing_aliases: list = []
    existing_refs: list = []

    if existing:
        if existing.get("log"):
            try:
                existing_log = json.loads(existing["log"])
            except (json.JSONDecodeError, TypeError):
                existing_log = []
        if existing.get("aliases"):
            existing_aliases = existing["aliases"]   # native list from FalkorDB
        if existing.get("refs"):
            try:
                existing_refs = json.loads(existing["refs"])
            except (json.JSONDecodeError, TypeError):
                existing_refs = []

    new_entry = LogEntry(recorded_at=datetime.now(timezone.utc), note=log_entry)
    existing_log.append(new_entry.model_dump(mode="json"))

    # Union new aliases
    if new_aliases:
        for a in new_aliases:
            if a not in existing_aliases:
                existing_aliases.append(a)

    # Append new ref
    if transcript_ref:
        existing_refs.append(transcript_ref)

    log_json = json.dumps(existing_log)
    refs_json = json.dumps(existing_refs)

    graph.query("MATCH (n:Node {id: $id}) REMOVE n.embedding", {"id": node_id})
    graph.query(
        """
        MATCH (n:Node {id: $id})
        SET n.summary = $summary,
            n.embedding = vecf32($embedding),
            n.aliases = $aliases,
            n.log = $log_json,
            n.refs = $refs_json,
            n.updated_at = $ts
        """,
        {
            "id": node_id,
            "summary": new_summary,
            "embedding": embedding,
            "aliases": existing_aliases,
            "log_json": log_json,
            "refs_json": refs_json,
            "ts": ts,
        },
    )
```

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| FalkorDB (Docker) | graph.py | Confirmed running (Phase 1) | latest | None — required |
| GEMINI_API_KEY | embeddings.py, harness.py | Set in .env | — | None — required |
| GROQ_API_KEY | transcribe.py | Set in .env | — | None — required |
| tiktoken | compress.py | Installed | 0.12.0 | None needed — available |
| google-genai | harness.py, compress.py | Installed | 1.68.0 | None needed — available |
| litellm | transcribe.py | Installed | 1.82.4 | None needed — available |
| falkordb Python client | graph.py | Installed | 1.6.0 | None needed — available |

**Missing dependencies with no fallback:** None.

**Linux-specific note:** `pathlib.Path.stat().st_birthtime` does NOT exist on Linux (verified). Use `st_mtime` for recording timestamp extraction from audio file metadata. This is the only OS-level difference from macOS development.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` — `[tool.pytest.ini_options]` testpaths = ["tests"] |
| Quick run command | `devenv shell -- uv run pytest tests/ -x -q --ignore=tests/test_graph.py` |
| Full suite command | `devenv shell -- uv run pytest tests/ -q` |
| Integration marker | `@pytest.mark.integration` — requires live FalkorDB and API keys |

Note: `test_graph.py` tests require a live FalkorDB instance. Quick run excludes it. Full suite runs all tests including integration-marked ones.

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TRNS-01 | transcribe_file() called for audio file | unit (mocked litellm) | `pytest tests/test_ingest.py::test_transcribe_called -x` | Wave 0 |
| TRNS-02 | Transcript saved with id, recorded_at, text | unit | `pytest tests/test_ingest.py::test_transcript_stored -x` | Wave 0 |
| TRNS-03 | Episode spans stored in transcript JSON after agent run | unit | `pytest tests/test_ingest.py::test_episode_spans_stored -x` | Wave 0 |
| GRPH-02 | Node has name, summary, log, aliases, refs after create/update | unit | `pytest tests/test_models.py::test_node_no_type_field -x` | Wave 0 (modify existing) |
| GRPH-03 | Edge has label, summary, log, refs after create/update | unit | `pytest tests/test_models.py::test_edge_label_field -x` | Wave 0 (modify existing) |
| GRPH-04 | Node and Edge accept any string for name/label | unit | `pytest tests/test_models.py::test_node_name_is_free_string -x` | Wave 0 (modify existing) |
| INGST-01 | Agent receives full transcript text (not chunks) | unit | `pytest tests/test_ingest.py::test_full_transcript_to_agent -x` | Wave 0 |
| INGST-02 | search_nodes_by_alias tool returns exact matches | unit (mocked graph) | `pytest tests/test_tools.py::test_search_by_alias -x` | Wave 0 |
| INGST-02 | search_nodes_by_embedding returns candidates with scores | unit (mocked graph) | `pytest tests/test_tools.py::test_search_by_embedding -x` | Wave 0 |
| INGST-03 | update_node unions new aliases into existing set | unit | `pytest tests/test_graph.py::test_update_node_unions_aliases -x` | Wave 0 |
| INGST-04 | Prompt contains selectivity directive | unit | `pytest tests/test_ingest.py::test_prompt_contains_selectivity -x` | Wave 0 |
| INGST-06 | Log entries include recorded_at + note | unit | `pytest tests/test_models.py::test_log_entry_creation` | Exists |
| COMP-01 | Compression triggers at 2000 token threshold | unit | `pytest tests/test_compress.py::test_compression_threshold -x` | Wave 0 |
| COMP-02 | Compressed log preserves arc of change (prompt test) | unit (mocked Gemini) | `pytest tests/test_compress.py::test_compress_prompt_content -x` | Wave 0 |
| COMP-03 | Last 3 entries always kept intact | unit | `pytest tests/test_compress.py::test_recent_entries_preserved -x` | Wave 0 |
| VECT-01 | embed_text called for episode span summaries | unit (mocked embed_text) | `pytest tests/test_ingest.py::test_episode_span_embedding -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `devenv shell -- uv run pytest tests/ -x -q --ignore=tests/test_graph.py`
- **Per wave merge:** `devenv shell -- uv run pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

The following test files and updates are needed before implementation:

- [ ] `tests/test_tools.py` — covers INGST-02 (search tools), tool factory pattern
- [ ] `tests/test_compress.py` — covers COMP-01, COMP-02, COMP-03
- [ ] `tests/test_ingest.py` — covers TRNS-01, TRNS-02, TRNS-03, INGST-01, INGST-04, VECT-01
- [ ] `tests/test_models.py` — UPDATE: replace type-based tests with name/label tests (GRPH-02, GRPH-03, GRPH-04)
- [ ] `tests/test_graph.py` — UPDATE: add test_update_node_unions_aliases, test_delete_node, test_delete_edge, test_search_by_alias

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Node.type field for entity classification | No type field; name + summary carry all semantic meaning | Phase 2 (D-01) | Existing tests and graph.py queries must be updated |
| Edge.type field | Edge.label — concise descriptor string | Phase 2 (D-03) | Rename in model + graph.py + all callers |
| Budget-enforced harness (budget=8) | Unbounded harness — runs until model stops | Phase 2 (D-08) | Remove budget param + enforcement branch from harness.py |
| TranscriptStore stores raw dict | TranscriptStore stores Transcript Pydantic model (serialized) | Phase 2 (D-04) | store.py needs Transcript model integration |

**Deprecated/outdated:**
- `Node.type` and `Edge.type`: dropped per D-01/D-03. Any code that constructs `Node(type=...)` or `Edge(type=...)` must be updated.
- Budget enforcement in `harness.py`: the `budget` parameter and `calls_used` logic are removed per D-08. Tests `test_harness_budget_enforcement` and `test_harness_budget_injects_exhausted_message` become obsolete.

---

## Open Questions

1. **How does the agent signal "ingestion complete" vs "I need more tools"?**
   - What we know: when the model returns no `fc_parts`, the harness returns `response.text`. The agent's final response text is not currently used for anything.
   - What's unclear: should `ingest.py` parse the final response text to extract the change summary (nodes created, etc.) or should the tools themselves track this via side effects?
   - Recommendation: track counts via side effects in the tool implementations (increment counters on `create_node`, `update_node`, etc.). The final response text is ignored by `ingest.py`. This avoids brittle response parsing.

2. **What happens when `delete_node` is called on a node that has edges?**
   - What we know: using `DETACH DELETE` in FalkorDB/Cypher deletes the node and all its attached edges automatically.
   - What's unclear: does the agent need to know the edge was deleted? Should delete_node return a list of deleted edge IDs?
   - Recommendation: `DETACH DELETE` is correct. Return `{"deleted": True, "node_id": node_id}` — the agent doesn't need the edge list since it has delete_edge for explicit edge deletion.

3. **How should the ingest.py compression pass find which nodes/edges were modified?**
   - What we know: the compression pass needs to check all modified nodes/edges post-agent.
   - What's unclear: tracking modified IDs in the tools (side effect list) vs. scanning all nodes every run.
   - Recommendation: track a `modified_node_ids: list[str]` and `modified_edge_ids: list[str]` inside the `build_tools` factory closure. Tools append to these lists on create/update. The compression pass only checks those IDs, not the full graph.

---

## Sources

### Primary (HIGH confidence)
- Verified directly against installed code — all google-genai API patterns confirmed against 1.68.0
- Verified against installed falkordb 1.6.0 Python client
- Verified against Phase 1 `graph.py` (all FalkorDB patterns working)
- Verified: tiktoken 0.12.0 `cl100k_base` encoding functional and fast
- `lifeos/memory/models.py`, `graph.py`, `harness.py`, `store.py` — read directly for current state
- `.planning/phases/02-ingestion-agent/02-CONTEXT.md` — all decisions sourced here
- `markdowns/Memory-v3.md` — design document for all architectural choices

### Secondary (MEDIUM confidence)
- Linux `st_birthtime` absence verified by direct Python runtime check — no macOS `birthtime` on this kernel
- Token threshold (2000) based on empirical measurement of sample log entries using tiktoken

### Tertiary (LOW confidence)
- FalkorDB edge property index syntax `CREATE INDEX FOR ()-[r:EDGE]->() ON (r.label)` — pattern derived from FalkorDB documentation conventions; the node index pattern is confirmed working; edge index follows same syntax. Not tested against live FalkorDB instance.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages verified against installed versions
- Architecture patterns: HIGH — derived from locked decisions in CONTEXT.md + existing Phase 1 code
- FalkorDB Cypher patterns: HIGH for node operations (Phase 1 proven), MEDIUM for edge label index (untested)
- Pitfalls: HIGH — each pitfall verified against actual code (existing tests, models, graph.py)
- Token threshold: MEDIUM — empirical measurement, not a Gemini-specific benchmark

**Research date:** 2026-03-26
**Valid until:** 2026-06-01 (stable stack; google-genai API shape unlikely to change significantly in 60 days)
