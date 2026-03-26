---
phase: 6
slug: migrate-from-google-genai-to-litellm-for-provider-agnostic-llm-calls-and-cost-tracking
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-27
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `devenv shell -- uv run pytest tests/ -x -q` |
| **Full suite command** | `devenv shell -- uv run pytest tests/ -v` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `devenv shell -- uv run pytest tests/ -x -q`
- **After every plan wave:** Run `devenv shell -- uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | Embedding smoke test | integration | `devenv shell -- uv run pytest tests/test_embeddings.py -x -q` | ✅ | ⬜ pending |
| 06-01-02 | 01 | 1 | Config provider-agnostic | unit | `devenv shell -- uv run pytest tests/test_config.py -x -q` | ❌ W0 | ⬜ pending |
| 06-02-01 | 02 | 2 | Harness litellm completion | unit | `devenv shell -- uv run pytest tests/test_harness.py -x -q` | ✅ | ⬜ pending |
| 06-02-02 | 02 | 2 | Compression litellm call | unit | `devenv shell -- uv run pytest tests/test_compression.py -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Existing test infrastructure covers most phase requirements
- [ ] `tests/test_harness.py` — already exists, needs litellm mock updates
- [ ] `tests/test_embeddings.py` — already exists, needs litellm mock updates

*Existing infrastructure covers most phase requirements. Tests will be updated in-place during migration.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Embedding via litellm works with gemini-embedding-001 | Embedding smoke test | Requires live API key and FalkorDB | Run `devenv shell -- uv run python -c "import litellm; print(litellm.embedding(model='gemini/gemini-embedding-001', input=['test']))"` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
