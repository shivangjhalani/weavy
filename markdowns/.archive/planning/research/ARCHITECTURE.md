# Architecture Research

**Domain:** Agentic memory system — AI voice journaling with 3-layer backend
**Researched:** 2026-04-01
**Confidence:** HIGH (primary source is the project's own authoritative spec, Memory-v5.md)

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────┐
│                     SCRIPT ENTRY POINTS                     │
│  ingest_audio.py / ingest_transcript.py / query_memory.py  │
│  inspect_graph.py                                          │
└──────────────────────────┬───────────────────────────────────┘
                           │ Python function calls
┌──────────────────────────▼───────────────────────────────────┐
│                AGENT HARNESS (shared runtime)               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐      │
│  │  Ingestion  │  │    Query    │  │     Theme       │      │
│  │   Prompt    │  │   Prompt    │  │     Prompt      │      │
│  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘      │
│         │                │                  │               │
│         ▼                ▼                  ▼               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │           LLM Tool-Calling Loop                       │  │
│  │  system_prompt + tools + messages → LLM → calls      │  │
│  │  → execute → append → repeat until termination       │  │
│  └───────────────────────────────────────────────────────┘  │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│                         TOOL LAYER                           │
│  Read: search_graph, get_node_neighborhood, get_node,       │
│         get_transcript_span, list_transcripts,              │
│         get_node_log_archive, get_theme                     │
│  Write: create_node, update_node, create_edge,              │
│         update_edge, delete_node, delete_edge               │
│  Theme: create_theme, update_theme, retire_theme            │
│  Control: complete_ingestion                                │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│               HARNESS CORE / JOBS / TOKEN REGISTRY          │
│   provenance validation · token minting · theme queue       │
│   log compression scheduling                                │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│                       STORAGE LAYER                          │
│   FalkorDB graph · transcript store · cold storage          │
└──────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component               | Responsibility                                                                                                      | Boundary                                                                          |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Script Entry Points     | Operator-facing Python scripts for ingestion, querying, and inspection                                               | Thin wrappers over harness entrypoints; no agent logic                            |
| Agent Harness           | Runs the LLM tool-calling loop; owns termination detection; validates provenance on writes; mints sequential tokens | Single Python class or function; shared across all three agent modes              |
| Ingestion Prompt Config | System prompt for ingestion mode; determines agent behavior during graph build                                      | Data, not code — swap prompt to change behavior                                   |
| Query Prompt Config     | System prompt for query mode; instructs progressive retrieval and citation grounding                                | Data, not code                                                                    |
| Theme Prompt Config     | System prompt for theme maintenance; operates on delta, not full graph                                              | Data, not code                                                                    |
| Tool Layer              | Python functions registered as LLM tools; reads/writes to FalkorDB and transcript store                             | Each tool is independently testable; harness calls them by name                   |
| Harness Core            | Loop execution: call LLM → execute tool → append result → loop; provenance guard on writes                          | Does not know semantics — only routes calls and enforces harness-level invariants |
| Token Registry          | Global counter per entity type (node:N, edge:N, rec:N); mints next ID on create calls                               | Persisted in FalkorDB; never delegated to LLM                                     |
| Background Job Queue    | Async queue for theme agent runs and log compression; serializes theme runs                                         | Prevents race conditions; user never waits on these                               |
| FalkorDB                | Native graph storage: nodes, edges with logs, themes, token counters, bidirectional index                           | All graph state lives here; can be fully rebuilt from transcripts                 |
| Transcript Store        | Canonical text records with segment-level timestamps; append-only                                                   | Source of truth; never mutated after write                                        |
| Cold Storage            | Archive of pre-compression log entries keyed by node/edge ID                                                        | Not a primary path; accessed only via `get_node_log_archive`                      |

---

## The Agent Harness — Core Pattern

The harness is the most architecturally significant component. It is a simple loop, not a framework.

### Loop Structure (Pure Python)

```python
def run_agent(system_prompt, tools, initial_messages, context):
    messages = [system_message(system_prompt)] + initial_messages
    while True:
        response = llm.chat(messages=messages, tools=tools)
        if response.stop_reason == "end_turn":
            return extract_answer(response)
        for tool_call in response.tool_calls:
            if tool_call.name == "complete_ingestion":
                result = handle_complete_ingestion(tool_call.args, context)
                messages.append(tool_result(tool_call.id, result))
                return result
            result = dispatch_tool(tool_call.name, tool_call.args, context)
            messages.append(assistant_turn(response))
            messages.append(tool_result(tool_call.id, result))
```

This is approximately 30 lines of Python. No framework is needed for this loop structure.

### Why Not LangGraph

LangGraph imposes a graph-of-nodes execution model where each node is a processing step and edges are conditional transitions. It is designed for multi-agent orchestration, human-in-the-loop workflows, and complex branching state machines.

Arakne's harness is a single-agent tool loop with two exit conditions: natural `end_turn` or explicit `complete_ingestion()`. There are no branches, no parallel agents, no human checkpoints, and no stateful graph nodes. LangGraph's abstractions add overhead and indirection without providing anything the architecture needs.

Verdict: LangGraph is overkill. It solves a harder coordination problem than this system has.

### Why Not Full LangChain

LangChain provides chains, agents, and tool-calling abstractions. Its `AgentExecutor` would handle the loop, but wraps it in abstraction that makes it harder to inspect tool call/result pairs directly, harder to implement the harness-owned invariants (provenance validation, token minting), and introduces a large dependency tree.

The harness needs to intercept writes before execution to validate provenance. LangChain's executor assumes tools are opaque. Getting provenance validation and token minting to sit between the LLM call and tool execution is awkward in LangChain's architecture.

Verdict: LangChain adds friction to the invariants this harness must own. Not recommended.

### Framework Recommendation

Use pure Python with the LLM provider's SDK directly. The harness is a thin loop that:

1. Manages the message array.
2. Intercepts write tool calls to validate provenance before execution.
3. Intercepts `create_node` / `create_edge` to mint tokens before delegating.
4. Detects `complete_ingestion()` and treats it as loop termination.
5. Enforces serialization of theme agent runs via a job queue.

---

## Component Boundaries — What Talks to What

```
Script Entry Points
  ↕  Python function call
Agent Harness
  ↕  Tool dispatch
Tool Functions
  ↕  FalkorDB driver / file I/O
Storage Layer

Background Job Queue
  ← triggered by: complete_ingestion payload
  → runs: Theme Agent (harness with theme prompt)
  → runs: Log Compression (non-agentic, deterministic)
```

### Strict Boundaries

- The **LLM never talks directly to storage**. All storage access goes through named tool functions that the harness dispatches.
- The **harness never interprets semantic content**. It validates structure but not meaning.
- The **theme agent never runs inline** with ingestion. It is always a background job. If it fails, the graph is still valid; only the orientation map is stale.
- The **token registry is owned by the harness**, not by tool functions. Token minting happens in the dispatch layer before the create calls run.

---

## Data Flow

### Ingestion Flow

```
Local ingestion script
  → Audio file path passed to transcription layer
  → Whisper transcription → transcript record written (rec:N minted)
  → Transcript text with inline segment-level timestamps rendered
  → Agent Harness launched with ingestion system prompt
      + full transcript text
      + hot themes block (k themes) + cold theme index
      + current time injected as human-readable string
  → LLM tool-calling loop:
      search_graph()           → identify existing relevant nodes
      get_node_neighborhood()  → explore local graph context
      get_node()               → read full node history if needed
      create_node() / update_node()   → harness mints token, validates provenance
      create_edge() / update_edge()   → harness mints token, validates provenance
      complete_ingestion(summary, touched_nodes, touched_edges)
          → harness catches this call as termination signal
          → payload written to transcript record (bidirectional index populated)
          → loop exits
  → Background queue receives (transcript_id, touched_nodes, touched_edges)
  → Theme agent job enqueued (serialized)
  → Log compression job enqueued (deterministic, non-agentic)
  → Script returns completion summary to operator
```

### Query Flow

```
Local query script
  → Question text passed to harness
  → Agent Harness launched with query system prompt
      + user question
      + hot themes block (k themes) + cold theme index
      + current time injected
  → LLM tool-calling loop (progressive disclosure):
      [Tier 1] Hot themes already in context → may skip to get_node_neighborhood
      [Tier 2] search_graph(query)           → candidate nodes with summaries
      [Tier 3] get_node_neighborhood(id)     → local graph context
      [Tier 4] get_node(id)                  → full node history
      [Archive] get_node_log_archive(id)     → only if compression entry found
      get_transcript_span(rec:N, start, end) → exact quoted text for citations
      [Optional] list_transcripts(date_range) → temporal queries
      [Optional] get_theme(name)             → cold-index themes on demand
  → LLM produces answer with inline citations (transcript_id + offsets)
  → Loop exits on end_turn
  → Script prints answer + citation metadata
```

### Theme Agent Flow (Background)

```
complete_ingestion payload received by job queue
  → Dequeued (serialized — no parallel theme runs)
  → Agent Harness launched with theme system prompt
      + FULL themes map
      + ingestion completion payload (summary, touched_nodes, touched_edges)
      + read tools available
  → LLM tool-calling loop (delta-only):
      get_node() / get_node_neighborhood() on touched_nodes only
      update_theme() / create_theme() / retire_theme() as needed
      decide hot-set membership for next sessions
  → Loop exits on end_turn
  → Updated themes persisted to FalkorDB
```

### Log Compression Flow (Non-Agentic)

```
Post-ingestion background job
  → For each touched node/edge:
      count tokens in log entries
      if over budget:
          call LLM once (not in loop) to produce arc summary of older entries
          write compression entry inline with get_node_log_archive reference
          move raw entries to cold storage keyed by node_id
  → Deterministic, inspectable — not an agent loop
```

---

## Recommended Project Structure

```
arakne/
├── src/
│   ├── harness/
│   │   ├── __init__.py
│   │   ├── loop.py
│   │   ├── dispatch.py
│   │   ├── tokens.py
│   │   └── context.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── read.py
│   │   ├── write.py
│   │   ├── theme.py
│   │   └── control.py
│   ├── prompts/
│   │   ├── ingestion.py
│   │   ├── query.py
│   │   └── theme.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── graph.py
│   │   ├── transcripts.py
│   │   └── cold.py
│   ├── jobs/
│   │   ├── __init__.py
│   │   ├── queue.py
│   │   ├── theme_job.py
│   │   └── compress_job.py
│   └── transcription/
│       ├── __init__.py
│       └── whisper.py
├── scripts/
│   ├── ingest_audio.py
│   ├── ingest_transcript.py
│   ├── query_memory.py
│   └── inspect_graph.py
├── tests/
│   ├── harness/
│   ├── tools/
│   ├── jobs/
│   └── flows/
├── devenv.nix
└── pyproject.toml
```

### Structure Rationale

- **harness/** isolates the loop, the most unique and testable component.
- **tools/** keeps storage actions in independently testable functions.
- **prompts/** isolates behavior changes from runtime changes.
- **storage/** ensures nothing outside the storage layer writes Cypher directly.
- **jobs/** preserves the correctness boundary between synchronous ingestion and asynchronous maintenance.
- **scripts/** provide the only operator-facing surface needed in the current scope.

---

## Architectural Patterns

### Pattern 1: Harness-Owned Invariants (Do Not Delegate to LLM)

Three invariants belong in the harness dispatch layer before any tool function runs: provenance validation on writes, token minting on creates, and theme-agent serialization.

### Pattern 2: Termination via Special Tool Call

The ingestion loop terminates when the agent calls `complete_ingestion()` rather than by reaching `end_turn`. This doubles as a structured audit log and background-job trigger.

### Pattern 3: Progressive Disclosure — Tiered Read Tools

Read tools are tiered by information density. Each tier returns just enough to decide whether to descend further. The agent never receives more than it asked for.

### Pattern 4: Hot/Cold Orientation Map

The hot themes block plus cold index is injected into every query and ingestion session prompt without a tool call. The agent starts oriented, not blind.

---

## Anti-Patterns

### Anti-Pattern 1: Letting the LLM Pick Its Own IDs

The harness must mint sequential tokens. The LLM should only propose aliases, summaries, and relationships.

### Anti-Pattern 2: Inline Theme Update During Ingestion

Theme analysis is a separate cognitive task. Keep it asynchronous and delta-driven.

### Anti-Pattern 3: Log Compression as Part of the Agent Loop

Compression is a deterministic maintenance operation. It should not bloat the ingestion loop.

### Anti-Pattern 4: Full Graph Scan in Theme Agent

The theme agent should only look at the `touched_nodes` delta and their neighborhoods.

### Anti-Pattern 5: Hardcoding Semantic Routing in the Harness

The harness routes by tool name, never by semantic content. Semantic decisions belong in prompts.

---

## Implementation Order — Component Dependencies

```
Step 1 — Storage Foundation (no dependencies)
  FalkorDB schema
  Transcript store
  Cold storage

Step 2 — Tool Layer (depends on Step 1)
  Read tools
  Write tools
  Transcript tools
  Theme tools
  Control tool

Step 3 — Harness Core (depends on Step 2)
  Token registry and minting
  Provenance validator
  Tool dispatch
  Loop runner
  Termination detection

Step 4 — Agent Modes (depends on Step 3)
  Ingestion prompt + harness wiring
  Theme prompt + harness wiring + background job
  Query prompt + harness wiring

Step 5 — Transcription Pipeline (depends on Step 4)
  Whisper integration
  Segment-boundary timestamp rendering
  rec:N minting

Step 6 — Script Entry Points (depends on Step 5)
  ingest_audio.py
  ingest_transcript.py
  query_memory.py
  inspect_graph.py
```

### Dependency Rationale

- **Storage before tools**: tools are wrappers over storage queries.
- **Tools before harness**: the harness dispatches to tools.
- **Harness before agent modes**: agent modes are harness + prompt.
- **Ingestion before theme**: the theme agent is triggered by `complete_ingestion()`.
- **Ingestion before query**: the query agent only returns useful answers if there is data in the graph.
- **Transcription before scripts**: scripts are thin wrappers and should come after the underlying pipeline is stable.

---

## Integration Points

### External Services

| Service                           | Integration Pattern           | Notes                                                                                                          |
| --------------------------------- | ----------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Whisper                           | Groq Whisper via `litellm`    | `whisper-large-v3-turbo` currently returns both word- and segment-level timestamps; the system uses segments |
| LLM Provider (OpenAI / Anthropic) | Direct SDK, not via framework | Swap by changing the client in harness/loop.py                                                                 |
| FalkorDB                          | Python driver (`falkordb`)    | All queries in `storage/graph.py`; rest of system never writes Cypher                                          |

### Internal Boundaries

| Boundary               | Communication                                                  | Invariant                                                          |
| ---------------------- | -------------------------------------------------------------- | ------------------------------------------------------------------ |
| Harness ↔ Tool Layer   | Python function call via dispatch                              | Harness validates provenance and mints tokens before calling tools |
| Scripts ↔ Harness      | Direct Python call                                             | Scripts do not know about LLM or tools                             |
| Ingestion ↔ Theme Job  | Job queue message (`transcript_id` + completion payload)       | Never in-process; always async                                     |
| Storage ↔ Tools        | FalkorDB driver calls inside storage module                    | Tools never call FalkorDB directly                                 |
| Theme Job ↔ Harness    | Same harness, different system prompt                          | Theme job is a harness call, not a special code path               |

---

## Sources

- `/home/shivang/shivang/projs/arakne/markdowns/Memory-v5.md` — primary architecture source
- `/home/shivang/shivang/projs/arakne/markdowns/planning/PROJECT.md` — product requirements and constraints
- Training data on LangGraph / LangChain through Aug 2025 — framework comparison context
- Installed FalkorDB package metadata and historical project code — storage/tooling context
