---
phase: 06-migrate-from-google-genai-to-litellm-for-provider-agnostic-llm-calls-and-cost-tracking
plan: 02
subsystem: agent/harness
tags: [litellm, migration, harness, cost-tracking, tests]
dependency_graph:
  requires:
    - 06-01 (litellm-based embeddings, compress, tools, config with gemini/ prefix)
  provides:
    - litellm-based AgentHarness with dict message history and json.loads tool dispatch
    - per-run cost tracking via litellm.completion_cost()
    - ingest.py wired to new harness (no genai.Client, uses reasoning_effort)
    - complete test suite with litellm mock shapes (MockModelResponse pattern)
  affects:
    - scripts/ingest.py (all harness wiring now uses litellm path)
    - tests/test_harness.py (fully rewritten, 10 tests green)
tech_stack:
  added: []
  patterns:
    - litellm.completion() with dict messages (OpenAI format) replacing generate_content()
    - json.loads(tc.function.arguments) for tool arg parsing
    - role:tool messages with tool_call_id for tool results
    - litellm.completion_cost() for per-turn cost accumulation
    - @patch("lifeos.agent.harness.litellm") for test isolation
key_files:
  created: []
  modified:
    - lifeos/agent/harness.py
    - scripts/ingest.py
    - tests/test_harness.py
decisions:
  - "AgentHarness drops client and thinking_config params: litellm is stateless, reasoning_effort string replaces ThinkingConfig"
  - "Tool results use role:tool messages with tool_call_id: required by OpenAI-compatible function calling protocol"
  - "last_run_cost initialized to 0.0 in __init__: set after each run() for caller access"
  - "cost tracking is best-effort (try/except around completion_cost): avoids breaking the loop on unsupported models"
metrics:
  duration: 4min
  completed_date: "2026-03-26"
  tasks_completed: 2
  files_modified: 3
---

# Phase 06 Plan 02: Migrate AgentHarness to litellm with Cost Tracking Summary

Rewrote AgentHarness from google-genai `generate_content()` to `litellm.completion()` with OpenAI-format dict messages, json.loads tool arg parsing, role:tool result messages, and per-run cost accumulation via `litellm.completion_cost()`. Updated ingest.py to remove all genai imports. Rewrote test_harness.py with litellm MockModelResponse shapes.

## Tasks Completed

| Task | Commit | Files Changed |
|------|--------|---------------|
| 1: Rewrite AgentHarness for litellm and add cost tracking | 74f092c | harness.py, ingest.py |
| 2: Rewrite tests to use litellm mock shapes | 64795ba | tests/test_harness.py |
| Fix unused result variable | fd515dc | scripts/ingest.py |

## Decisions Made

1. **AgentHarness drops `client` and `thinking_config` params:** litellm is stateless — no client construction needed. `thinking_config` (ThinkingConfig integer budget) replaced by `reasoning_effort` string that litellm maps to budget tokens internally.

2. **Tool results use `role:tool` messages with `tool_call_id`:** The OpenAI function calling protocol requires tool results to reference the originating tool call by ID. This replaces the google-genai `types.FunctionResponse(id=fc.id)` approach.

3. **`last_run_cost` initialized to `0.0` in `__init__`:** Makes the attribute always available (no AttributeError) and readable before `run()` is called.

4. **Cost tracking is best-effort (`try/except` around `completion_cost`):** Avoids breaking the agent loop when cost data is unavailable (e.g., unsupported model, missing pricing table). Silently passes.

5. **`@patch("lifeos.agent.harness.litellm")` patches the whole module:** Lets tests control both `litellm.completion` and `litellm.completion_cost` on the same mock object, matching how the harness imports and uses litellm.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed unused `result` variable in ingest.py**
- **Found during:** Task 1 ruff check — `result = harness.run(...)` assigned but never used (F841)
- **Issue:** Plan said to print cost after `harness.run()` but assigned the return value unnecessarily since the text output is not used downstream in ingest.py
- **Fix:** Changed `result = harness.run(...)` to `harness.run(...)` — cost is accessed via `harness.last_run_cost`
- **Files modified:** scripts/ingest.py
- **Commit:** fd515dc

## Verification Results

All plan success criteria met:

```
Zero google-genai imports in lifeos/ and scripts/: CLEAN
harness.py: import litellm, litellm.completion(), litellm.completion_cost(), last_run_cost
ingest.py: reasoning_effort wired, no client param, prints cost
tests/test_harness.py: 10/10 passed (MockModelResponse shapes, 2 new tests)
tests/test_compression.py: 8/8 passed (unchanged from plan 01)
Total: 18/18 tests green
ruff check lifeos/ scripts/: only pre-existing E402 in ingest.py (logging.basicConfig before imports)
```

## Known Stubs

None — all harness wiring is real implementation with litellm routing to live API.

## Self-Check: PASSED

All files exist and all commits verified:
- lifeos/agent/harness.py: FOUND
- scripts/ingest.py: FOUND
- tests/test_harness.py: FOUND
- 74f092c: FOUND
- 64795ba: FOUND
- fd515dc: FOUND
