# Phase 1: Infrastructure - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-25
**Phase:** 01-infrastructure
**Areas discussed:** Project structure, Graph data model, Harness loop design

---

## Project Structure

| Option | Description | Selected |
|--------|-------------|----------|
| Package + scripts | lifeos/ package with modules + top-level scripts/ for experiments | ✓ |
| Flat scripts | Everything in root, refactor later | |
| You decide | Claude picks cleanest structure | |

**User's choice:** Package + scripts
**Notes:** None

---

| Option | Description | Selected |
|--------|-------------|----------|
| Markdown files | prompts/ directory with .md files | ✓ |
| Inline in Python | Prompts as strings in roles.py | |
| You decide | Claude picks | |

**User's choice:** Markdown files
**Notes:** None

---

## Graph Data Model

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal Pydantic | Only structural requirements: id, summary, log[], aliases[], refs[]. Type is free string. | ✓ |
| Dict-based | No Pydantic, just dicts. Maximum flexibility. | |

**User's choice:** Minimal Pydantic
**Notes:** Follows the Bitter Lesson — minimal schema, maximum LLM flexibility

---

| Option | Description | Selected |
|--------|-------------|----------|
| FalkorDB | Transcripts as nodes in graph | |
| JSON on disk | Transcripts as JSON files in data/ | ✓ |
| You decide | Claude picks | |

**User's choice:** JSON on disk
**Notes:** Aligns with existing transcribe_batch.py output format

---

## Harness Loop Design

| Option | Description | Selected |
|--------|-------------|----------|
| Native FC loop | google-genai built-in function calling loop | |
| Manual dispatch | Roll own loop: prompt → parse → dispatch → feed back | ✓ |
| You decide | Claude picks simplest approach | |

**User's choice:** Manual dispatch
**Notes:** More control, easier to enforce budget and add instrumentation

---

| Option | Description | Selected |
|--------|-------------|----------|
| Force final answer | Inject system message to synthesize with what it has | |
| Hard cutoff | Stop dispatching, return last response | |
| You decide | Claude picks best approach under budget pressure | ✓ |

**User's choice:** You decide (Claude's discretion)
**Notes:** None

## Claude's Discretion

- Budget enforcement mechanism (force final answer vs hard cutoff)
- FalkorDB index set
- Config module design
- Async vs sync harness loop

## Deferred Ideas

None
