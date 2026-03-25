---
phase: 1
slug: infrastructure
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-25
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (to be added via `uv add --dev pytest`) |
| **Config file** | None — Wave 0 creates `pyproject.toml` `[tool.pytest.ini_options]` section |
| **Quick run command** | `devenv shell -- python -m pytest tests/ -x -q` |
| **Full suite command** | `devenv shell -- python -m pytest tests/ -v` |
| **Estimated runtime** | ~10 seconds (unit) / ~30 seconds (integration w/ FalkorDB) |

---

## Sampling Rate

- **After every task commit:** Run `devenv shell -- python -m pytest tests/ -x -q`
- **After every plan wave:** Run `devenv shell -- python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | INFR-01 | smoke | `devenv shell -- python -c "import lifeos"` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | INFR-02 | unit | `pytest tests/test_config.py -x` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 1 | INFR-03 | integration | `pytest tests/test_graph.py::test_init_graph -x` | ❌ W0 | ⬜ pending |
| 01-02-02 | 02 | 1 | GRPH-01 | integration | `pytest tests/test_graph.py::test_indexes -x` | ❌ W0 | ⬜ pending |
| 01-02-03 | 02 | 1 | GRPH-05 | integration | `pytest tests/test_graph.py::test_atomic_update -x` | ❌ W0 | ⬜ pending |
| 01-03-01 | 03 | 2 | HARN-01 | unit | `pytest tests/test_harness.py::test_run -x` | ❌ W0 | ⬜ pending |
| 01-03-02 | 03 | 2 | HARN-03 | unit | `pytest tests/test_harness.py::test_budget -x` | ❌ W0 | ⬜ pending |
| 01-04-01 | 04 | 2 | INFR-04 | smoke | `devenv shell -- python scripts/ingest.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/__init__.py` — empty, marks tests as package
- [ ] `tests/conftest.py` — shared fixtures: `graph_fixture` (temp FalkorDB graph), `mock_genai_client`
- [ ] `tests/test_config.py` — covers INFR-02
- [ ] `tests/test_graph.py` — covers INFR-03, GRPH-01, GRPH-05
- [ ] `tests/test_harness.py` — covers HARN-01, HARN-03
- [ ] Framework install: `uv add --dev pytest` — pytest not yet in pyproject.toml
- [ ] `pyproject.toml` `[tool.pytest.ini_options]` section added

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| FalkorDB Docker reachable after `devenv up` | INFR-03 | Requires running Docker daemon | Run `devenv up`, then `redis-cli -p 6379 PING` — expect PONG |
| Gemini API key produces completion | INFR-02 | Requires valid API key | Run `devenv shell -- python -c "from lifeos.core.config import get_config; print(get_config())"` |
| Groq Whisper returns transcription | INFR-04 | Requires valid API key + test audio file | Run transcribe script with a sample .m4a file |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
