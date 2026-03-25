# Phase 1: Infrastructure - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Set up the project environment, FalkorDB with proper indexes, atomic storage operations (update always re-embeds), LLM client wrappers (Gemini + Groq), and the agent harness skeleton with tool-call budget enforcement. No ingestion or query logic — just the foundation everything else builds on.

</domain>

<decisions>
## Implementation Decisions

### Project Structure
- **D-01:** Package + scripts layout: `lifeos/` Python package with submodules (`agent/`, `memory/`, `core/`) + top-level `scripts/` directory for experiment entry points
- **D-02:** Agent system prompts live as markdown files in `prompts/` directory (ingest.md, query.md, memo.md) — easy to edit and iterate without touching Python code
- **D-03:** Move existing `helpers/transcribe_batch.py` into the new structure (likely `scripts/transcribe.py` or `lifeos/core/transcribe.py`)

### Graph Data Model
- **D-04:** Minimal Pydantic models — enforce only structural requirements: id, summary, log[], aliases[], refs[]. Type field is a free string. No enum constraints. Follows the Bitter Lesson: minimal schema, maximum LLM flexibility.
- **D-05:** Transcripts stored as JSON files on disk (not in FalkorDB) — simpler, aligns with existing transcribe_batch.py output pattern. Graph nodes reference transcripts by ID; a transcript store module handles file I/O.

### Agent Harness
- **D-06:** Manual dispatch loop — roll our own: send prompt to Gemini, parse response, check for tool calls, dispatch to registered tool functions, feed results back. More control than the SDK's built-in FC loop, easier to enforce budget and add instrumentation.
- **D-07:** Tools registered as a dict mapping tool names to Python callables. FunctionDeclarations sent to Gemini so it knows the tool schemas.
- **D-08:** Tool-call budget enforcement: counter in the harness loop. When budget is exhausted, Claude has discretion on whether to force a final answer via system message injection or hard cutoff — pick what gives best answers under pressure.

### Dependency Cleanup
- **D-09:** Remove `chromadb` and `chonkie` from pyproject.toml — FalkorDB handles vectors natively, and there's no chunking step (full transcripts to agent). Run `uv sync` after cleanup.

### Claude's Discretion
- Budget enforcement mechanism (force final answer vs hard cutoff) — Claude picks what gives best results
- Exact FalkorDB index set (research says: name, aliases, type, transcript_id at minimum)
- Config module design (how .env vars are loaded and shared across modules)
- Whether to use async or sync for the harness loop

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Memory Architecture
- `markdowns/Memory-v3.md` — Defines the three-layer memory architecture, node/edge structure, disambiguation approach, log compression, theme layer design. This is the primary design document.
- `markdowns/Vision.md` — Product vision, user personas, anti-goals. Defines what LifeOS is NOT.

### Existing Code
- `helpers/transcribe_batch.py` — Existing transcription script using litellm + Groq Whisper. Shows env var patterns and output format.
- `devenv.nix` — FalkorDB Docker setup, Python/uv config, LD_LIBRARY_PATH
- `pyproject.toml` — Current dependencies (includes chromadb/chonkie to be removed)
- `.example.env` — Environment variable documentation

### Research
- `.planning/research/STACK.md` — Confirmed stack, what to drop, verification notes
- `.planning/research/PITFALLS.md` — FalkorDB silent full scans (need indexes), stale embeddings (need atomic updates), agentic loop termination

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `helpers/transcribe_batch.py` — Working Groq Whisper transcription via litellm. Can be refactored into the new structure. Pattern: reads .env, processes audio files, outputs JSON + TXT.
- `.env` / `.example.env` — Already has GROQ_API_KEY, GEMINI_API_KEY, transcription config vars

### Established Patterns
- `litellm` for Groq Whisper API calls (already working)
- `dotenv` for env loading from project root
- devenv.nix defines FalkorDB Docker as a process (`devenv up` starts it)

### Integration Points
- FalkorDB on `localhost:6379` (Redis protocol) and `localhost:3000` (browser UI)
- Data stored in `.devenv/falkordb-data/` (volume mount)

</code_context>

<specifics>
## Specific Ideas

- The Bitter Lesson is the core design principle: no heuristics, no domain knowledge engineering, minimal schemas, let the LLM handle semantic decisions. Every design choice should favor generality over specialized rules.
- Transcripts on disk (JSON files) referenced by graph nodes via transcript_id — the existing transcribe_batch.py output format is the starting point.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-infrastructure*
*Context gathered: 2026-03-25*
