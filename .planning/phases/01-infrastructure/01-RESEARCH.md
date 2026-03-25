# Phase 1: Infrastructure - Research

**Researched:** 2026-03-25
**Domain:** Python project scaffold, FalkorDB graph+vector storage, google-genai function calling harness, Groq Whisper client
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Package + scripts layout: `lifeos/` Python package with submodules (`agent/`, `memory/`, `core/`) + top-level `scripts/` directory for experiment entry points
- **D-02:** Agent system prompts live as markdown files in `prompts/` directory (ingest.md, query.md, memo.md) — easy to edit and iterate without touching Python code
- **D-03:** Move existing `helpers/transcribe_batch.py` into the new structure (likely `scripts/transcribe.py` or `lifeos/core/transcribe.py`)
- **D-04:** Minimal Pydantic models — enforce only structural requirements: id, summary, log[], aliases[], refs[]. Type field is a free string. No enum constraints. Follows the Bitter Lesson: minimal schema, maximum LLM flexibility.
- **D-05:** Transcripts stored as JSON files on disk (not in FalkorDB) — simpler, aligns with existing transcribe_batch.py output pattern. Graph nodes reference transcripts by ID; a transcript store module handles file I/O.
- **D-06:** Manual dispatch loop — roll our own: send prompt to Gemini, parse response, check for tool calls, dispatch to registered tool functions, feed results back. More control than the SDK's built-in FC loop, easier to enforce budget and add instrumentation.
- **D-07:** Tools registered as a dict mapping tool names to Python callables. FunctionDeclarations sent to Gemini so it knows the tool schemas.
- **D-08:** Tool-call budget enforcement: counter in the harness loop. When budget is exhausted, Claude has discretion on whether to force a final answer via system message injection or hard cutoff — pick what gives best answers under pressure.
- **D-09:** Remove `chromadb` and `chonkie` from pyproject.toml — FalkorDB handles vectors natively, and there's no chunking step (full transcripts to agent). Run `uv sync` after cleanup.

### Claude's Discretion

- Budget enforcement mechanism (force final answer vs hard cutoff) — Claude picks what gives best results
- Exact FalkorDB index set (research says: name, aliases, type, transcript_id at minimum)
- Config module design (how .env vars are loaded and shared across modules)
- Whether to use async or sync for the harness loop

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INFR-01 | Python project with uv, ruff, devenv — no global package installs | devenv.nix already has Python+uv wired; pyproject.toml needs chromadb/chonkie removed; ruff added as dev dep |
| INFR-02 | Environment config via .env (GEMINI_API_KEY, GROQ_API_KEY) | python-dotenv already in lock; pattern established in transcribe_batch.py |
| INFR-03 | FalkorDB running via Docker in devenv, with index creation at initialization | devenv.nix process already defined; CREATE INDEX and CREATE VECTOR INDEX syntax confirmed |
| INFR-04 | Runnable Python scripts for each workflow (ingest, query, memo, eval) — no API, no CLI | scripts/ directory as entry points per D-01; stubs sufficient for Phase 1 |
| GRPH-01 | FalkorDB graph store initialized with proper indexes on frequently queried properties | Four range indexes (name, aliases, type, transcript_id) + one vector index on summary embedding |
| GRPH-05 | Atomic update operations: updating a node/edge summary always re-embeds in the same operation | Single `update_node` / `update_edge` function; never expose separate summary and embedding update paths |
| HARN-01 | Single modular harness with agentic loop (LLM + tools + role-specific system prompt) | Manual dispatch loop using google-genai 1.x function calling; ~60 lines of Python |
| HARN-03 | Hard tool-call budget enforced in harness code — agent forced to answer/complete after budget exhausted | Counter in loop; inject "budget exhausted" system turn to force final answer |
</phase_requirements>

---

## Summary

Phase 1 establishes the three foundational pillars that all subsequent phases build on: (1) a clean Python package structure with the unwanted dependencies removed, (2) a FalkorDB graph store properly initialized with range and vector indexes so queries never silently full-scan, and (3) an agent harness skeleton with a hard tool-call budget baked in from the start.

The project already has a working devenv.nix with FalkorDB Docker defined and a working transcribe_batch.py that establishes the env-loading pattern. The main work is structural: reorganizing code into the `lifeos/` package, creating the FalkorDB init module with correct index DDL, building the Pydantic models that the graph layer will use, writing the harness loop, and confirming both the Gemini and Groq clients respond to a live call.

The most technically precise areas are the FalkorDB index syntax (which has no auto-creation) and the google-genai 1.x function-calling wire format (function call `id` must be round-tripped in the response part). Both are documented with confirmed syntax below.

**Primary recommendation:** Build bottom-up — models and FalkorDB init first, then atomic storage ops, then harness loop, then client smoke tests. This order means every higher layer has a working foundation.

---

## Project Constraints (from CLAUDE.md)

Directives that the planner MUST comply with:

| Directive | Source | Implication for Phase 1 |
|-----------|--------|--------------------------|
| No global package managers (apt, pip, npm -g) | Global CLAUDE.md | All deps via `uv`; devenv shell for all commands |
| Use `devenv` for project environment | Global CLAUDE.md | `devenv shell -- python scripts/...` is the run pattern |
| Python: use `uv`, linting: `ruff` | Global CLAUDE.md | `ruff` must be added to pyproject.toml dev deps |
| NixOS — no system package installs | Global CLAUDE.md | Anything new goes in devenv.nix or pyproject.toml |
| Tech stack decided: FalkorDB, Gemini 2.5 Flash, Groq Whisper, gemini-embedding-001 | Project CLAUDE.md | No substitutions; these are locked |
| No rigid schema — LLM defines node/edge types | Project CLAUDE.md | Pydantic models must NOT have enum constraints on type field |
| Single agent harness with role-specific prompts | Project CLAUDE.md | One harness class/function, not separate ingestion/query/memo agents |
| GSD workflow enforcement | Project CLAUDE.md | All file changes through GSD commands |

---

## Standard Stack

### Core (all already in pyproject.toml / uv.lock)

| Library | Confirmed Version | Purpose | Notes |
|---------|-------------------|---------|-------|
| falkordb | 1.6.0 (pypi 2026-02-21) | Graph store + vector index | Redis-wire-compatible; `FalkorDB(host, port)` → `select_graph(name)` |
| google-genai | 1.68.0 | Gemini 2.5 Flash completions + embeddings | `genai.Client()` with `GEMINI_API_KEY`; function calling via `types.Tool` |
| litellm | 1.82.4 | Groq Whisper transcription | `litellm.transcription(model="groq/whisper-large-v3-turbo", ...)` |
| pydantic | 2.12.5 | Node/Edge/Transcript models | v2 style; BaseModel with field validators |
| python-dotenv | 1.2.2 | .env loading | `load_dotenv(PROJECT_ROOT / ".env")` pattern already established |
| pyyaml | 6.0.3 | Prompt template loading | Load `prompts/*.md` or `.yaml` config |

### To Remove (D-09)

| Library | Why Removing |
|---------|-------------|
| chromadb 1.5.5 | FalkorDB handles vectors natively; no separate vector DB |
| chonkie 1.6.1 | No chunking step in this architecture |

**After removing from pyproject.toml:** `uv sync` will clean the venv.

### Dev Tools to Add

| Tool | How to Add | Purpose |
|------|-----------|---------|
| ruff | `uv add --dev ruff` | Linting + formatting (CLAUDE.md required) |

### Installation (cleanup + add ruff)

```bash
# Remove chromadb and chonkie from pyproject.toml first, then:
uv remove chromadb chonkie
uv add --dev ruff
uv sync
```

---

## Architecture Patterns

### Recommended Project Structure

```
lifeos/                      # Python package (installable via uv)
├── __init__.py
├── agent/
│   ├── __init__.py
│   └── harness.py           # AgentHarness — the loop, tool dispatch, budget enforcement
├── memory/
│   ├── __init__.py
│   ├── graph.py             # FalkorDB init, CRUD, index creation
│   ├── models.py            # Pydantic models: Node, Edge, TranscriptRef
│   └── store.py             # Transcript JSON file I/O
└── core/
    ├── __init__.py
    ├── config.py            # load_dotenv, expose typed config values
    ├── embeddings.py        # embed_text(), embed_batch() via gemini-embedding-001
    └── transcribe.py        # moved from helpers/transcribe_batch.py

prompts/
├── ingest.md
├── query.md
└── memo.md

scripts/
├── ingest.py                # Entry point: load transcript → run ingestion agent
├── query.py                 # Entry point: accept question → run query agent
├── memo.py                  # Entry point: run memo agent
└── eval.py                  # Entry point: run RAGAS eval
```

### Pattern 1: FalkorDB Graph Initialization

**What:** Create the graph connection and all indexes at startup; idempotent (safe to re-run).
**When to use:** Called once at application start or in the init script.

```python
# Source: https://docs.falkordb.com/cypher/indexing/range-index.html
#         https://docs.falkordb.com/cypher/indexing/vector-index
from falkordb import FalkorDB

def init_graph(host: str = "localhost", port: int = 6379, graph_name: str = "lifeos"):
    db = FalkorDB(host=host, port=port)
    graph = db.select_graph(graph_name)

    # Range indexes — safe to run even if they already exist
    for label, prop in [
        ("Node", "name"),
        ("Node", "type"),
        ("Node", "transcript_id"),
    ]:
        graph.query(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")

    # aliases is an array property — index for membership checks
    graph.query("CREATE INDEX FOR (n:Node) ON (n.aliases)")

    # Vector index on node summary embedding (3072 dims, cosine similarity)
    # gemini-embedding-001 outputs 3072 dims by default; pre-normalized at 3072
    graph.query("""
        CREATE VECTOR INDEX FOR (n:Node) ON (n.embedding)
        OPTIONS {dimension:3072, similarityFunction:'cosine'}
    """)

    return graph
```

**Important:** FalkorDB has NO auto-indexing. If the index already exists, `CREATE INDEX` raises no error — it is idempotent.

### Pattern 2: Atomic Node Update (GRPH-05)

**What:** Updating a node's summary always re-embeds in the same Python function call. There is no separate "update embedding" operation exposed to callers.
**When to use:** Any time node or edge summary changes.

```python
# Source: PITFALLS.md — Pitfall 7: Stale Embeddings
from lifeos.core.embeddings import embed_text
from datetime import datetime, timezone

def update_node(graph, node_id: str, new_summary: str, log_entry: str, transcript_ref: dict):
    embedding = embed_text(new_summary)   # always re-embed
    timestamp = datetime.now(timezone.utc).isoformat()
    graph.query(
        """
        MATCH (n:Node {id: $id})
        SET n.summary = $summary,
            n.embedding = vecf32($embedding),
            n.updated_at = $ts
        WITH n
        SET n.log = n.log + [$log_entry]
        """,
        {
            "id": node_id,
            "summary": new_summary,
            "embedding": embedding,
            "ts": timestamp,
            "log_entry": log_entry,
        }
    )
```

**Key:** `embed_text` and the Cypher SET happen in the same function. Callers never call `embed_text` directly on a node summary.

### Pattern 3: Agent Harness Loop (HARN-01, HARN-03)

**What:** Manual dispatch loop — send to Gemini, check for function calls, dispatch, feed results back. Hard tool-call budget enforced by counter.
**When to use:** All three agent roles (ingest, query, memo) use this same harness with different system prompts and tool sets.

```python
# Source: https://ai.google.dev/gemini-api/docs/function-calling
from google import genai
from google.genai import types

class AgentHarness:
    def __init__(self, model: str, tools: dict[str, callable], declarations: list, budget: int = 8):
        self.client = genai.Client()
        self.model = model
        self.tools = tools               # name -> callable
        self.declarations = declarations # list of FunctionDeclaration
        self.budget = budget

    def run(self, system_prompt: str, user_message: str) -> str:
        tool_config = types.Tool(function_declarations=self.declarations)
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[tool_config],
        )
        contents = [types.Content(role="user", parts=[types.Part(text=user_message)])]
        calls_used = 0

        while True:
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )
            contents.append(response.candidates[0].content)

            # Check for function calls in ALL parts (not just parts[0])
            fc_parts = [p for p in response.candidates[0].content.parts if p.function_call]

            if not fc_parts:
                # No tool calls — model is done
                return response.text

            if calls_used >= self.budget:
                # Budget exhausted — inject system message to force final answer
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(text=(
                        "Tool call budget exhausted. You must now provide your final answer "
                        "based only on what you have retrieved so far. Do not request more tools."
                    ))]
                ))
                final = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(system_instruction=system_prompt),
                )
                return final.text

            # Dispatch all function calls in this turn
            response_parts = []
            for part in fc_parts:
                fc = part.function_call
                result = self.tools[fc.name](**fc.args)
                calls_used += 1
                response_parts.append(
                    types.Part.from_function_response(
                        name=fc.name,
                        response={"result": result},
                        id=fc.id,   # REQUIRED — maps response to call
                    )
                )

            contents.append(types.Content(role="user", parts=response_parts))
```

**Budget mechanism:** "Force final answer" (inject a turn telling the model to stop requesting tools) is preferred over hard cutoff. Hard cutoff returns nothing if the model is mid-reasoning. Forcing a final answer guarantees a usable response even if tool calls ran dry.

**Note on `fc.id`:** The `id` field from the `FunctionCall` must be echoed back in `Part.from_function_response`. Omitting it causes the SDK to fail response mapping. (Source: official function calling docs.)

**Note on iterating parts:** Do NOT assume `parts[0]` is the function call. A single response turn can contain mixed parts (text + function calls). Always iterate `response.candidates[0].content.parts` and filter by `p.function_call`.

### Pattern 4: Gemini Embeddings

**What:** Call gemini-embedding-001 with `RETRIEVAL_DOCUMENT` task type for storage, `RETRIEVAL_QUERY` for queries.

```python
# Source: https://ai.google.dev/gemini-api/docs/embeddings
from google import genai
from google.genai import types

_client = None

def get_client():
    global _client
    if _client is None:
        _client = genai.Client()
    return _client

def embed_text(text: str) -> list[float]:
    """Returns 3072-dimensional embedding vector."""
    result = get_client().models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
    )
    return result.embeddings[0].values

def embed_query(text: str) -> list[float]:
    """For query-time embedding (different task type improves retrieval quality)."""
    result = get_client().models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
    )
    return result.embeddings[0].values
```

**Dimension note:** gemini-embedding-001 default output is 3072 dimensions. The API pre-normalizes 3072-dim vectors. If using a smaller dimension (768 or 1536 via `output_dimensionality`), you must normalize before computing cosine similarity. For simplicity, use 3072 throughout Phase 1.

### Pattern 5: Pydantic Models

**What:** Minimal structural models. Type is a free string per D-04 and the Bitter Lesson.

```python
from pydantic import BaseModel, Field
from datetime import datetime

class TranscriptRef(BaseModel):
    transcript_id: str
    start_offset: int | None = None
    end_offset: int | None = None

class LogEntry(BaseModel):
    recorded_at: datetime           # recording timestamp, not wall clock
    note: str                       # LLM-written natural language note

class Node(BaseModel):
    id: str
    type: str                       # free string — NO enum constraint
    summary: str
    aliases: list[str] = Field(default_factory=list)
    log: list[LogEntry] = Field(default_factory=list)
    refs: list[TranscriptRef] = Field(default_factory=list)
    embedding: list[float] | None = None

class Edge(BaseModel):
    id: str
    type: str                       # free string
    source_id: str
    target_id: str
    summary: str
    log: list[LogEntry] = Field(default_factory=list)
    refs: list[TranscriptRef] = Field(default_factory=list)
    embedding: list[float] | None = None
```

### Anti-Patterns to Avoid

- **Separate embed step:** Never expose `update_summary()` without also calling `embed_text()`. Always atomic.
- **Assuming indexes exist:** FalkorDB has zero auto-indexing. Any query on `name`, `aliases`, `type`, `transcript_id` will full-scan without explicit `CREATE INDEX`.
- **`parts[0].function_call`:** Gemini can return mixed parts in one turn. Always iterate all parts.
- **Skipping `fc.id` in function response:** The SDK requires the `id` field to map tool results back to the originating function call.
- **Using LangChain/LangGraph for harness logic:** These are transitive deps pulled in by RAGAS. Don't build on them — use google-genai directly.
- **Type-constraining node type field:** No enum. The whole design depends on the LLM choosing types freely.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Vector similarity search | Custom KNN loop in Python | FalkorDB `CALL db.idx.vector.queryNodes(...)` | Native C implementation; handles large graphs; Cypher composable |
| Embedding generation | Local sentence-transformers | `gemini-embedding-001` via google-genai | Decided stack; higher quality; consistent with LLM reasoning model |
| Function calling dispatch | Parsing raw JSON responses | `types.Part.from_function_response` + `response.function_calls` | SDK handles serialization, ID mapping, and type coercion |
| .env loading | Manual `os.environ` reads | `python-dotenv` `load_dotenv()` | Already in stack; handles path resolution correctly |
| Graph schema validation | Hardcoded entity type checks | None — let LLM set type freely | Violates Bitter Lesson; contradicts GRPH-04 |

**Key insight:** FalkorDB's native vector index means every graph write and vector similarity search happen in the same store, enabling hybrid Cypher queries later (Phase 3) without any cross-store joins.

---

## Common Pitfalls

### Pitfall 1: FalkorDB Silent Full Scans (CRITICAL for Phase 1)

**What goes wrong:** Queries on `name`, `aliases`, `type`, or `transcript_id` silently full-scan the graph. Works fine at 10 nodes, catastrophic at 10,000.
**Why it happens:** FalkorDB has no auto-indexing. The developer writes queries that work and assumes indexes exist.
**How to avoid:** `init_graph()` function creates all indexes at startup. Called before any other graph operation. Use `graph.explain(query)` to verify "Index Scan" appears in the plan.
**Warning signs:** Query latency grows linearly with node count on simple property lookups.

### Pitfall 2: Stale Embeddings (CRITICAL for Phase 1)

**What goes wrong:** `update_node` updates the summary but not the embedding. Vector search returns nodes whose summaries don't match the query.
**Why it happens:** Summary update and embedding update are separate operations; one is forgotten.
**How to avoid:** Single `update_node()` function that always calls `embed_text()` and writes both `summary` and `embedding` in the same Cypher SET. Never expose a summary-only update.
**Warning signs:** After updating a node, `db.idx.vector.queryNodes` for the new summary text does not return that node in top results.

### Pitfall 3: Missing `fc.id` in Function Response

**What goes wrong:** SDK raises a mapping error or silently drops tool results when `id` is omitted from `Part.from_function_response`.
**Why it happens:** The `id` field is not obvious from looking at the FunctionCall object; many examples omit it.
**How to avoid:** Always: `types.Part.from_function_response(name=fc.name, response=..., id=fc.id)`.
**Warning signs:** Harness loop produces errors or the model ignores tool results.

### Pitfall 4: Assuming `parts[0]` Is the Function Call

**What goes wrong:** Harness misses tool calls when Gemini returns mixed parts (text + function call) in one response turn.
**Why it happens:** Simple examples only show single-part responses.
**How to avoid:** Always: `fc_parts = [p for p in response.candidates[0].content.parts if p.function_call]`.
**Warning signs:** Agent appears to "ignore" tool calls; answers are unexpectedly shallow.

### Pitfall 5: devenv vs direct python

**What goes wrong:** Running `python scripts/ingest.py` directly (outside devenv) fails because the venv is not active and FalkorDB / google-genai are not on PATH.
**Why it happens:** Developers muscle-memory `python` directly.
**How to avoid:** All run instructions must use `devenv shell -- python scripts/ingest.py`. The `.envrc` / direnv integration may auto-activate but is not guaranteed.
**Warning signs:** `ModuleNotFoundError: No module named 'falkordb'` (confirmed — this happened in research).

### Pitfall 6: Embedding Dimension Mismatch

**What goes wrong:** FalkorDB vector index is created with a specific dimension. Storing an embedding of a different dimension raises a type error or silently truncates.
**Why it happens:** The dimension parameter in `CREATE VECTOR INDEX` must exactly match the embedding output size.
**How to avoid:** Use `dimension:3072` in the index DDL. gemini-embedding-001 default output is 3072. If you need to reduce dimensions, set `output_dimensionality` in `EmbedContentConfig` AND update the index DDL to match.
**Warning signs:** FalkorDB raises an error on `SET n.embedding = vecf32(...)` with mismatched length.

---

## Code Examples

### FalkorDB Vector KNN Search

```cypher
-- Source: https://docs.falkordb.com/cypher/indexing/vector-index
CALL db.idx.vector.queryNodes('Node', 'embedding', 5, vecf32($query_embedding))
YIELD node, score
RETURN node.id, node.summary, score
ORDER BY score DESC
```

```python
results = graph.query(
    "CALL db.idx.vector.queryNodes('Node', 'embedding', $k, vecf32($embedding)) "
    "YIELD node, score RETURN node.id, node.summary, score",
    {"k": 5, "embedding": query_vec}
)
```

### FalkorDB Index Verification

```python
# Verify index usage — look for "Index Scan" in the plan output
plan = graph.explain("MATCH (n:Node) WHERE n.name = 'test' RETURN n")
print(plan)
# Expected: "... | Index Scan | (n:Node) ..."
```

### Groq Whisper via litellm

```python
# Source: helpers/transcribe_batch.py (verified working)
import litellm
litellm.drop_params = True

response = litellm.transcription(
    file=open("audio.m4a", "rb"),
    model="groq/whisper-large-v3-turbo",
    response_format="verbose_json",
    temperature=0,
)
text = response.text
```

### Gemini Client Smoke Test

```python
from google import genai
from lifeos.core.config import get_config

cfg = get_config()
client = genai.Client()
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Say hello in one sentence.",
)
print(response.text)
```

---

## State of the Art

| Old Approach | Current Approach | Applies To |
|--------------|------------------|------------|
| `google.generativeai` (old SDK) | `google.genai` (unified SDK 1.x) | All Gemini calls |
| `CREATE INDEX ON :Label(prop)` syntax | `CREATE INDEX FOR (n:Label) ON (n.prop)` | FalkorDB index creation (both work but modern form preferred) |
| `types.FunctionDeclaration` as dict | `types.Tool(function_declarations=[...])` | Function calling config |
| Pass Python function directly to `tools=` | Explicit `FunctionDeclaration` list | Phase 1 uses explicit declarations for harness control |

**Deprecated/outdated:**
- `google.generativeai` module: replaced by `google.genai` in SDK 1.x. Do NOT use the old module.
- LangChain function-calling wrappers: pulled in as RAGAS transitive dep but must not be used for harness logic.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | All scripts | Yes | 3.12.12 | — |
| Docker | FalkorDB process in devenv | Yes | 28.5.2 | — |
| devenv | Environment management | Yes | 2.0.4 | — |
| uv | Package management | Yes (via devenv) | — | — |
| FalkorDB Docker image | INFR-03 | Pulled on `devenv up` | `latest` | — |
| GEMINI_API_KEY | Gemini completions + embeddings | In .env (confirmed by .example.env) | — | — |
| GROQ_API_KEY | Groq Whisper transcription | In .env (confirmed by .example.env) | — | — |

**Missing dependencies with no fallback:** None — all required tools are available.

**Infra gap from STATE.md:** "Confirm pulled FalkorDB Docker image version supports native vector indexes before Phase 1 closes." The vector index feature was present in the documented latest image. The `CREATE VECTOR INDEX` syntax is in the current official docs. Verification step: run `CREATE VECTOR INDEX FOR (n:TestNode) ON (n.emb) OPTIONS {dimension:4, similarityFunction:'cosine'}` after `devenv up` and confirm no error.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (to be added) |
| Config file | None — Wave 0 creates `pyproject.toml` `[tool.pytest.ini_options]` section |
| Quick run command | `devenv shell -- python -m pytest tests/ -x -q` |
| Full suite command | `devenv shell -- python -m pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFR-01 | `import lifeos` works; ruff reports no errors | smoke | `devenv shell -- python -c "import lifeos"` | No — Wave 0 |
| INFR-02 | `get_config()` returns populated Gemini/Groq keys | unit | `pytest tests/test_config.py -x` | No — Wave 0 |
| INFR-03 | FalkorDB connection succeeds; indexes exist on startup | integration | `pytest tests/test_graph.py::test_init_graph -x` | No — Wave 0 |
| INFR-04 | Script stubs importable and runnable with `--help` / no-op | smoke | `devenv shell -- python scripts/ingest.py` | No — Wave 0 |
| GRPH-01 | `graph.explain(name_query)` shows "Index Scan" | integration | `pytest tests/test_graph.py::test_indexes -x` | No — Wave 0 |
| GRPH-05 | After `update_node(...)`, vector KNN returns that node | integration | `pytest tests/test_graph.py::test_atomic_update -x` | No — Wave 0 |
| HARN-01 | Harness runs with mock tools and returns a string | unit | `pytest tests/test_harness.py::test_run -x` | No — Wave 0 |
| HARN-03 | Harness stops after N tool calls even if model requests more | unit | `pytest tests/test_harness.py::test_budget -x` | No — Wave 0 |

### Sampling Rate

- **Per task commit:** `devenv shell -- python -m pytest tests/ -x -q`
- **Per wave merge:** `devenv shell -- python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/__init__.py` — empty, marks tests as package
- [ ] `tests/conftest.py` — shared fixtures: `graph_fixture` (temp FalkorDB graph), `mock_genai_client`
- [ ] `tests/test_config.py` — covers INFR-02
- [ ] `tests/test_graph.py` — covers INFR-03, GRPH-01, GRPH-05
- [ ] `tests/test_harness.py` — covers HARN-01, HARN-03
- [ ] Framework install: `uv add --dev pytest` — pytest not yet in pyproject.toml

---

## Open Questions

1. **FalkorDB `aliases` array property indexing**
   - What we know: FalkorDB range index on array properties is supported (`CREATE INDEX FOR (n:Node) ON (n.aliases)`)
   - What's unclear: Whether membership queries (`WHERE $alias IN n.aliases`) use the array index or full-scan
   - Recommendation: After Phase 1 creates the index, run `EXPLAIN` on an alias lookup and verify "Index Scan" appears. If not, add a separate `alias_set` fulltext index.

2. **FalkorDB `latest` Docker tag version**
   - What we know: Vector index syntax is in the current docs; the image is defined in devenv.nix as `latest`
   - What's unclear: The exact image version that will be pulled
   - Recommendation: Pin the FalkorDB Docker image to a specific version tag (e.g., `falkordb/falkordb:v4.x.x`) after confirming vector index works in Phase 1, to prevent silent breakage from upstream updates.

3. **Async vs sync harness loop**
   - What we know: Claude has discretion (D-08 area). google-genai 1.x supports both sync (`client.models.generate_content`) and async (`await client.aio.models.generate_content`)
   - What's unclear: Whether Phase 2+ will need concurrent ingestion
   - Recommendation: Start with sync. Phase 1 is experimental scripts, not a server. Async adds complexity with no Phase 1 benefit.

---

## Sources

### Primary (HIGH confidence)

- FalkorDB range index docs — `CREATE INDEX FOR (n:Label) ON (n.prop)` syntax confirmed
  https://docs.falkordb.com/cypher/indexing/range-index.html
- FalkorDB vector index docs — `CREATE VECTOR INDEX`, KNN query procedure confirmed
  https://docs.falkordb.com/cypher/indexing/vector-index
- FalkorDB Python client getting started — connection and graph.query() pattern confirmed
  https://docs.falkordb.com/getting-started/
- Google Gemini function calling docs — `types.Tool`, `types.Part.from_function_response`, `fc.id` pattern confirmed
  https://ai.google.dev/gemini-api/docs/function-calling
- Google Gemini embeddings docs — `client.models.embed_content`, task types confirmed
  https://ai.google.dev/gemini-api/docs/embeddings
- gemini-embedding-001 model card — 3072 default dimensions, MRL technique, normalization note confirmed
  https://ai.google.dev/gemini-api/docs/models/gemini-embedding-001
- Existing project files: `helpers/transcribe_batch.py`, `devenv.nix`, `pyproject.toml`, `uv.lock`
- `.planning/research/PITFALLS.md` — FalkorDB full scan and stale embedding pitfalls (HIGH, prior research)
- `.planning/research/STACK.md` — Confirmed stack with versions (HIGH, prior research)

### Secondary (MEDIUM confidence)

- WebSearch: gemini-embedding-001 dimension = 3072 default — confirmed by multiple sources including official blog post

### Tertiary (LOW confidence)

- FalkorDB `aliases` array index membership query behavior — not confirmed via EXPLAIN; flag for Phase 1 verification

---

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — all versions confirmed from uv.lock (installed); APIs confirmed from official docs
- Architecture: HIGH — project structure per locked decisions D-01..D-09; FalkorDB and google-genai patterns confirmed from official docs
- Pitfalls: HIGH — FalkorDB full scan and stale embedding pitfalls confirmed from official docs + prior research; harness pitfalls confirmed from SDK docs
- Validation: MEDIUM — pytest patterns are standard; FalkorDB integration tests require live Docker for INFR-03/GRPH-01/GRPH-05

**Research date:** 2026-03-25
**Valid until:** 2026-04-24 (30 days — stable libraries)
