# Stack Research

**Domain:** AI voice journaling — Python agentic backend with semantic graph memory
**Researched:** 2026-04-01
**Confidence:** HIGH (primary sources: installed packages in `.devenv/state/venv`, `pyproject.toml`, `uv.lock`, and pre-reset source code recovered from git history which already validated most of these choices in production)

---

## Evidence Base

This project has already run a prior iteration (visible in git history through commit `e74f691`). That codebase reached a working state: transcription pipeline, FalkorDB graph layer with vector indexes, embedding via Gemini API, and a litellm-based agent harness were all operational. The current `pyproject.toml` and `uv.lock` preserve those decisions. The stack below reflects what the evidence shows was chosen and why it remains the correct v1 stack.

---

## Recommended Stack

### Core Technologies

| Technology      | Version (locked) | Purpose                                                        | Why Recommended                                                                                                                                                                                                                                                                                                            |
| --------------- | ---------------- | -------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `falkordb`      | 1.6.0            | Graph DB client — Cypher queries, vector index, node/edge CRUD | Project-committed. Supports `db.idx.vector.queryNodes` for semantic search over embedded summaries. `vecf32()` property type for native float vectors. Sync and async (`falkordb.asyncio`) APIs both available. Production-stable (Development Status: Production/Stable).                                                 |
| `litellm`       | 1.82.4           | Unified LLM + embedding interface                              | Single call interface across Gemini, OpenAI, Anthropic, and Groq. Handles `reasoning_effort` → `thinkingConfig.budget_tokens` translation for Gemini 2.5 models and surfaces `task_type` on embedding calls (required for `gemini-embedding-001` RETRIEVAL_DOCUMENT vs RETRIEVAL_QUERY distinction). Keeps every LLM call on the same interface required by the v1 design. |
| `pydantic`      | 2.12.5           | Data models for nodes, edges, log entries, tool call schemas   | V2 required. Tool call parsing and validation. `model_dump(mode="json")` for JSON serialization to FalkorDB string properties.                                                                                                                                                                                             |
| `python-dotenv` | 1.0.0            | Environment config loading                                     | Standard for `GEMINI_API_KEY`, `GROQ_API_KEY`, model override env vars.                                                                                                                                                                                                                                                    |
| `tiktoken`      | 0.12.0           | Token budget counting for log compression                      | Used to check whether a node's log exceeds the token budget before triggering compression. OpenAI-compatible tokenizer; reasonable proxy for Gemini context counting.                                                                                                                                                      |
| `pyyaml`        | 6.0.3            | Config / test fixture loading                                  | Used for test harness configuration and structured fixture files.                                                                                                                                                                                                                                                          |

### Transcription Stack

| Technology            | Version                       | Purpose                                              | Why Recommended                                                                                                                                                                                                                                                                                                                                            |
| --------------------- | ----------------------------- | ---------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `groq` (via litellm)  | `groq/whisper-large-v3-turbo` | Audio transcription with segment timestamps          | Groq runs Whisper inference on dedicated hardware at ~200x realtime speed. `whisper-large-v3-turbo` is the fastest large model with high accuracy. Returns `verbose_json` with `segments[]` each containing `start`, `end` (seconds), and `text`. The pre-reset codebase (`transcribe_batch.py`) already validated this pipeline against real audio files. |
| litellm transcription | 1.82.4                        | Thin adapter over `groq.audio.transcriptions.create` | `litellm.transcription(model="groq/whisper-large-v3-turbo", file=fp, response_format="verbose_json")` returns a `TranscriptionResponse` compatible with the existing pipeline and keeps transcription aligned with the same LiteLLM interface used elsewhere in the system.                                                                                   |

**On word-level vs segment-level timestamps:** Groq's `whisper-large-v3-turbo` supports `timestamp_granularities=["segment","word"]` via `verbose_json`. A live check in this workspace against `private/shania/shania_audio_diary/2021-01-01T00-00-00 01 - This diary belongs to.....mp3` returned both a populated `segments[]` array and a populated `words[]` array. Even so, Arakne should standardize on segment boundaries for transcript rendering and provenance because word-level granularity is unnecessary for the system design.

**Consequence:** Use segment `start`/`end` as `start_offset`/`end_offset` for provenance and render `[MM:SS]` markers from segment boundaries. Word-level timestamps are available but not required.

### Embedding Stack

| Technology                           | Version   | Purpose                                         | Why Recommended                                                                                                                                                                                                                                                                                                                                     |
| ------------------------------------ | --------- | ----------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `gemini-embedding-001` (via litellm) | API model | Node/edge summary embeddings + query embeddings | 3072-dimensional output matches the `OPTIONS {dimension:3072}` vector index already defined in `init_graph`. Requires `task_type` to distinguish RETRIEVAL_DOCUMENT (at index time) and RETRIEVAL_QUERY (at query time) — litellm passes this through. The pre-reset search experiments validated Gemini embeddings for journaling semantic search. |
| FalkorDB vector index                | (DB-side) | KNN search via `db.idx.vector.queryNodes`       | Native graph+vector in one query. No external vector DB needed. Eliminates dual-write synchronization problem. The Cypher procedure `CALL db.idx.vector.queryNodes('Node', 'embedding', $k, vecf32($embedding))` is already validated in the pre-reset graph layer.                                                                                 |

**On hybrid search:** `search_graph(query, limit)` in the spec means keyword + semantic fused. FalkorDB's range index on `Node.aliases` enables exact keyword match via `WHERE $alias IN n.aliases`. The pattern validated in the prior codebase: `search_nodes_by_alias` (Cypher `WHERE $alias IN n.aliases`) for keyword, `vector_search` (KNN procedure) for semantic, merged by the tool layer. No separate full-text search engine is needed for v1 at personal-scale data volumes.

### Agent Harness Stack

| Technology                         | Version | Purpose                                              | Why Recommended                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| ---------------------------------- | ------- | ---------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Custom agentic loop (no framework) | —       | Tool-calling loop for ingestion, query, theme agents | The prior codebase implemented this directly: `litellm.completion()` → parse `tool_calls` → dispatch → append to messages → loop until termination function or max iterations. This is ~80 lines of code. LangGraph (1.1.3, in lock file via langchain dependency) was available but not used — the harness requirements are simple enough that a direct loop is cleaner and more inspectable. Frameworks add routing complexity the architecture explicitly rejects. |
| `litellm.completion`               | 1.82.4  | LLM calls with tool schemas                          | `model`, `messages`, `tools` (OpenAI format), `reasoning_effort` → single unified call. `tool_choice="auto"` lets the model decide.                                                                                                                                                                                                                                                                                                                                   |

**On framework choice:** LangGraph, LangChain, PydanticAI, smolagents are all installed or available, but none were used in the prior iteration. The architecture explicitly states "the agent has full autonomy over which tools to call and when; no routing is hardcoded." Custom loops are better here because: (1) the harness owns token minting and provenance validation — not the model; (2) the termination condition is a specific tool call (`complete_ingestion`), not a message pattern; (3) the same loop serves three modes via system prompt swap. A framework would add indirection without benefit.

### Testing Stack

| Technology | Version | Purpose                        | Why Recommended                                                                                                                                                                                |
| ---------- | ------- | ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `pytest`   | 9.0.2+  | Unit + integration test runner | Standard. Integration tests marked with `@pytest.mark.integration` requiring live FalkorDB.                                                                                                    |
| `ragas`    | 0.4.3   | RAG/agent evaluation framework | Quantitative evaluation of query agent answer quality: answer relevancy, faithfulness, citation grounding. Already in pyproject — validates the agent's use of transcript spans for grounding. |

---

## Installation

```bash
# Core backend (already in pyproject.toml — use uv sync)
uv sync
```

---

## What NOT to Use

| Avoid                                           | Why                                                                                                                                                                                                                | Use Instead                                                               |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------- |
| `redisgraph-py`                                 | Deprecated. RedisGraph was archived in 2023. FalkorDB is the fork that continued development. `redisgraph-py` has no FalkorDB compatibility.                                                                       | `falkordb` 1.6.0                                                          |
| `langchain` as agent runtime                    | Installed as transitive dep but adds abstraction that obscures the token minting and provenance validation the harness must own. Prior iteration did not use it.                                                   | Custom litellm loop                                                       |
| `openai` Whisper API                            | Higher latency, higher cost than Groq for same model. Groq's hardware is purpose-built for Whisper inference.                                                                                                      | `groq/whisper-large-v3-turbo` via litellm                                 |
| Word-level timestamp dependence                 | Groq currently returns word-level timestamps, but making the system depend on them adds unnecessary precision and coupling.                                                               | Segment-level timestamps (`segments[].start`, `segments[].end`)           |
| Separate vector DB (Qdrant, Weaviate, Pinecone) | Dual-write synchronization with FalkorDB graph is a reliability hazard. Vectors stored out-of-graph can go stale when nodes are updated. FalkorDB's native vector index keeps embedding co-located with node data. | FalkorDB `VECTOR INDEX` + `db.idx.vector.queryNodes`                      |
| UUID-based node IDs                             | LLMs hallucinate UUIDs in tool arguments. High-entropy identifiers cause silent lookup failures. The spec explicitly chose sequential tokens (`node:N`).                                                           | Sequential readable tokens minted by the harness                          |
| Full graph survey in theme agent                | Theme agent receiving the full graph and re-evaluating everything will not scale past ~100 nodes. The spec is explicit: operate on delta only.                                                                     | Delta-only mode: `touched_nodes` + `touched_edges` from ingestion payload |

---

## Version Compatibility

| Package                | Compatible With                            | Notes                                                                                                                                           |
| ---------------------- | ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `falkordb==1.6.0`      | `redis>=7.1.0`                             | falkordb-py wraps redis-py; requires redis>=7.1 for connection pool API                                                                         |
| `falkordb==1.6.0`      | FalkorDB server `latest` Docker image      | Docker image pinned in devenv.nix as `falkordb/falkordb:latest` — should pin to a specific version tag in production to prevent schema drift    |
| `litellm==1.82.4`      | `openai>=2.8.0`                            | litellm requires openai>=2.8 as a runtime dep; openai 2.29.0 is in the lock file                                                                |
| `gemini-embedding-001` | `dimension: 3072` in FalkorDB vector index | Index must be created with `OPTIONS {dimension:3072, similarityFunction:'cosine'}`. Changing models requires dropping and recreating the index. |
| `pydantic==2.12.5`     | `litellm==1.82.4`                          | litellm requires `pydantic>=2.5.0,<3.0.0`; compatible                                                                                           |
| `ragas==0.4.3`         | `langchain` transitive deps                | ragas pulls in langchain; this is acceptable for eval runs only — do not import ragas in production agent code                                  |

---

## FalkorDB Client Specifics

The question about `redisgraph-py` vs `falkordb-py` is settled:

- **`redisgraph-py`**: Do not use. RedisGraph was sunset in 2023. The package is unmaintained and incompatible with FalkorDB's extended command set.
- **`falkordb`** (PyPI package `FalkorDB`): The official client. Package name on PyPI is `FalkorDB` (case-sensitive in install, lowercase in import: `from falkordb import FalkorDB`). Current version: **1.6.0**.

Key API facts verified from installed source:

- Sync: `FalkorDB(host, port)` → `db.select_graph(name)` → `graph.query(cypher, params)`
- Async: `from falkordb.asyncio import FalkorDB` — same interface, awaitable queries
- Vector index syntax: `CREATE VECTOR INDEX FOR (n:Label) ON (n.prop) OPTIONS {dimension:N, similarityFunction:'cosine'}`
- Vector query: `CALL db.idx.vector.queryNodes('Label', 'prop', $k, vecf32($embedding)) YIELD node, score`
- `vecf32($embedding)` wraps a Python `list[float]` as a 32-bit float vector property
- **Known quirk**: Updating a vector property requires `REMOVE n.embedding` before `SET n.embedding = vecf32(...)` — direct overwrite does not update the stored vector. This was discovered and fixed in the pre-reset codebase.

---

## Sources

- `/home/shivang/shivang/projs/arakne/pyproject.toml` — project dependencies, confirmed versions
- `/home/shivang/shivang/projs/arakne/uv.lock` — locked versions: falkordb 1.6.0, litellm 1.82.4, pydantic 2.12.5, openai 2.29.0, langgraph 1.1.3
- `/home/shivang/shivang/projs/arakne/.devenv/state/venv/lib/python3.12/site-packages/falkordb-1.6.0.dist-info/METADATA` — falkordb-py confirmed MIT, Python 3.10-3.14 support, redis>=7.1 dep — HIGH confidence
- `/home/shivang/shivang/projs/arakne/.example.env` — canonical env var documentation showing `groq/whisper-large-v3-turbo`, `gemini/gemini-2.5-flash`, `gemini/gemini-embedding-001` — HIGH confidence
- `git show 0883904:lifeos/memory/graph.py` — pre-reset FalkorDB graph layer with vector index, `vecf32` usage, and REMOVE-before-SET quirk — HIGH confidence (production-validated)
- `git show 0883904:lifeos/core/embeddings.py` — litellm embedding calls with `task_type` — HIGH confidence
- `git show 0883904:lifeos/core/config.py` — full config schema, confirming all stack decisions — HIGH confidence
- `git show 8b87507:transcribe_batch.py` — Groq Whisper API usage via `groq` SDK — HIGH confidence
- `git show e872282:pyproject.toml` — search experiments used `chromadb` + `google-genai` directly; `falkordb` native vector supersedes this — HIGH confidence
- Live workspace experiment on `private/shania/shania_audio_diary/2021-01-01T00-00-00 01 - This diary belongs to.....mp3` via Groq's OpenAI-compatible transcription API — confirmed both `segments[]` and `words[]` are populated for `whisper-large-v3-turbo`
