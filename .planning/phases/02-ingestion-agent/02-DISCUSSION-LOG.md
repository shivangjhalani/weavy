# Phase 2: Ingestion Agent - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-26
**Phase:** 02-ingestion-agent
**Areas discussed:** Agent tool granularity, Disambiguation flow, Episode span lifecycle, Log compression trigger, Ingestion prompt design, Data model changes, Transcript record format, Ingest script UX

---

## Agent Tool Granularity

| Option | Description | Selected |
|--------|-------------|----------|
| Fine-grained tools | Individual tools: search_nodes, create_node, update_node, merge_nodes, create_edge, update_edge, delete_node. Maximum LLM flexibility. | |
| Coarse batch tool | One write_graph tool accepting a list of operations. Fewer tool calls but LLM must plan upfront. | |
| Hybrid approach | Fine-grained search + batch write. Balances budget with flexibility. | |
| You decide | Claude picks based on constraints. | |

**User's choice:** Fine-grained tools
**Notes:** Aligns with Bitter Lesson — maximum LLM autonomy over graph operations.

### Sub-decision: Delete tools

| Option | Description | Selected |
|--------|-------------|----------|
| Additive only | Ingestion only creates, updates, merges. Deletion for future phase. | |
| Include delete tools | Agent can delete nodes/edges it judges wrong or redundant. | |

**User's choice:** Include delete tools

### Sub-decision: Vocabulary registry injection

**User's choice:** N/A — User questioned the need for types and vocabulary entirely. Led to D-01 (drop types).

### Sub-decision: Merge tool

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated merge tool | Atomic merge_nodes(a, b) tool. | |
| Compose from primitives | Agent uses update + delete to merge manually. | |

**User's choice:** Compose from primitives

### Sub-decision: Tool-call budget

| Option | Description | Selected |
|--------|-------------|----------|
| Higher budget (20-30) | More room for tool-heavy ingestion. | |
| Dynamic per transcript | Scale budget by transcript length. | |
| You decide | Claude picks a sensible default. | |

**User's choice:** Remove all budgets entirely. No budget enforcement for now.

---

## Disambiguation Flow

| Option | Description | Selected |
|--------|-------------|----------|
| Code-driven gate | Search tool internally runs all 3 tiers, returns ranked candidates. | |
| Agent-driven | Agent gets separate tools, 3-tier flow is emergent from behavior. | |

**User's choice:** Agent-driven
**Notes:** Maximum LLM autonomy. System prompt guides search-before-create behavior.

### Sub-decision: Fuzzy matching method

| Option | Description | Selected |
|--------|-------------|----------|
| Embedding similarity | Reuse existing vector_search. Catches semantic matches. | |
| String distance | Levenshtein/Jaro-Winkler on aliases. Catches typos. | |
| Both as separate tools | Vector search + string distance. Covers both failure modes. | |

**User's choice:** Embedding similarity

### Sub-decision: Score visibility

| Option | Description | Selected |
|--------|-------------|----------|
| Agent sees scores + decides | Search returns candidates with similarity scores. | |
| Agent sees candidates only | No scores, pure semantic reasoning. | |

**User's choice:** Agent sees scores + decides

---

## Episode Span Lifecycle

| Option | Description | Selected |
|--------|-------------|----------|
| In transcript JSON on disk | Stored alongside raw text in TranscriptStore. | |
| In FalkorDB as nodes | Spans become queryable graph nodes. | |
| Both locations | Duplicated for different access patterns. | |

**User's choice:** In transcript JSON on disk

### Sub-decision: Creation timing

| Option | Description | Selected |
|--------|-------------|----------|
| After graph writes | Agent builds graph first, then identifies topic spans. | |
| Before graph writes | Segment first, then process each span. | |
| Interleaved | Create spans as agent goes. | |

**User's choice:** After graph writes

---

## Log Compression Trigger

| Option | Description | Selected |
|--------|-------------|----------|
| Inline during ingestion | Check after each log append. | |
| Post-ingestion pass | Separate pass after agent finishes. | |
| Lazy / on-read | Compress only when log is read and over budget. | |

**User's choice:** Post-ingestion pass

### Sub-decision: Compression executor

| Option | Description | Selected |
|--------|-------------|----------|
| Separate LLM call | Standalone Gemini call with compression prompt. | |
| Same agent, extra pass | Ingestion agent compresses using its tools. | |

**User's choice:** Separate LLM call

### Sub-decision: Threshold type

| Option | Description | Selected |
|--------|-------------|----------|
| Token count | Compress when log exceeds token threshold. | |
| Entry count | Compress when log has > N entries. | |

**User's choice:** Token count

---

## Ingestion Prompt Design

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal guardrails | Describe structure, list tools, state goal. Let LLM figure out the rest. | |
| Guided workflow | Include suggested step-by-step workflow. | |

**User's choice:** Minimal guardrails

### Sub-decision: Selectivity guidance (INGST-04)

| Option | Description | Selected |
|--------|-------------|----------|
| Explicitly state it | Prompt says "not everything is worth persisting, use judgment." | |
| Leave implicit | Trust LLM to naturally focus on what's meaningful. | |

**User's choice:** Explicitly state it

### Sub-decision: Recording timestamp delivery

| Option | Description | Selected |
|--------|-------------|----------|
| In the user message | "Recording from [date]:\n\n[transcript]" | |
| As a tool parameter | Pass as parameter to start_ingestion tool. | |

**User's choice:** In the user message

---

## Data Model Changes

### Sub-decision: Dropping types

**User's choice:** Drop types entirely from both nodes and edges. Types are a categorization scheme that violates the Bitter Lesson. The summary carries all semantic meaning.

### Sub-decision: Node model fields

| Option | Description | Selected |
|--------|-------------|----------|
| Exactly minimal (id, summary, aliases, log, refs, embedding) | Maximum simplicity. | |
| Keep a name field | Explicit canonical display label separate from aliases. | |

**User's choice:** Keep a name field

### Sub-decision: Edge label

| Option | Description | Selected |
|--------|-------------|----------|
| Summary only | Drop label/type entirely. Summary describes relationship. | |
| Keep a short label | Rename type to label — concise relationship descriptor. | |

**User's choice:** Keep a short label

---

## Transcript Record Format

| Option | Description | Selected |
|--------|-------------|----------|
| Pydantic model | Transcript model with id, recorded_at, text, segments, episode_spans. | |
| Keep raw dicts | TranscriptStore stays as-is. | |

**User's choice:** Pydantic model

### Sub-decision: Recording timestamp source

| Option | Description | Selected |
|--------|-------------|----------|
| From audio file metadata | Read filesystem creation/modification time. | |
| User provides it | --recorded-at flag or sidecar file. | |

**User's choice:** From audio file metadata

---

## Ingest Script UX

| Option | Description | Selected |
|--------|-------------|----------|
| Single file path | One audio file per run. | |
| Directory of files | Process all audio files in directory. | |
| Both modes | Accept file or directory. | |

**User's choice:** Single file path

### Sub-decision: Output

| Option | Description | Selected |
|--------|-------------|----------|
| Summary of changes | Print transcript ID, node/edge counts, span count. | |
| Verbose play-by-play | Print each tool call and result. | |
| Silent | Exit code only. | |

**User's choice:** Summary of changes

---

## Claude's Discretion

- Token threshold value for log compression
- FalkorDB index changes after type removal
- Async vs sync for agent loop
- Episode span embedding approach
- Token counting method for compression threshold

## Deferred Ideas

None — discussion stayed within phase scope
