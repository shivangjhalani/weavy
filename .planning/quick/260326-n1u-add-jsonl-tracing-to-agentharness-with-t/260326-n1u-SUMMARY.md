---
phase: quick
plan: 260326-n1u
subsystem: agent
tags: [tracing, observability, debugging, harness, verbose]
dependency_graph:
  requires: []
  provides: [lifeos.agent.tracer.Tracer, lifeos.agent.tracer.JsonlTracer]
  affects: [lifeos.agent.harness.AgentHarness, scripts/ingest.py]
tech_stack:
  added: []
  patterns:
    - "Injected tracer protocol: harness depends on base Tracer only; caller creates JsonlTracer"
    - "Guard pattern: all tracer calls wrapped in 'if self.tracer:' for zero-overhead default"
    - "Append-mode JSONL writes with immediate flush for mid-run readability"
key_files:
  created:
    - lifeos/agent/tracer.py
  modified:
    - lifeos/agent/harness.py
    - scripts/ingest.py
    - .gitignore
decisions:
  - "Tracer injected into harness — harness imports only Tracer base (not JsonlTracer) to keep decoupling clean"
  - "ThinkingConfig gated behind --verbose to avoid unexpected cost increase in normal runs"
  - "argparse replaces manual sys.argv parsing in ingest.py for --verbose and future flag extensibility"
metrics:
  duration: "~8 minutes"
  completed: "2026-03-26"
  tasks: 2
  files: 4
---

# Quick Task 260326-n1u: Add JSONL Tracing to AgentHarness Summary

**One-liner:** Injected Tracer protocol with JsonlTracer writing full-fidelity JSONL to traces/, toggled by --verbose on ingest.py with zero overhead when disabled.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create Tracer base class and JsonlTracer | 4d72444 | lifeos/agent/tracer.py |
| 2 | Instrument AgentHarness + --verbose on ingest.py | ce75e9a | lifeos/agent/harness.py, scripts/ingest.py, .gitignore |

## What Was Built

### lifeos/agent/tracer.py (new)

- **Tracer** base class: 7 no-op methods — `on_run_start`, `on_llm_response`, `on_llm_error`, `on_tool_call`, `on_tool_result`, `on_tool_error`, `on_run_end`. Zero overhead, safe to subclass.
- **JsonlTracer(Tracer)**: Creates `traces/` dir on init (mkdir parents). Generates trace filename `{iso_timestamp}_{uuid4_prefix}.jsonl`. Each `on_*` call appends one JSON line with event name, ISO timestamp, and full-fidelity payload (no truncation). Uses `json.dumps(default=str)` for datetime safety. Opens in append mode and flushes immediately.

### lifeos/agent/harness.py (modified)

- New constructor params: `tracer: Tracer | None = None`, `thinking_config: types.ThinkingConfig | None = None`.
- `thinking_config` is passed to `GenerateContentConfig` when set.
- Turn counter (`turn`) starts at 1 and increments each loop iteration.
- `total_tool_calls` accumulates across turns.
- **7 trace points** instrumented with `if self.tracer:` guard:
  1. `on_run_start` — before while loop, with model, tool names, UTC timestamp
  2. `on_llm_response` — after response extraction, with turn, finish_reason, tool_call_count, thinking text, response text
  3. `on_llm_error("no_candidates", ...)` — before RuntimeError on empty candidates
  4. `on_llm_error("none_content", ...)` — before RuntimeError on None content
  5. `on_tool_call` — before each tool dispatch, with turn, name, args
  6. `on_tool_result` — after successful tool call, with duration_ms via `time.perf_counter()`
  7. `on_run_end` — before final return, with turn count, total_tool_calls, final text
- Tool dispatch wrapped in try/except: `on_tool_error` on exception then re-raise.
- Thinking text extracted from candidate parts where `p.thought is True`.

### scripts/ingest.py (modified)

- Replaced manual `sys.argv` parsing with `argparse` (positional `audio_file`, optional `--verbose`).
- When `--verbose`: imports `JsonlTracer`, creates instance, creates `ThinkingConfig(thinking_budget=8000, include_thoughts=True)`, passes both to `AgentHarness`. Prints trace file path.
- Without `--verbose`: tracer and thinking_config default to None — zero overhead.
- All existing ingestion functionality preserved unchanged.

### .gitignore (modified)

Added `traces/` at top of project-specific section.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED

All files present and commits verified:
- FOUND: lifeos/agent/tracer.py
- FOUND: lifeos/agent/harness.py
- FOUND: scripts/ingest.py
- FOUND: commit 4d72444 (Task 1)
- FOUND: commit ce75e9a (Task 2)
