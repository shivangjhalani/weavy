---
phase: 03
slug: query-agent
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-29
---

# Phase 03 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=9.0.2 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `devenv shell -- uv run python -m pytest tests/test_query_tools.py -x -q` |
| **Full suite command** | `devenv shell -- uv run python -m pytest tests/ -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `devenv shell -- uv run python -m pytest tests/test_query_tools.py -x -q`
- **After every plan wave:** Run `devenv shell -- uv run python -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 0 | VECT-02 | unit | `pytest tests/test_query_tools.py::test_search_nodes_by_embedding_returns_matches -x` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 0 | VECT-02 | unit | `pytest tests/test_query_tools.py::test_search_edges_by_embedding_returns_matches -x` | ❌ W0 | ⬜ pending |
| 03-01-03 | 01 | 0 | VECT-02 | unit | `pytest tests/test_query_tools.py::test_search_episode_spans_returns_ranked -x` | ❌ W0 | ⬜ pending |
| 03-01-04 | 01 | 0 | VECT-03 | unit | `pytest tests/test_query_tools.py::test_hybrid_search_enriches_with_edges -x` | ❌ W0 | ⬜ pending |
| 03-01-05 | 01 | 0 | HARN-02 | unit | `pytest tests/test_query_tools.py::test_query_prompt_is_substantive -x` | ❌ W0 | ⬜ pending |
| 03-01-06 | 01 | 0 | HARN-04 | unit | `pytest tests/test_query_tools.py::test_build_query_tools_count -x` | ❌ W0 | ⬜ pending |
| 03-01-07 | 01 | 0 | HARN-04 | unit | `pytest tests/test_query_tools.py::test_build_query_tools_no_write_tools -x` | ❌ W0 | ⬜ pending |
| 03-01-08 | 01 | 0 | HARN-04 | unit | `pytest tests/test_query_tools.py::test_get_transcript_span_returns_text -x` | ❌ W0 | ⬜ pending |
| 03-01-09 | 01 | 0 | HARN-04 | unit | `pytest tests/test_query_tools.py::test_get_transcript_span_not_found -x` | ❌ W0 | ⬜ pending |
| 03-01-10 | 01 | 0 | HARN-04 | unit | `pytest tests/test_query_tools.py::test_get_transcript_span_no_segments_fallback -x` | ❌ W0 | ⬜ pending |
| 03-02-01 | 02 | 1 | QURY-01 | unit | `pytest tests/test_query_tools.py::test_query_harness_dispatches_tools -x` | ❌ W0 | ⬜ pending |
| 03-02-02 | 02 | 1 | QURY-03 | unit | `pytest tests/test_query_tools.py::test_query_script_runs_smoke -x` | ❌ W0 | ⬜ pending |
| 03-02-03 | 02 | 1 | QURY-03 | unit | `pytest tests/test_query_tools.py::test_query_declarations_include_hybrid_search -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_query_tools.py` — stubs for all VECT-02, VECT-03, HARN-02, HARN-04, QURY-01, QURY-03 unit tests listed above

*Existing `tests/conftest.py` covers fixtures — no changes needed. `tests/test_tools.py` pattern is the reference for all new tool tests.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Query agent returns grounded answer with citations | QURY-01, QURY-02 | End-to-end requires live FalkorDB + LLM | Run `scripts/query.py "question"` against populated graph, verify citations in output |
| Different questions produce different tool sequences | QURY-03 | Agent autonomy requires live LLM reasoning | Query 2-3 different question types, verify distinct tool call patterns in trace |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
