# Architecture Research

**Domain:** Agentic memory system — AI voice journaling with 3-layer backend
**Researched:** 2026-04-01
**Confidence:** HIGH (primary source is the project's own authoritative spec, Memory-v5.md)

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                         MOBILE CLIENT                            │
│  Voice Capture → Audio File → Backend API → Answer + Citations   │
└──────────────────────────┬───────────────────────────────────────┘
                           │ HTTP (audio upload / question text)
┌──────────────────────────▼───────────────────────────────────────┐
│                         BACKEND API                              │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │              AGENT HARNESS (shared runtime)               │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │    │
│  │  │  Ingestion  │  │    Query    │  │     Theme       │  │    │
│  │  │   Prompt    │  │   Prompt    │  │     Prompt      │  │    │
│  │  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘  │    │
│  │         │                │                  │           │    │
│  │         ▼                ▼                  ▼           │    │
│  │  ┌───────────────────────────────────────────────────┐  │    │
│  │  │           LLM Tool-Calling Loop                   │  │    │
│  │  │  system_prompt + tools + messages → LLM → calls   │  │    │
│  │  │  → execute → append → repeat until termination    │  │    │
│  │  └───────────────────────────────────────────────────┘  │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                    TOOL LAYER                             │    │
│  │  Read: search_graph, get_node_neighborhood, get_node,    │    │
│  │         get_transcript_span, list_transcripts,           │    │
│  │         get_node_log_archive, get_theme                  │    │
│  │  Write: create_node, update_node, create_edge,           │    │
│  │         update_edge, delete_node, delete_edge            │    │
│  │  Theme: create_theme, update_theme, retire_theme         │    │
│  │  Control: complete_ingestion                             │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐  │
│  │   Harness Core   │  │ Background Jobs  │  │  Token Reg.   │  │
│  │  (loop + valid.) │  │ (theme, compress) │  │ (seq IDs)     │  │
│  └────────┬─────────┘  └────────┬─────────┘  └───────┬───────┘  │
└───────────┼─────────────────────┼────────────────────┼──────────┘
            │                     │                    │
┌───────────▼─────────────────────▼────────────────────▼──────────┐
│                       STORAGE LAYER                              │
│  ┌───────────────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │     FalkorDB      │  │  Transcript Store │  │ Cold Storage │  │
│  │  (graph: nodes,   │  │  (canonical text, │  │  (archive of │  │
│  │   edges, themes,  │  │   timestamps,     │  │   compressed │  │
│  │   token registry) │  │   audio file ref) │  │   log entries│  │
│  └───────────────────┘  └──────────────────┘  └──────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Boundary |
|-----------|----------------|----------|
| Mobile Client | Voice capture, audio upload, question input, answer display | Sends audio/text to backend; receives structured answers |
| Backend API | HTTP entry points for record upload and query; orchestrates harness launch | Does not contain agent logic; delegates to harness |
| Agent Harness | Runs the LLM tool-calling loop; owns termination detection; validates provenance on writes; mints sequential tokens | Single Python class or function; shared across all three agent modes |
| Ingestion Prompt Config | System prompt for ingestion mode; determines agent behavior during graph build | Data, not code — swap prompt to change behavior |
| Query Prompt Config | System prompt for query mode; instructs progressive retrieval and citation grounding | Data, not code |
| Theme Prompt Config | System prompt for theme maintenance; operates on delta, not full graph | Data, not code |
| Tool Layer | Python functions registered as LLM tools; reads/writes to FalkorDB and transcript store | Each tool is independently testable; harness calls them by name |
| Harness Core | Loop execution: call LLM → execute tool → append result → loop; provenance guard on writes | Does not know semantics — only routes calls and enforces harness-level invariants |
| Token Registry | Global counter per entity type (node:N, edge:N, rec:N); mints next ID on create calls | Persisted in FalkorDB; never delegated to LLM |
| Background Job Queue | Async queue for theme agent runs and log compression; serializes theme runs | Prevents race conditions; user never waits on these |
| FalkorDB | Native graph storage: nodes, edges with logs, themes, token counters, bidirectional index | All graph state lives here; can be fully rebuilt from transcripts |
| Transcript Store | Canonical text records with sentence-level timestamps; append-only | Source of truth; never mutated after write |
| Cold Storage | Archive of pre-compression log entries keyed by node/edge ID | Not a primary path; accessed only via get_node_log_archive tool |

---

## The Agent Harness — Core Pattern

The harness is the most architecturally significant component. It is a simple loop, not a framework.

### Loop Structure (Pure Python)

```
def run_agent(system_prompt, tools, initial_messages, context):
    messages = [system_message(system_prompt)] + initial_messages
    while True:
        response = llm.chat(messages=messages, tools=tools)
        if response.stop_reason == "end_turn":
            # No more tool calls — final answer produced
            return extract_answer(response)
        for tool_call in response.tool_calls:
            if tool_call.name == "complete_ingestion":
                result = handle_complete_ingestion(tool_call.args, context)
                messages.append(tool_result(tool_call.id, result))
                return result  # Explicit termination — caller gets payload
            result = dispatch_tool(tool_call.name, tool_call.args, context)
            messages.append(assistant_turn(response))
            messages.append(tool_result(tool_call.id, result))
```

This is approximately 30 lines of Python. No framework needed for this loop structure.

### Why Not LangGraph

LangGraph imposes a graph-of-nodes execution model where each node is a processing step and edges are conditional transitions. It is designed for multi-agent orchestration, human-in-the-loop workflows, and complex branching state machines.

Arachne's harness is a single-agent tool loop with two exit conditions: natural end_turn or explicit complete_ingestion(). There are no branches, no parallel agents, no human checkpoints, and no stateful graph nodes. LangGraph's abstractions add overhead and indirection without providing anything the architecture needs.

Verdict: LangGraph is overkill. It solves a harder coordination problem than this system has.
**Confidence: MEDIUM** (based on training knowledge of LangGraph's design; no live docs available to verify current API)

### Why Not Full LangChain

LangChain provides chains, agents, and tool-calling abstractions. Its `AgentExecutor` would handle the loop, but wraps it in abstraction that makes it harder to inspect tool call/result pairs directly, harder to implement the harness-owned invariants (provenance validation, token minting), and introduces a large dependency tree.

The harness needs to intercept writes before execution to validate provenance. LangChain's executor assumes tools are opaque. Getting provenance validation and token minting to sit between the LLM call and tool execution is awkward in LangChain's architecture.

Verdict: LangChain adds friction to the invariants this harness must own. Not recommended.
**Confidence: MEDIUM** (based on training knowledge of LangChain's AgentExecutor model)

### Why Pure OpenAI Function Calling (via SDK) Is Correct

The OpenAI chat completions API (or Anthropic equivalent) with tool definitions is exactly the right primitive. The loop is visible, the harness owns the dispatch, and there is nothing between the LLM response and the tool execution that the harness does not control.

Arachne uses Python, so either `openai` SDK (if using OpenAI models) or `anthropic` SDK (if using Claude) provides the raw tool-calling interface. The harness loop is a Python `while True` with ~5 meaningful lines of logic.

Verdict: Pure SDK tool-calling loop with thin harness wrapper is the correct architecture.
**Confidence: HIGH** (directly follows from Memory-v5.md design, which explicitly calls for one harness across three modes)

### Framework Recommendation

**Use pure Python with the LLM provider's SDK directly.** The harness is a thin loop that:
1. Manages the message array (append assistant turns + tool results)
2. Intercepts write tool calls to validate provenance before execution
3. Intercepts create_node/create_edge to mint tokens before delegating
4. Detects complete_ingestion() and treats it as loop termination
5. Enforces serialization of theme agent runs via a job queue

A helper library like `instructor` (for structured output parsing) is acceptable if needed, but even that is optional given the free-form nature of the agent's decisions.

---

## Component Boundaries — What Talks to What

```
Mobile Client
  ↕  HTTP/REST
Backend API
  ↕  Python function call
Agent Harness
  ↕  Tool dispatch
Tool Functions
  ↕  FalkorDB driver / file I/O
Storage Layer

Background Job Queue
  ← triggered by: complete_ingestion payload (via Backend API)
  → runs: Theme Agent (harness with theme prompt)
  → runs: Log Compression (non-agentic, deterministic)
```

### Strict Boundaries

- The **LLM never talks directly to storage**. All storage access goes through named tool functions that the harness dispatches.
- The **harness never interprets semantic content**. It validates structure (provenance fields present, token format valid) but not meaning.
- The **theme agent never runs inline** with ingestion. It is always a background job. If it fails, the graph is still valid; only the orientation map is stale.
- The **token registry is owned by the harness**, not by tool functions. Token minting happens in the dispatch layer before the create_node/create_edge tool function runs.

---

## Data Flow

### Ingestion Flow

```
Voice Recording (mobile)
  → Audio file uploaded to Backend API
  → Whisper transcription → transcript record written (rec:N minted)
  → Transcript text with inline sentence-level timestamps rendered
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
  → API returns 200 to mobile client
```

### Query Flow

```
User question (mobile)
  → Backend API receives question text
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
  → Loop exits on end_turn (no complete_ingestion in query mode)
  → API returns answer + citation metadata to mobile client
```

### Theme Agent Flow (Background)

```
complete_ingestion payload received by job queue
  → Dequeued (serialized — no parallel theme runs)
  → Agent Harness launched with theme system prompt
      + FULL themes map (unlike query/ingestion which get hot+cold index)
      + ingestion completion payload (summary, touched_nodes, touched_edges)
      + read tools available
  → LLM tool-calling loop (delta-only):
      get_node() / get_node_neighborhood() on touched_nodes only
      update_theme() / create_theme() / retire_theme() as needed
      Decides hot-set membership for next sessions
  → Loop exits on end_turn (no special termination call)
  → Updated themes persisted to FalkorDB
```

### Log Compression Flow (Non-Agentic)

```
Post-ingestion background job
  → For each touched node/edge:
      Count tokens in log entries
      If over budget:
          Call LLM once (not in loop) to produce arc summary of older entries
          Write compression entry inline with get_node_log_archive reference
          Move raw entries to cold storage keyed by node_id
  → Deterministic, inspectable — not an agent loop
```

---

## Recommended Project Structure

```
arachne/
├── src/
│   ├── harness/
│   │   ├── __init__.py
│   │   ├── loop.py           # Core tool-calling loop, termination detection
│   │   ├── dispatch.py       # Tool name → function routing; provenance guard
│   │   ├── tokens.py         # Sequential token minting and registry
│   │   └── context.py        # Session context: current_time, transcript, themes
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── read.py           # search_graph, get_node*, get_transcript_span, etc.
│   │   ├── write.py          # create_node, update_node, create_edge, etc.
│   │   ├── theme.py          # create_theme, update_theme, retire_theme
│   │   └── control.py        # complete_ingestion (termination tool)
│   │
│   ├── prompts/
│   │   ├── ingestion.py      # Ingestion system prompt builder
│   │   ├── query.py          # Query system prompt builder
│   │   └── theme.py          # Theme agent system prompt builder
│   │
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── graph.py          # FalkorDB client, queries, schema ops
│   │   ├── transcripts.py    # Transcript store: read, write, span retrieval
│   │   └── cold.py           # Cold storage for archived log entries
│   │
│   ├── jobs/
│   │   ├── __init__.py
│   │   ├── queue.py          # Background job queue (simple async or taskiq)
│   │   ├── theme_job.py      # Theme agent job: receives delta, runs harness
│   │   └── compress_job.py   # Log compression job: deterministic, no LLM loop
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py         # FastAPI routes: /record, /query
│   │   └── schemas.py        # Request/response models
│   │
│   └── transcription/
│       ├── __init__.py
│       └── whisper.py        # Whisper integration, timestamp rendering
│
├── tests/
│   ├── harness/              # Loop tests: termination, provenance guard
│   ├── tools/                # Tool unit tests with FalkorDB test fixture
│   ├── jobs/                 # Background job integration tests
│   └── flows/                # End-to-end: ingest transcript → query answer
│
├── devenv.nix                # FalkorDB, Python, dependencies declared here
└── pyproject.toml
```

### Structure Rationale

- **harness/**: The loop is the system's most unique and testable component. Isolated so it can be tested without storage or LLM calls (mock the LLM, check loop behavior).
- **tools/**: Each tool is a pure function against storage. Independently testable. The harness only knows tool names and schemas.
- **prompts/**: Prompts are code — they are builders that inject session context (time, themes, transcript). Isolating them enables A/B testing and iteration without touching loop logic.
- **storage/**: All FalkorDB queries live here. The rest of the system never writes Cypher directly — this boundary makes storage swappable.
- **jobs/**: The async separation between ingestion and theme/compression is a correctness boundary, not just a performance boundary. Isolating jobs prevents theme runs from blocking ingestion response time.

---

## Architectural Patterns

### Pattern 1: Harness-Owned Invariants (Do Not Delegate to LLM)

**What:** Three invariants are enforced by the harness dispatch layer before any tool function runs: (a) provenance validation on writes, (b) token minting on creates, (c) theme agent serialization.

**When to use:** Any invariant that must hold regardless of LLM output. LLMs can hallucinate tool arguments. The harness is the last safety boundary before storage mutation.

**Trade-offs:** Makes the dispatch layer slightly more complex, but eliminates entire classes of corruption bugs. The alternative — relying on the LLM to always provide provenance — is not safe.

```python
def dispatch_tool(name, args, context):
    if name in WRITE_TOOLS:
        validate_provenance(args)  # raises if missing transcript_id/offsets
    if name in CREATE_TOOLS:
        args["id"] = mint_next_token(name, context.registry)
    return TOOL_REGISTRY[name](args, context)
```

### Pattern 2: Termination via Special Tool Call

**What:** The ingestion loop terminates when the agent calls `complete_ingestion()` rather than by reaching `end_turn`. This double-duties as a structured audit log and as the trigger for downstream jobs.

**When to use:** When the loop needs to produce a structured payload at termination, not just a text answer. The payload (summary + touched_nodes + touched_edges) populates the bidirectional index and seeds background jobs.

**Trade-offs:** Requires the system prompt to clearly instruct the agent that `complete_ingestion` is mandatory. If the agent forgets, the harness can implement a max-turn fallback that synthesizes the payload from the session's tool call history.

```python
if tool_call.name == "complete_ingestion":
    record_ingestion_completion(tool_call.args, context.transcript_id)
    enqueue_theme_job(tool_call.args)
    enqueue_compression_job(context.transcript_id, tool_call.args["touched_nodes"])
    return tool_call.args  # also returned as tool result to close the message array cleanly
```

### Pattern 3: Progressive Disclosure — Tiered Read Tools

**What:** Read tools are tiered by information density. Each tier returns just enough to decide whether to descend further. The agent never receives more than it asked for, preserving token budget for reasoning.

**When to use:** Any agentic system where the data space is large and most queries only need a fraction of it. The tiers (search → neighborhood → full node → archive) mirror how a human expert navigates: scan → skim → read → deep research.

**Trade-offs:** Requires good tool descriptions so the LLM knows when to use each tier. The payoff is that most queries resolve at Tier 2-3, leaving room in the context window for reasoning and answer generation.

### Pattern 4: Hot/Cold Orientation Map (Always-In-Context Themes)

**What:** The hot themes block (k full theme records) plus cold index (remaining theme names) is injected into every query and ingestion session prompt without a tool call. The agent starts oriented, not blind.

**When to use:** Any agentic system where a cold-start orientation problem exists. Without this, the first N tokens of every session would be wasted on search_graph calls to discover what territory exists.

**Trade-offs:** The hot set must be maintained by the theme agent as an editorial judgment, not a mechanical sort. Maintaining it poorly (wrong themes in hot set) degrades first-move efficiency. The cold index is the safety net — themes not in the hot set are still discoverable.

---

## Anti-Patterns

### Anti-Pattern 1: Letting the LLM Pick Its Own IDs

**What people do:** Ask the LLM to generate a name or identifier for a new node/edge and use that directly as the storage key.

**Why it's wrong:** LLMs produce inconsistent, high-entropy identifiers — "anxiety_about_career_transition_2024" one time, "career-anxiety" the next. Cross-references in tool calls become unreliable. The system accumulates duplicate nodes for the same concept. Sequential tokens (node:12) are unambiguous and memorable.

**Do this instead:** The harness mints the next sequential token at dispatch time. The LLM provides aliases and summary; the harness provides the ID.

### Anti-Pattern 2: Inline Theme Update During Ingestion

**What people do:** Have the ingestion agent also update the themes map as part of the same tool loop, to save a round-trip.

**Why it's wrong:** Theme analysis requires reading the full themes map and making editorial judgments about theme topology. Doing this inline bloats the ingestion loop's context window, conflates two different cognitive tasks, and slows the synchronous response. Theme updates only need to happen before the next session — the user never waits on them.

**Do this instead:** Complete ingestion first (complete_ingestion() as termination), then run the theme agent as a background job.

### Anti-Pattern 3: Log Compression as Part of the Agent Loop

**What people do:** Have the ingestion agent detect when logs are large and compress them inline as part of the write loop.

**Why it's wrong:** Compression is a deterministic mechanical operation — count tokens, summarize, archive. It does not require an LLM loop. Running it inline adds latency to every ingestion and creates risk of the agent compressing logs mid-write when some entries are not yet finalized.

**Do this instead:** Log compression runs as a post-ingestion background job. It calls the LLM once (not in a loop) to produce the arc summary, then performs the mechanical archival.

### Anti-Pattern 4: Full Graph Scan in Theme Agent

**What people do:** Have the theme agent read all nodes to ensure no theme is out of date.

**Why it's wrong:** At 500+ nodes this becomes expensive. The ingestion agent already identified what changed. The theme agent only needs to look at the touched_nodes delta. Everything else is definitionally unchanged from the last theme run.

**Do this instead:** Pass the touched_nodes list from the complete_ingestion payload. The theme agent reads those nodes and their neighborhoods only.

### Anti-Pattern 5: Hardcoding Routing Logic in the Harness

**What people do:** Add `if this is an emotion node, call X; if this is a decision node, call Y` logic to the harness dispatch layer.

**Why it's wrong:** The architecture's core design principle is that all semantic decisions are delegated to the LLM. Hardcoded routing reintroduces schema rigidity and breaks the moment the LLM creates a node type not anticipated at implementation time. There is no type field on nodes by design.

**Do this instead:** The harness routes only by tool name, never by semantic content. Routing logic lives entirely in the system prompt as natural language instructions.

---

## Build Order — Component Dependencies

The architecture has hard dependencies that dictate build order:

```
Phase 1 — Storage Foundation (no dependencies)
  FalkorDB schema (nodes, edges, themes, token registry)
  Transcript store
  Cold storage

Phase 2 — Tool Layer (depends on Phase 1)
  Read tools (search_graph, get_node_neighborhood, get_node, etc.)
  Write tools (create_node, update_node, create_edge, etc.)
  Transcript tools (get_transcript_span, list_transcripts)
  Theme tools (create_theme, update_theme, retire_theme)
  Control tool (complete_ingestion)

Phase 3 — Harness Core (depends on Phase 2)
  Token registry and minting
  Provenance validator
  Tool dispatch
  Loop runner
  Termination detection

Phase 4 — Agent Modes (depends on Phase 3)
  Ingestion system prompt + harness wiring
  [Test: full transcript → graph]
  Theme system prompt + harness wiring + background job
  [Test: ingestion delta → theme update]
  Query system prompt + harness wiring
  [Test: question → cited answer]

Phase 5 — Transcription Pipeline (depends on Phase 4)
  Whisper integration
  Sentence-boundary timestamp rendering
  rec:N minting

Phase 6 — API + Mobile Client (depends on Phase 5)
  FastAPI endpoints (/record, /query)
  Mobile voice recording
  Answer display with citation spans
```

### Dependency Rationale

- **Storage before tools**: Tools are wrappers over storage queries. Cannot test tools without storage.
- **Tools before harness**: The harness dispatches to tools. Cannot test the loop without real tool implementations (mocked LLM + real tools is the first useful test).
- **Harness before agent modes**: Agent modes are harness + prompt. The harness must be correct before prompts can be evaluated.
- **Ingestion before theme**: The theme agent is triggered by complete_ingestion(). Cannot test theme agent end-to-end without a working ingestion path.
- **Ingestion before query**: The query agent only returns useful answers if there is data in the graph. Build ingestion first.
- **Transcription before API**: The API endpoint triggers transcription then ingestion. Both must exist before the endpoint makes sense.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Whisper | Local inference via Python library (whisperx or faster-whisper) | Word-level timestamps required; sentence-boundary rendering in harness |
| LLM Provider (OpenAI / Anthropic) | Direct SDK, not via framework | Swap by changing the client in harness/loop.py |
| FalkorDB | Python driver (falkordb-py) | All queries in storage/graph.py; rest of system never writes Cypher |

### Internal Boundaries

| Boundary | Communication | Invariant |
|----------|---------------|-----------|
| Harness ↔ Tool Layer | Python function call via dispatch | Harness validates provenance and mints tokens before calling tools |
| API ↔ Harness | Direct Python call (sync for query, async for ingestion launch) | API does not know about LLM or tools |
| Ingestion ↔ Theme Job | Job queue message (transcript_id + complete_ingestion payload) | Never in-process; always async |
| Storage ↔ Tools | FalkorDB driver calls inside storage module | Tools never call FalkorDB directly |
| Theme Job ↔ Harness | Same harness, different system prompt | Theme job is a harness call, not a special code path |

---

## Scaling Considerations

This is a single-user, privacy-first, local-data system in v1. Scaling targets are personal use throughput, not multi-tenant scale.

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1 user / personal | Monolith is correct. SQLite or file store viable for transcripts. FalkorDB local. |
| 10-50 users (self-hosted) | Same monolith. Add per-user graph isolation (separate FalkorDB keyspaces or node labels). |
| 100+ users (hosted) | Background job queue needs durability (Redis/ARQ or similar). Per-user FalkorDB instances or sharding. |
| 1000+ users | LLM call cost is the constraint, not architecture. Prompt caching, batching, and model tier selection become the levers. |

### Scaling Priorities

1. **First bottleneck:** LLM API latency and cost. Ingestion already runs async; query is the synchronous user-facing path. Cache hot themes aggressively (they change only when theme agent runs).
2. **Second bottleneck:** FalkorDB with many nodes per user. Graph traversal queries need indexes on node IDs and alias fields from day one — retrofit is painful.

---

## Sources

- Memory-v5.md (primary source — project's own authoritative architecture spec): `/home/shivang/shivang/projs/arachne/markdowns/Memory-v5.md`
- PROJECT.md (requirements and decisions): `/home/shivang/shivang/projs/arachne/.planning/PROJECT.md`
- LangGraph framework analysis: training data (MEDIUM confidence — framework landscape stable as of Aug 2025 cutoff; verify against current docs before committing)
- OpenAI Agents SDK / pure tool-calling pattern: training data (MEDIUM confidence — loop structure follows directly from OpenAI/Anthropic function calling APIs, which are stable)
- FalkorDB Python driver: training data (MEDIUM confidence — verify driver name and current API in devenv.nix before implementation)

---
*Architecture research for: Arachne — AI voice journaling with 3-layer memory backend*
*Researched: 2026-04-01*
