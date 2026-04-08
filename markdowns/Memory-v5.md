# The Memory

> How do you represent a human's evolving inner life in a data structure that supports arbitrary, open-ended queries without baking in assumptions about what questions will be asked?

## Goal

Design representation to be maximally expressive, and delegate query strategy entirely to the agent at query time. That leads to:

1. **LLM-Defined Semantic Graph** — no engineered schema. The most abstract, universally valid structure is defined, and all semantic decisions are left to the LLM. The system becomes more powerful as models improve.
2. **Agentic retrieval** — tell the LLM what is available, and it figures out how to find the answer.

The semantic graph and themes are not truth. They are derived, rebuildable caches built on top of the canonical source layers — transcripts and chat sessions — to make retrieval and orientation cheaper at runtime.

The structure that is universally valid for journaling:

1. Things (concepts, people, emotions, decisions, questions, themes): nodes
2. Relationships between things: edges with free-form natural language labels
3. The raw sources — transcripts and chat sessions: source of truth. Everything can be reconstructed from here.

**No rigid extraction schema.** The LLM is free to create whatever nodes and relationships it judges best. Structure emerges from the LLM's judgment guided by prompt-level directions, not from hardcoded constraints.

---

## Core Idea

Transcripts and chat sessions are the canonical records. Everything else is derived from them.

The semantic graph and themes are rebuildable working memory layers: useful, lossy, and replaceable. They exist to help the agent navigate, not to replace the source material. If the system regenerates them from transcripts and chat logs, no truth is lost — the canonical sources contain everything.

**Structurally rebuildable** means no truth is locked inside the semantic graph that doesn't also exist in the canonical sources. This is an architectural guarantee. **Operationally durable** means the semantic graph and its logs are maintained persistently in practice — the system does not routinely discard and rebuild them. Node logs are append-only and preserved for as long as the node lives.

---

## Infrastructure

**Graph database:** FalkorDB — stores the semantic graph, themes, transcript metadata, and all log entries. Single store for everything; no separate cold-storage tables.

**LLM and models:** litellm as the unified interface. Currently:

- **LLM:** Gemini (via litellm)
- **Embeddings:** gemini-embeddings-001 (via litellm)
- **Speech-to-text:** Whisper via Groq (via litellm)

**Token estimation:** tiktoken with cl100k_base encoding. Used for all token budget calculations — theme hot set rendering, log compression thresholds. Rust-based, runs locally, fast and consistent. Close enough for budget decisions across models.

**Audio-to-transcript pipeline:** A Python script calls Groq Whisper through litellm, producing a timestamped transcript. The raw audio file is always retained as a permanent artifact alongside the transcript. Recordings have an app-enforced time limit, so transcript length is bounded.

**Current form:** Python backend scripts. No API layer yet — designed so a FastAPI wrapper can be added later without restructuring the core logic.

### Data Model

Everything lives in a single FalkorDB store. Two terms are used precisely throughout this document:

- **The store** — the full FalkorDB database: all five node labels and all edge types below.
- **The semantic graph** — specifically the `(:SemanticNode)` nodes and `[:RELATES]` edges. This is the derived layer that agents build and query. When this document says "graph write operations," "search the graph," or "rebuild the graph," it means the semantic graph.

Initially FalkorDB was supposed to have only the semantic graph, but for now, have included everything except audio files to not deal with 2 stores.

The store contains five node labels and two edge types.

**Node labels:**

```
(:SemanticNode)    — semantic graph: concepts, people, emotions, decisions etc. what LLM judges fit
(:Transcript)      — transcript records (id, timestamp, audio_path, text)
(:ChatSession)     — chat session records (id, timestamp, messages)
(:Theme)           — theme records (name, state, status)
(:System)          — singleton config node (token counters, budgets, priority order)
```

Transcript, ChatSession, Theme, and System nodes are not part of the semantic graph — they are store-level entities. Transcript and ChatSession nodes are standalone records queried by property type (trancript or chatsession), date range and id, not by traversal. The link between canonical sources and semantic nodes is captured in node log entries via provenance. Theme nodes connect to the semantic graph only through `[:ANCHORS]` edges (see below).

**Edge types:**

```
(:SemanticNode)-[:RELATES {id, label}]->(:SemanticNode)
    Semantic edges. These are the free-form relationships the LLM creates.
    The edge id (e.g. edge:4) and label live here. Edges are lightweight —
    no log or history. When a relationship evolves, the agent updates the
    label. The narrative of why it changed lives in the node logs on either end.

(:Theme)-[:ANCHORS]->(:SemanticNode)
    Theme entry points into the semantic graph. A store-level edge that
    bridges the theme layer to the semantic graph. Replaces what would
    otherwise be an array of node IDs on the theme. Adding an anchor =
    creating an edge, removing = deleting one.
```

**The System node:**

```
(:System {
    next_node_id,           — counter for node:N tokens
    next_edge_id,           — counter for edge:N tokens
    next_rec_id,            — counter for rec:N tokens
    next_chat_id,           — counter for chat:N tokens
    theme_priority_order,   — ordered array of theme names for hot set rendering
    hot_theme_token_budget  — configurable threshold for hot set rendering
})
```

**Log serialization:** FalkorDB cannot store maps as property values. Log entries (`{source_id, timestamp, start_offset, end_offset, note}`) are stored as JSON-serialized strings in an array property on the node. The harness serializes on write and deserializes on read — timestamps are stored as datetime internally but surfaced to the agent as human-readable relative time. The agent never sees the JSON or raw datetimes — tool responses present logs as structured, readable objects.

**Vector index:** An HNSW vector index on `SemanticNode.embedding` powers the semantic half of `search_graph`. The embedding is generated from the node's summary + aliases via gemini-embeddings-001.

---

## Memory Layers

### Layer 1: Transcripts

The full transcript is stored as-is. The ingest agent reads the whole thing — meaning often depends on the full arc of a recording, and chunking is lossy.

Each transcript record:

- **id** — readable sequential token, e.g. `rec:7`. Primary key everywhere. No UUIDs — LLMs hallucinate high-entropy identifiers.
- **audio_path** — path to the retained raw audio file. The audio is a permanent artifact, never discarded.
- **timestamp** — When audio was recorded. Stored as datetime internally, always surfaced to the agent as human-readable relative time: `"3 weeks ago, Tuesday 24 Jun 2023, 11:42 PM"`. Harness injects current time at session start so the agent reasons naturally, never arithmetically.
- **text** — transcript from Whisper, presented to the agent with inline timestamps at whisper segment boundaries:
  ```
  [0:00] So I've been thinking about this career decision a lot lately.
  [0:14] I know I should probably just quit but the mortgage keeps stopping me.
  [0:28] And honestly I think I'm scared of what happens if I actually do it.
  ```
  Timestamps in the text are **seconds into the recording**. Groq Whisper returns both word-level and segment-level timestamps, but the system standardizes on segment boundaries and renders them as readable inline markers. These inline markers are what the agent reads during ingestion to identify provenance spans.

The link between transcripts and semantic nodes lives in the node log entries themselves — each log entry carries `(source_id, timestamp, start_offset, end_offset)` as provenance. No separate index is needed. To trace from a node back to the original recording, the agent reads the node's log and follows the provenance to `get_transcript_span`.

#### Chat Sessions

Chat sessions are tracked alongside transcripts as first-class entities with their own sequential tokens:

```
chat:7
```

A `chat:N` token is minted by the harness when a query/chat session starts. It serves as the provenance source for any graph modifications made during chat — corrections, new context, or updates the user offers conversationally. Chat sessions are canonical sources alongside transcripts: when a user corrects a fact, adds context, or surfaces something new during chat, that information carries the same authority as a voice recording. Chat sessions do not have audio but their conversation log is retained as a permanent artifact.

Each chat session record:

- **id** — e.g. `chat:7`
- **timestamp** — when the session started
- **messages** — the full conversation log, retained as a permanent canonical artifact. Stored as a JSON-serialized array of `{role, content}` entries.

Like transcripts, the link between chat sessions and semantic nodes lives in the node log entries — each chat-driven log entry carries `(chat:N, message_index, null)` as provenance, where `message_index` is the position in the messages array that sourced the write. The harness auto-records the message index on every chat-driven graph modification.

---

### Layer 2: Semantic Graph

The semantic graph is a derived semantic cache over the canonical sources (transcripts and chat sessions), not a canonical store itself. It is made of nodes and edges. The agent reads the full transcript and builds or updates the semantic graph in one pass, preserving the arc of how a topic starts, changes, and resolves.

All semantic decisions — what deserves a node, how to label a relationship, whether to update or create — are left entirely to the LLM. The ingestion prompt guides the agent to exercise judgment: extract what is meaningfully distinct, emotionally significant, or decision-relevant. Skip the rest.

The semantic graph exists to support retrieval, orientation, and synthesis. It is structurally rebuildable — if models or indexing strategy improve, it can be regenerated from canonical sources — but operationally durable: logs are append-only and maintained for as long as the node lives.

#### Identifiers

All identifiers are sequential readable tokens per entity type:

```
node:12    edge:4    rec:2    chat:7
```

These tokens are the primary keys — in the store, in provenance references, in the agent interface. The global token registry is a permanent first-class artifact of the system. The harness mints new tokens at creation time; the agent never picks its own. As the agent discovers nodes through tool calls, active tokens surface into the session context.

No concurrent writes — all ingestion and processing is sequential. The token registry is a simple counter per entity type.

#### Node Schema

```
id              — e.g. node:12
aliases         — [string]. aliases[0] is the canonical name.
summary         — current best description, rewritten when the agent judges it necessary when node is updated / created.
                   Serves as agent orientation and embedding target for semantic search.
embedding       — vector generated from summary + aliases via gemini-embeddings-001.
                   Updated lazily by a background job when summary or aliases change.
                   Powers the semantic half of search_graph via HNSW index.
total_log_count — integer. Total number of log entries on this node.
                   Incremented by the harness on every write. Used by read tools to hint
                   how much history exists.
log             — append-only list of JSON-serialized entry strings.

                   Entry format:
                     { source_id, timestamp, start_offset, end_offset, note }
                   source_id is rec:N for ingestion writes or chat:N for chat writes.
                   timestamp is stored as datetime internally, surfaced to the agent as
                   human-readable relative time (same convention as transcript timestamps).
                   For transcript sources, start_offset and end_offset are seconds into the
                   recording. For chat sources, start_offset is the message_index into the
                   chat's messages array and end_offset is null.
                   note is mandatory — the agent must provide a short description of what
                   this entry means for the node (what changed, emotional nuance, certainty,
                   stance). This makes each entry self-documenting at read time without
                   requiring a round-trip to the source transcript or chat.
                   The harness auto-creates the log entry shell from provenance on every
                   write; the agent's note is attached to it.
                   When a summary is rewritten, the harness archives the previous summary
                   into the note (e.g. "[archived summary] Previous text... | Agent note:
                   What changed and why."). This preserves prior summary states for
                   auditability.

                   The log array is ordered chronologically and append-only.
```

Aliases capture how people refer to the same thing across time — "my dad", "my father", "papa". `aliases[0]` is the canonical handle. The alias list is used by keyword search inside `search_graph` and enriches the embedding target alongside the summary.

There is no type field. A free-form type tag degrades over time — the agent produces "emotion", "feeling", "emotional state" for semantically identical things, making filtering unreliable. The summary carries all semantic meaning and is a better retrieval target.

#### Edge Schema

Semantic edges are stored as `[:RELATES]` edges between `(:SemanticNode)` nodes in FalkorDB:

```
id     — e.g. edge:4
label  — free-form natural language. This is the type and name of the relationship.
```

Edges are lightweight — just an id and a label. No log, no history, no cold summary. When a relationship evolves, the agent updates the label to reflect the current state. The narrative of why and how it changed lives in the node logs on either end, which already capture the context.

`from` and `to` are implicit in the edge direction. Edges do not have aliases — the label is the relationship's name and there is no parallel ambiguity problem.

#### Embeddings

Node embeddings (generated from summary + aliases via gemini-embeddings-001) power the semantic half of `search_graph`. Embeddings are regenerated **synchronously** whenever `create_node` or `update_node` changes the summary or aliases. The keyword half of `search_graph` (which operates on aliases directly) also reflects updates immediately.

---

### Layer 3: Themes

Themes are a derived layer on top of the semantic graph. Like the semantic graph, they are structurally rebuildable, not truth. They are the agent's **map** — a compact orientation document that lets the agent make informed tool-call decisions from the first move of any session, without searching blind.

The design principle: themes exist to solve the cold-start problem. An agent opening a session knows nothing about this person's life. Themes give it a terrain map — what the major territories are, what's currently active, and where to jump into the semantic graph. Like a doctor reading a patient chart summary before entering the room, not the full medical history.

#### Theme Schema

```
name     — canonical label (e.g., "career-direction"). Doubles as identifier.
             No IDs — themes are referenced by name in theme-specific tools,
             but never in semantic graph write operations. Themes are store-level
             entities that exist outside the semantic graph.
state    — 1-2 sentences: what is currently true about this theme.
anchors  — modeled as (:Theme)-[:ANCHORS]->(:SemanticNode) edges in the store.
             Direct entry points that let the agent skip search and jump straight
             to get_node_neighborhood on known territory.
status   — categorical label(s) from: deep | active | emerging | dormant
```

No log, no history, no versioning on themes. Themes are a **living snapshot** of current understanding, not a record. The history of the underlying territory lives in the semantic graph's node logs. This keeps themes cheap to rewrite.

#### Status Labels

Status captures a blend of depth, recency, and maturity as the theme agent's editorial judgment. A single heat score collapses this into one number and destroys information the agent needs. Categorical labels preserve the distinctions:

| Status         | Meaning                           | Agent behavior it implies                                  |
| -------------- | --------------------------------- | ---------------------------------------------------------- |
| `deep, active` | Rich history AND recently touched | Core territory — search carefully before creating anything |
| `deep`         | Rich history, not recently active | Important context but don't expect new content here        |
| `active`       | Recently frequent, still forming  | Evolving fast — update aggressively                        |
| `emerging`     | New, few data points              | Still taking shape — be liberal with new structure         |
| `dormant`      | Historically deep, gone quiet     | Out of context map, accessible on demand                   |

Status labels are not computed mechanically. They are **the theme agent's editorial judgment** each time it touches a theme — consistent with the system's philosophy of LLM judgment over hardcoded rules. The agent reads the theme, reads what just changed, and decides if the status still feels right.

#### Context Rendering

The system maintains the full themes map out of band, but query and ingestion agents do **not** receive the whole map by default. They receive a **hot set** of the most important themes rendered in full, plus a cold index listing the names of every remaining theme. This keeps the always-in-context working set small while preserving discoverability.

The hot set is **token-budget-derived**, not a fixed count. The theme agent produces a **priority-ordered list** of all theme names, ranked by current importance, recency, and expected usefulness as entry points. The renderer walks this list top-down, rendering each theme in full until a configurable token budget (estimated via tiktoken) is exhausted. Remaining themes fall into the cold index. When the budget or themes change, rendering adjusts automatically — no manual `k` to tune.

The priority list is `theme_priority_order` on the System node — an ordered array of all active theme names. The theme agent rewrites the full list at the end of every run via `complete_theme_update`. The harness commits it in one write; no separate sync is needed.

The theme agent is different: because it runs asynchronously and its only job is maintaining the map, it receives the complete themes map.

For query and ingestion sessions, the prompt rendering looks like:

```
HOT THEMES (3 of 47 themes, filling 240 of 250 token budget)

career-direction [deep, active]
Weighing whether to leave job. Tension: security vs creative
fulfillment. Shift toward risk-taking after mentor conversation.
→ node:4, node:17, node:23, node:31

relationship-with-father [deep]
Reconciliation in progress. Positive shift after Feb visit.
Childhood resentment unresolved.
→ node:7, node:12, node:45

meditation-practice [emerging]
Just started for anxiety management. Skeptical but curious.
→ node:52, node:53

Other themes: pottery-class, sleep-routine, apartment-hunt ...
```

For example: At ~50-80 tokens per theme, a 250-token budget fits roughly 3-5 themes — enough for orientation while leaving room for transcript and tool context.

Themes outside the hot set are still available on demand through `get_theme(name)`. This prevents duplicate theme creation without forcing every theme summary into every session.

#### Theme Agent

The theme agent is the simplest of the three agent modes. It operates on the **delta from the preceding session**, not the full semantic graph. This is why it scales.

**Trigger:** After every ingestion, and after every chat session that modifies the semantic graph. The theme agent runs synchronously after the main run completes. If no graph writes occurred, the theme pass is skipped.

**Input:** Exactly three things:

1. Current complete themes map (all Theme nodes) and the current `theme_priority_order` from the System node
2. A delta payload: `{ summary, touched_nodes, touched_edges }`. The summary comes from the agent's termination call (`complete_ingestion` or `deliver_response`). The `touched_nodes` and `touched_edges` lists are always constructed by the harness from tracked write calls — no agent mode reports these manually.
3. Read tools — same semantic graph read tools as any other agent mode

The theme agent **never surveys the full semantic graph.** It works from the delta. The preceding session already did the hard work of reading the transcript (or chatting with the user) and deciding what to create and update. The theme agent's job is just: given what just changed, does the map need updating, and what should the priority order be for future sessions?

**Decision flow:**

1. Check if touched nodes fall within existing themes (by matching against anchor lists). If yes → read those nodes, update the theme's state line.
2. Check if new nodes were created that don't belong to any theme. If yes → read their neighborhoods, decide: new theme, or extend an existing theme's anchors?
3. Check if any status labels feel wrong given the update. Adjust.
4. Decide the new priority order for all themes.

At 10 nodes this is trivial. At 500 nodes it's the same difficulty — the agent only looks at the 5-10 nodes that were just touched. The rest of the semantic graph is irrelevant.

**Tools:**

```
update_theme(name, new_state?, new_anchors?, new_status?)
create_theme(name, state, anchors, status)
retire_theme(name)
```

Targeted updates, not a full rewrite. If only `career-direction` was touched, only `career-direction` changes. Other themes stay exactly as they were. This prevents the drift that comes from LLMs rewriting documents holistically — a small mechanical guardrail where it matters.

**Termination:**

```
complete_theme_update(updated_themes, priority_order)
```

`updated_themes` is a list of theme names that were modified, created, or retired during this run. `priority_order` is the full ordered list of all active theme names, ranked for hot set rendering. The harness catches this call, persists the new priority order, and closes the loop.

---

## The Agent Harness

**Harness = LLM in an agentic loop + a unified pool of tools.**

One harness runs across all three modes: ingestion, query/chat, and theme work. Same tools, different system prompts:

- **Ingestion** — prioritises consistency, accuracy, and semantic graph coherence.
- **Query/Chat** — prioritises synthesis, surfacing surprising connections, grounding answers in cited source text. Can also modify the semantic graph when the user offers corrections or new context.
- **Theme** — takes the voice of a thoughtful observer noticing patterns.

One harness means derived memory is live, not batch-processed. During chat, the user can offer corrections or new context and the agent can update the semantic graph in real time. The canonical layers (transcripts and chat sessions) remain the source of truth, and the derived layers remain rebuildable caches.

The agent has full autonomy over which tools to call and when. No routing is hardcoded. No tool call budgets or timeouts currently.

### Termination

Each agent mode has its own termination signal — a special tool call the harness catches to close the loop.

The harness tracks every write tool call (create, update, delete) made during any session. It automatically constructs `touched_nodes` and `touched_edges` lists with actions (`created`, `updated`, `deleted`). No agent mode needs to report what it modified — the harness already knows.

**Ingestion:**

```
complete_ingestion(summary_of_what_was_done)
```

`summary_of_what_was_done` is a natural language summary for the theme agent's orientation — what the transcript was about, what was notable. The harness appends the automatically tracked `touched_nodes` and `touched_edges` to form the complete delta payload, then triggers a synchronous theme agent run.

**Query/Chat:**

```
deliver_response(answer, cited_sources, consulted_nodes)
```

`answer` is the final response delivered to the user. `cited_sources` is a list of `{ source_id, start_offset, end_offset }` — the evidence the answer is grounded in. `source_id` is `rec:N` or `chat:N`. For transcripts, offsets are seconds into the recording. For chats, `start_offset` is the message index and `end_offset` is null. `consulted_nodes` is a list of node IDs the agent read during retrieval, providing an audit trail of graph traversal.

The harness catches this call and delivers `answer` to the user. If any semantic graph writes occurred during the session, the harness constructs the delta payload from tracked modifications and triggers a synchronous theme agent run.

**Theme:**

```
complete_theme_update(updated_themes, priority_order)
```

`updated_themes` lists which themes were modified, created, or retired. `priority_order` is the full ordered list of active theme names for hot set rendering. The harness persists the new priority order and closes the loop.

---

## Write Architecture

The write flow is prompt-driven, not hardcoded. The agent follows a structured approach without the harness enforcing it mechanically:

1. **Read** — read the full transcript to understand what is being talked about.
2. **Explore** — use read tools to understand the existing semantic graph. Search for relevant nodes, traverse neighborhoods, identify what in the transcript relates to what already exists. This is targeted, not exhaustive — the hot themes block and cold index provide high-level orientation for free.
3. **Plan** — reason about how to integrate the transcript into the semantic graph. Decide what to create, update, or delete. Consider whether something in the transcript refers to an existing node or warrants a new one.
4. **Write** — execute writes in the same loop. Every node write requires a note describing what changed and why. Every node summary rewrite is archived into the log entry, so the agent can see prior summary states if a mid-loop write needs revisiting. This does not extend to alias changes, edge mutations, or deletes — those are not archived.

The harness owns four things regardless of agent autonomy:

- **Token minting** — the agent requests node/edge creation, the harness assigns the next sequential token. The agent never picks its own identifier.
- **Provenance validation** — rules vary by mode (see below). Applies to node writes only; edges carry no provenance.
- **Log entry creation** — the harness auto-creates a log entry from provenance on every node write. The entry contains `source_id`, `timestamp` (datetime), `start_offset`, `end_offset`, and the agent's mandatory `note`. This guarantees every node write produces a traceable, self-documenting provenance record. Edges have no logs — their provenance is implicit in the node logs on either end.

### Provenance Rules

Provenance requirements differ by agent mode:

- **Ingestion writes** must carry `(rec:N, start_offset, end_offset)` where offsets are seconds into the recording. The harness rejects ingestion writes without valid provenance.
- **Chat writes** carry `(chat:N, message_index, null)`. The harness auto-records the message index — the position in the chat's messages array that sourced the modification.
- **Theme agent** writes carry no provenance. Themes are a derived orientation layer, not evidence-grounded artifacts. This is intentional.
- **Deletes** are permanent and non-recoverable in the semantic graph. The node or edge is hard-deleted from the store along with its logs — no provenance, no persistent audit trail. The deletion reason is captured in the `delete_node`/`delete_edge` call, and the `deleted` action appears in the session's completion payload so the theme agent can clean up anchors. The canonical sources (transcripts and chat sessions) that originally produced the deleted entity still exist — the underlying material is never lost, only the graph-side interpretation of it.

### Write Tools

```
create_node(aliases, summary, note, provenance)
update_node(node_id, note, new_summary?, new_aliases?, provenance)
create_edge(from_node_id, to_node_id, label)
update_edge(edge_id, new_label)
delete_node(node_id, reason)
delete_edge(edge_id, reason)
```

`note` is mandatory on both `create_node` and `update_node` — the agent must describe what this write means for the node. `update_node` accepts partial updates for `new_summary` and `new_aliases` — any combination. If `new_summary` is provided, the harness archives the old summary into the log entry alongside the agent's note before applying the new one.

No merge tool. Merge is composed from `create_node` + `update_edge` + `delete_node`. No special casing.

One operation per call. Keeps each write inspectable and the log clean.

---

## Memory Interface Design

The tool interface is the LLM's only view of the memory system. Every design decision here answers one question: what is the most natural representation of a 3-layer personal memory for an LLM to reason over, navigate, and modify through tool calls?

### Design Principles

**The memory has three layers. The interface has three corresponding tiers of interaction.**

| Layer | What it is | How the agent sees it |
|-------|-----------|----------------------|
| Canonical sources (transcripts, chats) | Ground truth — the user's actual words | Source retrieval tools with offset-based slicing |
| Semantic graph (nodes, edges) | Derived cache — LLM-built meaning structure | Graph CRUD tools with progressive disclosure |
| Themes | Derived orientation — editorial map of the territory | Injected into system prompt + on-demand read tools |

The agent doesn't interact with "a database." It interacts with a layered memory that presents itself the way a person's memory works: orientation first (themes → "what do I know about this person?"), then structure (graph → "how does this connect to that?"), then evidence (sources → "what did they actually say?").

**No UUIDs.** All identifiers are short sequential tokens: `node:4`, `edge:12`, `rec:7`, `chat:3`. This is not cosmetic.

- LLMs hallucinate high-entropy identifiers. A UUID like `550e8400-e29b-41d4-a716-446655440000` is noise in a context window — the model has to carry 36 characters of opaque hex through every reasoning step. Sequential tokens are short, memorable, and pattern-recognizable. An LLM that has seen `node:4` and `node:17` in search results can reference them accurately in a write call three turns later. It cannot do this reliably with UUIDs.
- The harness mints all tokens — the agent never picks its own identifier. This eliminates collision, hallucination of non-existent IDs, and the need for existence checks in the agent's reasoning.
- Token format also encodes entity type. `node:N` vs `edge:N` vs `rec:N` is self-documenting in tool arguments, log entries, and provenance chains. The agent can parse entity type from the identifier without a separate field.

**No timestamps.** The agent never sees raw datetimes or ISO strings. Every temporal value is serialized into human-readable relative time before it enters the context window: `"3 weeks ago, Tuesday 24 Jun 2025, 11:42 PM"`.

- Temporal arithmetic is a known failure mode for LLMs. "Was `2024-11-15T14:32:00Z` before or after `2024-11-14T23:58:00Z`?" requires mental parsing that models do unreliably. "Yesterday, 2:32 PM" vs "2 days ago, 11:58 PM" is immediate.
- The harness injects the current time into the system prompt at session start. All relative phrases are computed against this anchor. The agent reasons temporally using natural language — "this was recent," "this was months ago" — which is how humans reason about time and how LLMs reason best.
- This extends to every surface: log entry timestamps, transcript recording times, chat session timestamps. No raw datetime ever reaches the agent.

**No internal mechanics exposed.** The agent sees tool names, descriptions, and typed inputs/outputs. It does not see:

- Database query language or schema details
- Embedding vectors or similarity scores
- JSON serialization of log entries
- The search fusion strategy (keyword + semantic)

The harness handles all of this. `search_graph(query)` returns ranked results — the agent doesn't know or care whether it was keyword match, vector similarity, or both. `get_node(node_id)` returns structured log entries with human-readable timestamps — the agent doesn't know they were JSON-serialized strings in a FalkorDB array property.

### The Three-Layer View

**Layer 1 — Themes (orientation, zero-cost):** The agent starts every session with a terrain map injected into the system prompt. The hot themes block gives the 3-5 most important themes rendered in full — name, state line, status labels, anchor node IDs. The cold index lists every other theme by name. This is the LLM's equivalent of a doctor reading a patient summary before entering the room. No tool call required. The agent knows the major territories and has direct entry points (anchor node IDs) into the semantic graph.

**Layer 2 — Semantic graph (structure, on-demand):** The graph is accessed through a progressive disclosure chain. Each tool reveals just enough to decide whether to go deeper:

1. `search_graph` → one-line summaries, connectivity hints
2. `get_node_neighborhood` → local structure, edge labels, neighbor summaries
3. `get_node` → full detail, complete log history

This is deliberate. Dumping the full graph into context would be wasteful and confusing. The progressive chain mirrors how a person explores: scan, orient, zoom in. Each step gives the agent a reason to continue or stop.

**Layer 3 — Canonical sources (evidence, on-demand):** Transcripts and chats are accessed through offset-based slicing. The agent doesn't retrieve full transcripts at query time — it follows provenance from node log entries (`source_id: rec:7, start_offset: 14, end_offset: 28`) directly to `get_transcript_span(rec:7, 14, 28)` to get the user's exact words. This is citation-grade retrieval: the agent can ground any claim in a specific moment of a specific recording.

### Tool Surface Design

The tool set is flat — no namespaces, no nesting, no hierarchy. Every tool is a top-level function with a natural-language name. This matters because LLM tool calling works best with:

- **Verb-noun names** that describe exactly one action: `search_graph`, `get_node`, `create_edge`, `deliver_response`
- **Minimal required parameters** — most tools take 1-2 arguments. The most complex (`create_node`) takes 4. No tool requires the agent to construct nested objects beyond a provenance triple.
- **Typed, validated inputs** — Pydantic models enforce identifier format (`node:N`, `edge:N`), required fields, and valid enum values. Invalid tool calls fail fast with clear error messages rather than silently producing wrong results.
- **Structured, predictable outputs** — every read tool returns a typed model, serialized to JSON. The agent can reliably extract fields from responses because the shape is consistent across calls.

The tool set is also **mode-gated** — each agent mode receives only the tools it's allowed to use. Ingestion gets graph read + write + `complete_ingestion`. Query gets the same plus `get_theme` and `deliver_response`. Theme mode gets a narrow set: graph reads, theme CRUD, and `complete_theme_update`. The agent never sees tools it can't use, which prevents wasted reasoning about unavailable actions.

### What the Agent Doesn't Do

The harness absorbs all bookkeeping that would otherwise pollute the agent's reasoning:

- **Token minting** — the agent says "create a node with these aliases and summary." The harness assigns `node:47`. The agent never counts, never checks for collisions.
- **Provenance stamping** — the agent provides a note and provenance triple. The harness constructs the full log entry with timestamp and attaches it to the node.
- **Summary archival** — when the agent rewrites a summary, the harness archives the old one into the log entry automatically. The agent doesn't manage versioning.
- **Write tracking** — the harness tracks every mutation (`touched_nodes`, `touched_edges`) across the session. The agent's completion call provides a natural-language summary; the harness appends the structural delta automatically.
- **Embedding updates** — the harness regenerates embeddings synchronously when a node's summary or aliases change. The agent never triggers or waits for embedding generation.

This split is deliberate: the agent's context budget is spent on semantic reasoning about a person's life, not on infrastructure bookkeeping. Every token the agent spends tracking IDs, managing versions, or formatting entries is a token not spent understanding what the user said and what it means.

---

## Read Architecture

**The governing principle: progressive disclosure.** Each tier reveals enough to decide whether to go deeper. The agent never gets more than it asked for.

### Tier 1 — Always in context, no tool call

For query and ingestion modes: the hot themes block (filled by priority order up to the token budget) plus the cold index of all other theme names. The agent starts every session oriented at the high level without paying to keep the full map in context.

### Tier 2 — Orientation

```
search_graph(query, limit)
```

Hybrid search: keyword and semantic fused internally. Keyword handles proper nouns and aliases; semantic handles concepts via gemini-embeddings-001 embeddings. The agent does not control the retrieval mechanics.

Returns per node: `id`, `aliases[0]`, one-line summary, edge count. Nothing else. Edge count hints at connectedness without exposing structure. The agent uses this purely to decide which nodes are worth exploring.

Note: semantic search uses the most recently generated embeddings. Because embeddings update lazily in the background, nodes modified in the current session may not reflect updates in semantic search results. Keyword search over aliases reflects updates immediately.

### Tier 3 — Local exploration

```
get_node_neighborhood(node_id, depth)
```

Returns the target node with: all aliases, full summary, last 2-3 log entries. Plus for each neighbor: edge id, edge label, neighbor id, canonical name, one-line neighbor summary. Enough to understand local graph structure and recent history without full depth.

### Tier 4 — Full node detail

```
get_node(node_id)
```

Returns: all aliases, full summary, `total_log_count`, edge list with ids and labels, and all log entries in chronological order.

### Transcript & Chat Tools

```
list_transcripts(date_range, limit)
get_transcript_span(transcript_id, start_offset, end_offset)
list_chats(date_range, limit)
get_chat(chat_id, start_index?, end_index?)
```

`list_transcripts` enables temporal queries — the agent can browse recordings by date range.

`get_transcript_span` takes time offsets in seconds and returns the corresponding transcript text. During ingestion, the agent reads the inline timestamps in the transcript to identify relevant spans and records those offsets as provenance on every write. At query time, the agent reads `start_offset` and `end_offset` directly from node log entries and passes them through to retrieve exact quotes for citation.

`list_chats` enables temporal queries over chat sessions — the agent can browse past conversations by date range.

`get_chat` returns the conversation log for a chat session. Without index arguments, returns the full log. With `start_index` and/or `end_index`, returns only that slice — mirroring `get_transcript_span` for chat provenance. Used to trace from a node log entry's `(chat:N, message_index, null)` provenance back to the exact exchange.

### Theme Tools

```
get_theme(name)
```

For any theme outside the hot set. Returns the theme's current state and anchors. The agent discovers non-hot theme names from the cold index in the always-in-context block.

---

## Retrieval

**User → Query → Agent → Tools (loop) → `deliver_response`**

The agent decides its own retrieval strategy per query. No routing is hardcoded.

Typical retrieval arc:

1. Hot themes block or cold index orients at high level.
2. `search_graph` lands on relevant nodes.
3. `get_node_neighborhood` gives local semantic graph context.
4. `get_node` for full detail when needed.
5. `get_transcript_span` or `get_chat` grounds the answer in the user's exact words.
6. `deliver_response` delivers the final answer with cited spans and consulted nodes.

The semantic graph and themes guide navigation; they do not serve as the final evidentiary layer. The query agent is required to cite canonical source references (transcripts or chat sessions) in its answers. Grounding responses in cited sources significantly reduces hallucination, and if a cache summary and source evidence disagree, source evidence wins.

> **Future consideration: bi-temporal versioning.** The log approach works for v0. As the system matures, edges may benefit from explicit temporal validity markers (`t_valid`, `t_invalid`) to let the agent query "what was true as of date X" structurally rather than by interpreting logs. See Graphiti (arxiv 2501.13956).

> **Future consideration: composite retrieval.** Consider tools that fuse vector search with graph traversal in a single call — returning semantically similar nodes and their neighborhoods together. Mem0 and Reflect show dual-path retrieval significantly outperforms either alone.
