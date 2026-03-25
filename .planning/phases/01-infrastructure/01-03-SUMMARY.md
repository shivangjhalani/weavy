---
phase: 01-infrastructure
plan: 03
subsystem: agent
tags: [python, google-genai, agent-harness, tool-dispatch, budget-enforcement, tdd, pytest, hatchling]

requires:
  - 01-01  # lifeos package, config, models
  - 01-02  # graph layer (indirect — scripts import harness which could use graph)

provides:
  - lifeos/agent/harness.py with AgentHarness class (manual dispatch loop, budget enforcement)
  - scripts/ingest.py, query.py, memo.py, eval.py — runnable stubs, all exit 0
  - hatchling build system added — lifeos installable as editable package via uv sync
  - 9 unit tests for AgentHarness with mocked Gemini client

affects: [02-graph-ingestion, 03-query, 04-memo, 05-eval]

tech-stack:
  added:
    - hatchling>=1.29.0 (build backend — enables `uv sync` to install lifeos as editable)
  patterns:
    - AgentHarness(model, tools, declarations, budget, client) constructor accepts optional mock client
    - types.Part(function_response=types.FunctionResponse(name, response, id)) for fc.id round-trip
    - Manual dispatch loop: iterate ALL parts, dispatch, append types.Content, loop

key-files:
  created:
    - lifeos/agent/harness.py
    - scripts/ingest.py
    - scripts/query.py
    - scripts/memo.py
    - scripts/eval.py
    - tests/test_harness.py
  modified:
    - pyproject.toml

key-decisions:
  - "types.Part.from_function_response() does not accept id kwarg in google-genai 1.68.0 — use types.Part(function_response=types.FunctionResponse(id=fc.id)) instead"
  - "hatchling build system added to pyproject.toml — previously missing [build-system] meant uv sync did not install lifeos, causing ModuleNotFoundError in scripts/"
  - "Budget enforcement uses forced final answer (inject budget-exhausted turn) not hard cutoff — guarantees usable response even mid-reasoning"
  - "TDD used for Task 1 — RED committed before GREEN"

requirements-completed: [HARN-01, HARN-03, INFR-04]

duration: 5min
completed: 2026-03-25
---

# Phase 01 Plan 03: Agent Harness and Script Stubs Summary

**AgentHarness manual dispatch loop with budget enforcement via forced final answer, fc.id round-trip fix, and four runnable script stubs — lifeos package now installable via uv sync**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-03-25T18:20:51Z
- **Completed:** 2026-03-25T18:25:30Z
- **Tasks:** 2 (Task 1 TDD: RED + GREEN, Task 2 auto)
- **Files modified:** 7

## Accomplishments

- Created `lifeos/agent/harness.py` with `AgentHarness` class implementing:
  - Manual dispatch loop per D-06 (full control, instrumentation-ready)
  - Tool registry as dict mapping names to callables per D-07
  - Budget counter with forced final answer on exhaustion per D-08
  - Iterates ALL parts for function calls (not just parts[0] — Pitfall 4)
  - Correct fc.id round-trip using `types.Part(function_response=types.FunctionResponse(id=fc.id))`
- Created `tests/test_harness.py` with 9 unit tests, all passing with mocked Gemini client — no live API needed
- Created four runnable script stubs: `scripts/{ingest,query,memo,eval}.py` — each imports from `lifeos.agent.harness`, prints stub message, exits 0
- Fixed `pyproject.toml` to include `[build-system]` with hatchling, enabling `uv sync` to install lifeos as an editable package (previously missing, causing `ModuleNotFoundError` in scripts)

## Task Commits

1. **TDD RED — test(01-03):** `c5f1618` — 9 failing unit tests for AgentHarness
2. **TDD GREEN — feat(01-03):** `84c6cfd` — harness.py implementation + test fixes, all 9 green
3. **Task 2 — feat(01-03):** `a8bb588` — four script stubs + hatchling build system

## Files Created/Modified

- `lifeos/agent/harness.py` — AgentHarness with dispatch loop, budget enforcement (new)
- `tests/test_harness.py` — 9 unit tests with MockClient strategy (new)
- `scripts/ingest.py` — ingestion entry point stub (new)
- `scripts/query.py` — query agent entry point stub (new)
- `scripts/memo.py` — memo agent entry point stub (new)
- `scripts/eval.py` — eval harness entry point stub (new)
- `pyproject.toml` — added [build-system] hatchling

## Decisions Made

- **fc.id round-trip:** `types.Part.from_function_response()` in google-genai 1.68.0 does not accept `id` as a keyword argument. Correct approach: `types.Part(function_response=types.FunctionResponse(name=fc.name, response={...}, id=fc.id))`. The `id` field is on `FunctionResponse` directly.
- **Build system:** `pyproject.toml` was missing `[build-system]`. Without it, `uv sync` resolves dependencies but does not install the local `lifeos` package. Added `requires = ["hatchling"]` + `build-backend = "hatchling.build"`. Now `uv sync` installs lifeos as editable and scripts find it via site-packages.
- **Forced final answer:** When budget is exhausted, harness injects a user-role turn with "Tool call budget exhausted..." message and makes one more generate_content call. This guarantees a usable text response even if the model was mid-reasoning when budget hit.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `types.Part.from_function_response()` lacks `id` kwarg**
- **Found during:** Task 1 (GREEN phase — test_harness_dispatches_tool_call failing)
- **Issue:** `types.Part.from_function_response(name=..., response=..., id=fc.id)` raises `TypeError: got an unexpected keyword argument 'id'` in google-genai 1.68.0
- **Fix:** Replaced with `types.Part(function_response=types.FunctionResponse(name=..., response=..., id=fc.id))` — the `id` field is on `FunctionResponse` directly per its Pydantic model signature
- **Files modified:** `lifeos/agent/harness.py`
- **Commit:** `84c6cfd`

**2. [Rule 3 - Blocking] Missing `[build-system]` caused `ModuleNotFoundError` in scripts**
- **Found during:** Task 2 (verifying scripts run)
- **Issue:** `devenv shell -- uv run python scripts/ingest.py` raised `ModuleNotFoundError: No module named 'lifeos'` because `uv sync` without a build backend does not install the local package into site-packages
- **Fix:** Added `[build-system]` with hatchling to `pyproject.toml`; ran `uv add --dev hatchling` which auto-installed lifeos as editable
- **Files modified:** `pyproject.toml`, `uv.lock`
- **Commit:** `a8bb588`

**3. [Rule 1 - Bug] Test `test_harness_function_response_includes_fc_id` accessed wrong index**
- **Found during:** Task 1 GREEN phase
- **Issue:** Test assumed `fr_part` was a MockPart with `.function_response`, but the harness appends a real `types.Content` to contents, not a MockPart — accessing `.function_response` on the MockContent raised `AttributeError`
- **Fix:** Updated test to walk all contents items looking for any part with `.function_response is not None`
- **Files modified:** `tests/test_harness.py`
- **Commit:** `84c6cfd`

**4. [Rule 1 - Bug] Test `test_harness_budget_injects_exhausted_message` off-by-one on capture**
- **Found during:** Task 1 GREEN phase
- **Issue:** Test captured contents only on `_count == 1` (second call), but budget-exhausted message is injected before the third call; captured contents didn't include it
- **Fix:** Changed to capture all contents on every call and search all of them for the budget text
- **Files modified:** `tests/test_harness.py`
- **Commit:** `84c6cfd`

## Known Stubs

- `scripts/ingest.py` — prints stub message, no actual ingestion logic. Intentional — Phase 2 work.
- `scripts/query.py` — prints stub message, no query logic. Intentional — Phase 3 work.
- `scripts/memo.py` — prints stub message, no memo logic. Intentional — Phase 4 work.
- `scripts/eval.py` — prints stub message, no eval logic. Intentional — Phase 5 work.

These stubs satisfy INFR-04 (runnable entry points exist) and do not block this plan's goal (harness scaffold). Each stub documents which phase resolves it.

## Next Phase Readiness

- All three agent roles (ingest, query, memo) can use `AgentHarness(model, tools, declarations, budget)` immediately
- `AgentHarness` accepts an optional `client` parameter — allows injection of mock clients in tests or future test agents
- Budget enforcement is operational — no runaway tool calls possible from any future phase
- `scripts/ingest.py` is the Phase 2 entry point: just replace `print("[ingest] Stub...")` with actual agent invocation

## Self-Check: PASSED
