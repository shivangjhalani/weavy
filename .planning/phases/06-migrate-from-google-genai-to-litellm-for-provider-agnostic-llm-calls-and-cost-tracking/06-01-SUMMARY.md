---
phase: 06-migrate-from-google-genai-to-litellm-for-provider-agnostic-llm-calls-and-cost-tracking
plan: 01
subsystem: core/agent
tags: [litellm, migration, embeddings, compression, tools, config]
dependency_graph:
  requires: []
  provides:
    - litellm-based embedding functions (embed_text, embed_query)
    - litellm-based log compression (compress_log, run_compression_pass)
    - OpenAI-format tool declarations (9 tool dicts)
    - gemini/ prefix model name defaults in config
  affects:
    - lifeos/agent/harness.py (consumes declarations — Plan 02 migration)
    - scripts/ingest.py (run_compression_pass no longer needs client param)
tech_stack:
  added: []
  patterns:
    - litellm.embedding() with task_type for Google AI Studio embeddings
    - litellm.completion() with response_format for structured JSON output
    - OpenAI-format tool dicts (type/function/parameters) replacing FunctionDeclaration objects
key_files:
  created: []
  modified:
    - lifeos/core/embeddings.py
    - lifeos/agent/compress.py
    - lifeos/core/config.py
    - lifeos/agent/tools.py
    - scripts/ingest.py
    - tests/test_compression.py
    - tests/test_tools.py
    - .example.env
decisions:
  - "litellm requires gemini/ prefix for Google AI Studio routing (not vertex AI): model names updated in config defaults and .env"
  - "reasoning_effort replaces thinking_budget: litellm uses string param, not integer budget"
  - "compress_log drops client param entirely: litellm.completion() is stateless, no client object needed"
  - "OpenAI-format tool dicts are plain Python — no SDK imports in tools.py"
metrics:
  duration: 9min
  completed_date: "2026-03-26"
  tasks_completed: 2
  files_modified: 8
---

# Phase 06 Plan 01: Migrate Leaf Modules to litellm Summary

Migrated three leaf modules (embeddings.py, compress.py, tools.py) from google-genai SDK to litellm, removing all google-genai imports from these files and updating config defaults to use litellm's `gemini/` provider prefix format.

## Tasks Completed

| Task | Commit | Files Changed |
|------|--------|---------------|
| 1: Migrate embeddings.py and compress.py to litellm | da8a62a | embeddings.py, compress.py, config.py, scripts/ingest.py, tests/test_compression.py |
| 2: Migrate tools.py declarations to OpenAI format | 1dec5ae | tools.py, tests/test_tools.py |
| Env config update | 09ce0e8 | .example.env |

## Decisions Made

1. **litellm requires `gemini/` prefix for Google AI Studio:** Without this prefix, litellm routes calls to Vertex AI (requiring GCP credentials) instead of Google AI Studio. Both config.py defaults and .env were updated.

2. **`reasoning_effort` replaces `thinking_budget`:** litellm uses a string enum (`"none"/"low"/"medium"/"high"`) mapped to budget tokens internally, not an explicit integer. The `_parse_thinking_budget` function and `thinking_budget` field removed entirely from config.

3. **`compress_log` drops `client` parameter:** litellm is stateless — no client object is constructed or threaded. The signature simplifies from `(log_entries, client, model)` to `(log_entries, model)`.

4. **OpenAI-format tool dicts need no SDK imports:** `tools.py` now has zero imports from google-genai. Declarations are plain Python dicts that work with any OpenAI-compatible provider.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated .env GEMINI_EMBEDDING_MODEL to use gemini/ prefix**
- **Found during:** Task 1 verification (integration test routing to vertex AI)
- **Issue:** .env had `GEMINI_EMBEDDING_MODEL=gemini-embedding-001` — without prefix, litellm routes to vertex AI and fails with `DefaultCredentialsError`
- **Fix:** Updated `.env` (local, gitignored) and `.example.env` to use `gemini/gemini-embedding-001`
- **Files modified:** .example.env (committed); .env (local only, gitignored)
- **Commit:** 09ce0e8

**2. [Rule 1 - Bug] Fixed test_compression.py mock shapes for litellm**
- **Found during:** Task 1 — tests used `mock_client.models.generate_content` pattern from google-genai
- **Issue:** `compress_log` signature and mock pattern fundamentally changed; tests would all fail at import/call time
- **Fix:** Rewrote test helpers with `patch("litellm.completion", ...)` and `_make_litellm_response()` helper; updated all signatures from `(entries, mock_client)` to `(entries, TEST_MODEL)`
- **Files modified:** tests/test_compression.py
- **Commit:** da8a62a

**3. [Rule 1 - Bug] Fixed test_tools.py declaration name access**
- **Found during:** Task 2 — `d.name` on FunctionDeclaration objects now fails because declarations are plain dicts
- **Issue:** `test_declaration_names_match_tool_keys` accessed `d.name` which doesn't exist on dict
- **Fix:** Changed to `d["function"]["name"]` to match OpenAI-format structure
- **Files modified:** tests/test_tools.py
- **Commit:** 1dec5ae

**4. [Rule 3 - Blocking] Updated scripts/ingest.py for new signatures**
- **Found during:** Task 1 — ingest.py passed `client` to `run_compression_pass` and used `thinking_budget`
- **Issue:** `run_compression_pass(graph, ..., client, model=...)` would fail since `client` param removed
- **Fix:** Removed `client` from `run_compression_pass` call; removed `thinking_budget`/`ThinkingConfig` references; removed `genai.Client()` construction; kept AgentHarness call compatible with current harness.py (which is migrated in plan 02)
- **Files modified:** scripts/ingest.py
- **Commit:** da8a62a

### Out of Scope (Deferred)

- **test_harness.py + harness.py pre-existing diff:** Both files have uncommitted changes in the working tree that predate plan 01. `harness.py` changed `getattr(candidate, "finish_reason", "UNKNOWN")` to `candidate.finish_reason`, causing `MockCandidate` to fail. This is a pre-existing issue outside plan 01 scope — will be resolved in plan 02 (harness migration).

## Verification Results

All plan acceptance criteria met:

```
lifeos/core/embeddings.py: 0 google imports, 3 litellm references
lifeos/agent/compress.py: 0 google imports, 3 litellm references
lifeos/agent/tools.py: 0 google imports, 9 occurrences of "type": "function"
lifeos/core/config.py: gemini/ prefix in both model defaults, reasoning_effort field present
ruff check: All checks passed (all 4 files)
tests/test_compression.py: 8/8 passed
tests/test_tools.py: 17/17 passed
tests/test_config.py: passed
```

## Self-Check: PASSED

All files exist and all commits verified in git log.
