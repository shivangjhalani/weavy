---
phase: 02-ingestion-agent
plan: "03"
subsystem: agent-prompts-compression
tags: [prompts, compression, tiktoken, tdd, log-management]
dependency_graph:
  requires: [02-01, 02-02]
  provides: [prompts/ingest.md, prompts/compress.md, lifeos/agent/compress.py]
  affects: [lifeos/agent/harness.py, scripts/ingest.py]
tech_stack:
  added: [tiktoken>=0.12.0]
  patterns: [standalone-gemini-call, tdd-red-green, log-compression-pass]
key_files:
  created:
    - prompts/ingest.md
    - prompts/compress.md
    - lifeos/agent/compress.py
  modified:
    - tests/test_compression.py
    - pyproject.toml
    - uv.lock
decisions:
  - "tiktoken cl100k_base encoding for token counting — consistent with LLM tokenization, threshold 2000 tokens"
  - "compress_log keeps last 3 entries intact per COMP-03 — recent context preserved verbatim"
  - "run_compression_pass uses set_node_log/set_edge_log not update_node — avoids spurious re-embedding after compression"
  - "Standalone Gemini call for compression per D-16 — not part of agent loop, no tools, pure text -> JSON"
metrics:
  duration: "3 minutes"
  completed: "2026-03-26"
  tasks_completed: 2
  files_changed: 6
requirements_satisfied: [COMP-01, COMP-02, COMP-03, VECT-01]
---

# Phase 02 Plan 03: Ingestion Prompt, Compression Prompt, and Compression Module Summary

**One-liner:** Minimal ingestion guardrails prompt with search-first disambiguation, plus token-budgeted log compression using tiktoken cl100k_base with standalone Gemini call preserving arc of change.

## What Was Built

### Task 1: Ingestion and Compression Prompts

**prompts/ingest.md** — Minimal guardrails system prompt for the ingestion agent:
- Describes graph structure (nodes with name/summary/aliases/log/refs, edges with label/summary/log/refs)
- Lists all 9 tools with one-line descriptions
- Disambiguation: search-first guidance (alias exact match → embedding similarity → create if not found)
- Selectivity (INGST-04): "Use your judgment — only create or update nodes for things that matter"
- Log entry guidance with recording date context
- Transcript ref guidance (transcript_id, start_offset/end_offset in seconds)
- Episode spans: create after all graph writes complete
- Recording timestamp format: "Recording from [date]:\n\n[transcript text]"
- No hardcoded node types (GRPH-04 compliant)
- ~585 words (well under 800-word limit)

**prompts/compress.md** — Log compression prompt:
- Preserves inflection points, reversals, contradictions
- Condenses routine reinforcements into counts/brief summaries
- Narrative arc output: "story of change, not a summary of facts"
- JSON output format: `{"recorded_at": "[ISO timestamp]", "note": "[narrative]"}`
- ~258 words (under 300-word limit)

### Task 2: tiktoken Dependency and Compression Module (TDD)

**pyproject.toml** — `tiktoken>=0.12.0` added as direct dependency.

**lifeos/agent/compress.py** — Post-ingestion log compression:
- `count_tokens(text: str) -> int` — cl100k_base encoding via tiktoken
- `needs_compression(log_json: str) -> bool` — returns True if token count > 2000
- `compress_log(log_entries: list[dict], client) -> list[dict]` — keeps last 3 intact, compresses older via standalone Gemini call
- `run_compression_pass(graph, modified_node_ids, modified_edge_ids, client) -> int` — iterates nodes/edges, compresses over-budget logs, writes back via `set_node_log`/`set_edge_log`

**tests/test_compression.py** — 8 tests replacing Wave 0 stubs:
1. `test_count_tokens_returns_int`
2. `test_needs_compression_under_threshold`
3. `test_needs_compression_over_threshold`
4. `test_compress_log_short_list_unchanged`
5. `test_compress_log_splits_correctly`
6. `test_compress_log_sends_only_older_to_gemini`
7. `test_run_compression_pass_no_overbudget`
8. `test_run_compression_pass_compresses_node`

All 8 tests pass.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | 40ffd89 | feat(02-03): write ingestion and compression prompts |
| 2 RED | d5dcfa4 | test(02-03): add failing tests for log compression module |
| 2 GREEN | 9b9e57f | feat(02-03): implement log compression module |

## Decisions Made

1. **tiktoken cl100k_base** — Used for token counting. Consistent with most LLMs' tokenization (GPT-4 family), and since this is a threshold for compressing LLM-generated logs, approximate consistency is sufficient.

2. **Threshold = 2000 tokens** — Per research recommendation (D-17). Conservative threshold that triggers compression before logs become unwieldy.

3. **Last 3 entries kept intact** — Per COMP-03. Ensures the most recent context is always available verbatim for the agent.

4. **set_node_log/set_edge_log not update_node** — Compression only touches the log, not the summary or embedding. Using update_node would trigger re-embedding (wasteful and incorrect since the semantic meaning of the node hasn't changed).

5. **Standalone Gemini call** — Per D-16. Compression is a simple text transformation, not an agentic operation. Using a plain generate_content call without tools is simpler, cheaper, and more reliable.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all exported functions are fully implemented and tested.

## Self-Check: PASSED

- [x] prompts/ingest.md exists
- [x] prompts/compress.md exists
- [x] lifeos/agent/compress.py exists with count_tokens, needs_compression, compress_log, run_compression_pass
- [x] tests/test_compression.py has 8 tests, all passing
- [x] pyproject.toml contains tiktoken>=0.12.0
- [x] Commits 40ffd89, d5dcfa4, 9b9e57f exist
