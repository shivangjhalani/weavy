---
phase: 2
slug: ingestion-agent
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-03-26
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `pyproject.toml` ([tool.pytest.ini_options]) |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-00-01 | 00 | 0 | (all stubs) | stubs | `uv run pytest tests/test_transcription.py tests/test_tools.py tests/test_compression.py tests/test_ingestion.py tests/test_episodes.py -v` | W0 creates | pending |
| 02-01-01 | 01 | 1 | GRPH-02, GRPH-03, GRPH-04, TRNS-02 | unit | `uv run pytest tests/test_models.py -v` | yes | pending |
| 02-01-02 | 01 | 1 | GRPH-02, GRPH-03, INGST-03, INGST-06 | unit+integration | `uv run pytest tests/test_graph.py -v` | yes | pending |
| 02-02-01 | 02 | 2 | (D-08) | unit | `uv run pytest tests/test_harness.py -v` | yes | pending |
| 02-02-02 | 02 | 2 | INGST-01, INGST-02, INGST-04 | unit | `uv run pytest tests/test_tools.py -v` | W0 stub | pending |
| 02-03-01 | 03 | 3 | (prompts) | file check | `test -f prompts/ingest.md && test -f prompts/compress.md` | N/A | pending |
| 02-03-02 | 03 | 3 | COMP-01, COMP-02, COMP-03, VECT-01 | unit | `uv run pytest tests/test_compression.py -v` | W0 stub | pending |
| 02-04-01 | 04 | 4 | TRNS-01, TRNS-03 | integration | `grep -c "def main" scripts/ingest.py` | yes | pending |

*Status: pending -- green -- red -- flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_transcription.py` — stubs for TRNS-01, TRNS-02, TRNS-03
- [ ] `tests/test_tools.py` — stubs for INGST-01, INGST-02
- [ ] `tests/test_ingestion.py` — stubs for INGST-03, INGST-04, INGST-06
- [ ] `tests/test_compression.py` — stubs for COMP-01, COMP-02, COMP-03
- [ ] `tests/test_episodes.py` — stubs for VECT-01

*Existing `tests/test_models.py` and `tests/test_graph.py` cover graph model verification.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Audio transcription quality | TRNS-01 | Requires actual Groq Whisper API call with real audio | Record 30s audio, run `ingest.py`, verify transcript text is accurate |
| Duplicate detection across sessions | INGST-03 | Requires two separate ingest runs with related content | Ingest two audio files mentioning same concept with different wording, verify single node |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter (set, pending Wave 0 execution)

**Approval:** pending Wave 0 execution
