# Stack Research

**Domain:** AI voice journaling — Python agentic backend with semantic graph memory
**Researched:** 2026-04-01
**Confidence:** HIGH (primary sources: installed packages in `.devenv/state/venv`, `pyproject.toml`, `uv.lock`, and pre-reset source code recovered from git history which already validated most of these choices in production)

---

## Evidence Base

This project has already run a prior iteration (visible in git history through commit `e74f691`). That codebase reached a working state: transcription pipeline, FalkorDB graph layer with vector indexes, embedding via Gemini API, and a litellm-based agent harness were all operational. The current `pyproject.toml` and `uv.lock` preserve those decisions. The stack below reflects what the evidence shows was chosen, why it was chosen, and where new decisions are needed.

---

## Recommended Stack

### Core Technologies

| Technology      | Version (locked) | Purpose                                                        | Why Recommended                                                                                                                                                                                                                                                                                                            |
| --------------- | ---------------- | -------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `falkordb`      | 1.6.0            | Graph DB client — Cypher queries, vector index, node/edge CRUD | Project-committed. Supports `db.idx.vector.queryNodes` for semantic search over embedded summaries. `vecf32()` property type for native float vectors. Sync and async (`falkordb.asyncio`) APIs both available. Production-stable (Development Status: Production/Stable).                                                 |
| `litellm`       | 1.82.4           | Unified LLM + embedding interface                              | Single call interface across Gemini, OpenAI, Anthropic, Groq. Handles `reasoning_effort` → `thinkingConfig.budget_tokens` translation for Gemini 2.5 models. Surfaces `task_type` on embedding calls (required for `gemini-embedding-001` RETRIEVAL_DOCUMENT vs RETRIEVAL_QUERY distinction). Eliminates provider lock-in. |
| `google-genai`  | 1.68.0           | Gemini SDK (fallback/direct access)                            | Already installed as transitive dep. Use litellm as primary interface; this provides direct SDK access if needed for features not yet in litellm.                                                                                                                                                                          |
| `pydantic`      | 2.12.5           | Data models for nodes, edges, log entries, tool call schemas   | V2 required. Tool call parsing and validation. `model_dump(mode="json")` for JSON serialization to FalkorDB string properties.                                                                                                                                                                                             |
| `python-dotenv` | 1.0.0            | Environment config loading                                     | Standard for `GEMINI_API_KEY`, `GROQ_API_KEY`, model override env vars.                                                                                                                                                                                                                                                    |
| `tiktoken`      | 0.12.0           | Token budget counting for log compression                      | Used to check whether a node's log exceeds the token budget before triggering compression. OpenAI-compatible tokenizer; reasonable proxy for Gemini context counting.                                                                                                                                                      |
| `pyyaml`        | 6.0.3            | Config / test fixture loading                                  | Used for test harness configuration and structured fixture files.                                                                                                                                                                                                                                                          |

### Transcription Stack

| Technology            | Version                       | Purpose                                              | Why Recommended                                                                                                                                                                                                                                                                                                                                            |
| --------------------- | ----------------------------- | ---------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `groq` (via litellm)  | `groq/whisper-large-v3-turbo` | Audio transcription with segment timestamps          | Groq runs Whisper inference on dedicated hardware at ~200x realtime speed. `whisper-large-v3-turbo` is the fastest large model with high accuracy. Returns `verbose_json` with `segments[]` each containing `start`, `end` (seconds), and `text`. The pre-reset codebase (`transcribe_batch.py`) already validated this pipeline against real audio files. |
| litellm transcription | 1.82.4                        | Thin adapter over `groq.audio.transcriptions.create` | `litellm.transcription(model="groq/whisper-large-v3-turbo", file=fp, response_format="verbose_json")` returns a `TranscriptionResponse` compatible with the existing pipeline. Keeps provider swappable.                                                                                                                                                   |

**On word-level vs sentence-level timestamps:** Groq's `whisper-large-v3-turbo` supports `timestamp_granularities=["segment","word"]` via `verbose_json`. The pre-reset codebase requested both but the stored JSON files show `words: null` — Groq's turbo model silently drops word-level timestamps even when requested. The architecture spec calls for sentence-level timestamps (segment boundaries), which Groq does return reliably. The harness should render segment boundaries as `[MM:SS]` inline markers, not rely on word-level. This is already what `Memory-v5.md` describes: timestamps at sentence boundaries.

**Consequence:** Do not depend on word-level timestamps. Use segment `start`/`end` as `start_offset`/`end_offset` for provenance. This matches what the spec calls for.

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

### Mobile Frontend

| Technology          | Version                          | Purpose                                   | Why Recommended                                                                                                                                                                                                                                                                                                                                                                        |
| ------------------- | -------------------------------- | ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| React Native + Expo | Expo SDK ~53 (2026)              | Cross-platform mobile app (iOS + Android) | Standard for indie/solo developers building voice-capture apps. Expo provides `expo-av` for audio recording with configurable format and quality. `expo-file-system` for file access. No native module bridging needed for v1 recording requirements. The Python backend exposes a REST API; Expo's `fetch` API handles multipart upload. Significant ecosystem and community support. |
| `expo-av`           | latest via Expo SDK              | Audio recording                           | `Audio.Recording` API. Records to M4A (AAC) or WAV. M4A is what the existing test audio files use. Configurable quality presets.                                                                                                                                                                                                                                                       |
| FastAPI             | 0.120.1+ (via litellm proxy dep) | Backend HTTP API                          | Not currently in pyproject as a direct dep but available. Async-native. Handles multipart file upload for audio. Server-sent events for streaming query responses. Clean path to mobile → backend communication.                                                                                                                                                                       |

---

## Installation

```bash
# Core backend (already in pyproject.toml — use uv sync)
uv sync

# To add FastAPI for the backend API server (not yet in pyproject):
uv add "fastapi>=0.120" "uvicorn[standard]>=0.30" "python-multipart>=0.0.9"

# Mobile (separate directory, uses bun per NixOS directives):
bun create expo-app@latest arakne-mobile
cd arakne-mobile
bun add expo-av
```

---

## Alternatives Considered

| Category            | Recommended                              | Alternative                        | When to Use Alternative                                                                                                                                                          |
| ------------------- | ---------------------------------------- | ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| LLM interface       | litellm                                  | Direct Gemini SDK (`google-genai`) | Only if litellm has a bug with a specific Gemini feature that requires raw SDK access                                                                                            |
| Transcription host  | Groq API (`groq/whisper-large-v3-turbo`) | Local `faster-whisper`             | Local model if deployment requirements change to keep audio entirely in user-run infrastructure; ~5-10x slower without GPU; not needed for the current hosted transcription path |
| Transcription model | `whisper-large-v3-turbo`                 | `whisper-large-v3` (Groq)          | `large-v3` for higher accuracy on heavily accented speech or poor audio; ~3x slower                                                                                              |
| Vector search       | FalkorDB native KNN                      | ChromaDB / Qdrant                  | Only if graph is dropped in favor of flat vector DB; ChromaDB was used in search experiments before graph architecture was chosen                                                |
| Embedding model     | `gemini-embedding-001`                   | `text-embedding-3-large` (OpenAI)  | If switching to OpenAI; note dimension difference (3072 Gemini vs 3072 OpenAI — same dimension, but indexes must be rebuilt after provider switch)                               |
| Keyword search      | FalkorDB range index (`IN n.aliases`)    | Whoosh / Tantivy full-text         | Only if CONTAINS substring matching becomes needed and property lookup proves insufficient                                                                                       |
| Agent loop          | Custom loop                              | LangGraph                          | Only if the harness needs persistent checkpointing, branching, or parallel agent execution — none of which are in v1                                                             |
| Mobile              | React Native + Expo                      | Flutter                            | Flutter has better perf for complex UIs; Expo is simpler for audio-only apps and JS ecosystem fits the backend integration pattern better                                        |
| Backend API         | FastAPI                                  | Flask                              | Flask for minimal REST; FastAPI preferred for async, type safety, and streaming SSE for query responses                                                                          |

---

## What NOT to Use

| Avoid                                           | Why                                                                                                                                                                                                                | Use Instead                                                               |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------- |
| `redisgraph-py`                                 | Deprecated. RedisGraph was archived in 2023. FalkorDB is the fork that continued development. `redisgraph-py` has no FalkorDB compatibility.                                                                       | `falkordb` 1.6.0                                                          |
| `langchain` as agent runtime                    | Installed as transitive dep but adds abstraction that obscures the token minting and provenance validation the harness must own. Prior iteration did not use it.                                                   | Custom litellm loop                                                       |
| `openai` Whisper API                            | Higher latency, higher cost than Groq for same model. Groq's hardware is purpose-built for Whisper inference.                                                                                                      | `groq/whisper-large-v3-turbo` via litellm                                 |
| Word-level timestamp granularity                | `groq/whisper-large-v3-turbo` does not return word-level data despite accepting the parameter. The `words` field is `null` in all test transcripts. Relying on it will silently produce no timestamps.             | Segment-level timestamps (`segments[].start`, `segments[].end`)           |
| Separate vector DB (Qdrant, Weaviate, Pinecone) | Dual-write synchronization with FalkorDB graph is a reliability hazard. Vectors stored out-of-graph can go stale when nodes are updated. FalkorDB's native vector index keeps embedding co-located with node data. | FalkorDB `VECTOR INDEX` + `db.idx.vector.queryNodes`                      |
| UUID-based node IDs                             | LLMs hallucinate UUIDs in tool arguments. High-entropy identifiers cause silent lookup failures. The spec explicitly chose sequential tokens (`node:N`).                                                           | Sequential readable tokens minted by the harness                          |
| Full graph survey in theme agent                | Theme agent receiving the full graph and re-evaluating everything will not scale past ~100 nodes. The spec is explicit: operate on delta only.                                                                     | Delta-only mode: `touched_nodes` + `touched_edges` from ingestion payload |

---

## Stack Patterns by Variant

**If running on-device (privacy-first, no cloud):**

- Replace `groq/whisper-large-v3-turbo` with local `faster-whisper` (`large-v3-turbo` model, 809 MB)
- Replace `gemini-embedding-001` with a local embedding model (`sentence-transformers/all-mpnet-base-v2`, 768d — requires FalkorDB vector index rebuild to 768d)
- Replace `gemini/gemini-2.5-flash` with a local Ollama model (`llama3.3` or `qwen2.5`)
- litellm handles all three substitutions; the harness code changes only `.env` values

**If word-level timestamps become required (future):**

- Switch transcription to `openai/whisper-1` API (returns word timestamps reliably) or run local `faster-whisper` with `word_timestamps=True`
- Update provenance offsets from segment-level to word-level; schema is already compatible

**If query volume grows and latency matters:**

- FalkorDB vector index is already in-process with graph traversal — no change needed
- Upgrade to `falkordb.asyncio.FalkorDB` with a `BlockingConnectionPool` for concurrent query sessions

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
- `/home/shivang/shivang/projs/arakne/private/transcripts/*.json` — real Groq output format showing `words: null` on `whisper-large-v3-turbo` — HIGH confidence (empirical)
