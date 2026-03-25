---
phase: 01-infrastructure
plan: 01
subsystem: infra
tags: [python, pydantic, falkordb, gemini, litellm, uv, ruff, pytest]

requires: []

provides:
  - lifeos Python package importable with core/, memory/, agent/ submodules
  - Config loading from .env via python-dotenv (get_config())
  - Pydantic models Node, Edge, TranscriptRef, LogEntry with free-string type field
  - TranscriptStore for JSON file I/O
  - Embeddings module embed_text()/embed_query() via gemini-embedding-001
  - transcribe_file() refactored from helpers/transcribe_batch.py
  - Prompt stubs for ingest, query, memo agents
  - pyproject.toml cleaned: chromadb/chonkie removed, ruff/pytest added as dev deps
  - 23 unit tests all passing

affects: [02-graph, 03-harness]

tech-stack:
  added:
    - python-dotenv>=1.0.0 (replaces incorrect dotenv package name)
    - ruff (dev dep, linting)
    - pytest (dev dep, testing)
  patterns:
    - Singleton config via module-level _config global, reset-safe for tests
    - Pydantic BaseModel with free-string type field (no enum)
    - TranscriptStore file I/O with pathlib.Path
    - Lazy genai.Client() singleton for embeddings

key-files:
  created:
    - lifeos/__init__.py
    - lifeos/core/__init__.py
    - lifeos/core/config.py
    - lifeos/core/embeddings.py
    - lifeos/core/transcribe.py
    - lifeos/memory/__init__.py
    - lifeos/memory/models.py
    - lifeos/memory/store.py
    - lifeos/agent/__init__.py
    - tests/__init__.py
    - tests/conftest.py
    - tests/test_config.py
    - tests/test_models.py
    - prompts/ingest.md
    - prompts/query.md
    - prompts/memo.md
  modified:
    - pyproject.toml

key-decisions:
  - "Removed chromadb and chonkie from pyproject.toml — FalkorDB handles vectors natively, no chunking step"
  - "python-dotenv>=1.0.0 replaces incorrect dotenv package name in pyproject.toml"
  - "Config singleton uses module-level _config variable; tests reset it directly for isolation"
  - "TDD used for Task 1 — failing tests committed before implementation"
  - "devenv shell -- uv run is the correct invocation (not devenv shell -- python -m) for the venv to activate"

patterns-established:
  - "Pattern: lifeos.core.config.get_config() is the single config entry point — always call this, never read env vars directly"
  - "Pattern: Node/Edge.type is always a free string — no enum, no validation against a list"
  - "Pattern: TranscriptStore wraps pathlib for all transcript JSON file I/O"
  - "Pattern: embed_text() for storage (RETRIEVAL_DOCUMENT), embed_query() for search (RETRIEVAL_QUERY)"

requirements-completed: [INFR-01, INFR-02]

duration: 4min
completed: 2026-03-25
---

# Phase 01 Plan 01: Project Scaffold and Foundation Summary

**lifeos Python package with typed config, free-schema Pydantic models, transcript file store, and gemini-embedding-001 embeddings — chromadb/chonkie removed, ruff/pytest wired in**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-03-25T18:07:55Z
- **Completed:** 2026-03-25T18:11:35Z
- **Tasks:** 2
- **Files modified:** 17

## Accomplishments

- Created `lifeos` Python package with `core/`, `memory/`, `agent/` submodules — all importable
- Cleaned `pyproject.toml`: removed `chromadb` and `chonkie`, fixed `dotenv` package name to `python-dotenv`, added `ruff` and `pytest` as dev deps
- Implemented `get_config()` singleton that loads from `.env` via `python-dotenv` and returns a typed frozen dataclass
- Implemented `Node`, `Edge`, `TranscriptRef`, `LogEntry` Pydantic models with free-string type fields (no enum constraints)
- Implemented `TranscriptStore` for JSON file I/O with `save()`, `load()`, and `exists()` methods
- Implemented `embed_text()` and `embed_query()` using `gemini-embedding-001` with correct task types
- Refactored `helpers/transcribe_batch.py` into `lifeos/core/transcribe.py` as a clean `transcribe_file()` function
- Created prompt stubs for ingest, query, and memo agents in `prompts/`
- 23 unit tests passing; ruff reports no lint errors

## Task Commits

1. **TDD RED — test(01-01):** `4bcadb7` — failing tests for config, models, transcript store + pyproject.toml cleanup
2. **TDD GREEN — feat(01-01):** `c7605ee` — lifeos package implementation (config, models, store)
3. **Task 2 — feat(01-01):** `af9b339` — embeddings module, transcribe refactor, prompt stubs

## Files Created/Modified

- `pyproject.toml` — removed chromadb/chonkie, fixed dotenv package name, added dev deps section
- `lifeos/core/config.py` — `get_config()` loading from .env, typed frozen dataclass
- `lifeos/core/embeddings.py` — `embed_text()` RETRIEVAL_DOCUMENT, `embed_query()` RETRIEVAL_QUERY
- `lifeos/core/transcribe.py` — `transcribe_file()` refactored from helpers/, uses litellm
- `lifeos/memory/models.py` — Pydantic Node, Edge, TranscriptRef, LogEntry
- `lifeos/memory/store.py` — TranscriptStore JSON file I/O
- `tests/conftest.py` — `tmp_transcript_dir` and `mock_env` fixtures
- `tests/test_config.py` — 6 config tests
- `tests/test_models.py` — 17 model and store tests
- `prompts/ingest.md`, `prompts/query.md`, `prompts/memo.md` — agent prompt stubs

## Decisions Made

- `dotenv>=0.9.9` was an incorrect PyPI package name — replaced with `python-dotenv>=1.0.0` (the correct package)
- Config singleton reset pattern: tests set `lifeos.core.config._config = None` directly before each test to avoid cross-test contamination
- `devenv shell -- uv run` is the correct invocation to activate the venv in this devenv environment (not `devenv shell -- python -m`)
- Prompt files are markdown stubs with `[Detailed instructions will be added in Phase N]` placeholders — intentional, wired in Phase 2/3/4

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

- `devenv shell -- python -m pytest` failed because the devenv shell uses the system Python, not the project venv. Resolution: use `devenv shell -- uv run python -m pytest` throughout. This is documented in RESEARCH.md Pitfall 5.

## Known Stubs

- `prompts/ingest.md` — placeholder text "Detailed instructions will be added in Phase 2". Intentional — prompt content is Phase 2 work.
- `prompts/query.md` — placeholder text "Detailed instructions will be added in Phase 3". Intentional.
- `prompts/memo.md` — placeholder text "Detailed instructions will be added in Phase 4". Intentional.

These stubs do not block this plan's goal (foundation scaffold). They will be resolved in Plans 02 and 03.

## Next Phase Readiness

- Plan 02 (graph layer) can import `lifeos.memory.models`, `lifeos.core.config`, and `lifeos.core.embeddings` immediately
- Plan 03 (agent harness) can import all of the above plus `lifeos.core.transcribe`
- `prompts/` directory ready for Phase 2 to fill in ingestion agent prompt

## Self-Check: PASSED

All 11 created files verified present. All 3 task commits verified in git history.

---
*Phase: 01-infrastructure*
*Completed: 2026-03-25*
