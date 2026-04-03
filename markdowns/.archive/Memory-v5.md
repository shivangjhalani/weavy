# The Memory

> How do you represent a human's evolving inner life in a data structure that supports arbitrary, open-ended queries without baking in assumptions about what questions will be asked?

## Goal

Design representation to be maximally expressive, and delegate query strategy entirely to the agent at query time. That leads to:

1. **LLM-Defined Semantic Graph** — no engineered schema. The most abstract, universally valid structure is defined, and all semantic decisions are left to the LLM. The system becomes more powerful as models improve.
2. **Agentic retrieval** — tell the LLM what is available, and it figures out how to find the answer.

The graph and themes are not truth. They are derived, rebuildable caches built on top of the canonical transcript layer to make retrieval and orientation cheaper at runtime.

The structure that is universally valid for journaling:

1. Things (concepts, people, emotions, decisions, questions, themes): nodes
2. Relationships between things: edges with free-form natural language labels
3. The raw transcripts: source of truth. Everything can be reconstructed from here.

**No rigid extraction schema.** The LLM is free to create whatever nodes and relationships it judges best. Structure emerges from the LLM's judgment guided by prompt-level directions, not from hardcoded constraints.

---

## Core Idea

The raw transcript is the only canonical record. Everything else is derived from it.

The semantic graph and themes are rebuildable working memory layers: useful, lossy, and disposable. They exist to help the agent navigate, not to replace the source material. If the system drops them and regenerates them from transcripts, no truth is lost.

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

---

## Memory Layers

### Layer 1: Transcripts

The full transcript is stored as-is. The ingest agent reads the whole thing — meaning often depends on the full arc of a recording, and chunking is lossy.

Each transcript record:

- **id** — readable sequential token, e.g. `rec:7`. Primary key everywhere. No UUIDs — LLMs hallucinate high-entropy identifiers.
- **audio_path** — path to the retained raw audio file. The audio is a permanent artifact, never discarded.
- **timestamp** — stored as datetime internally, always surfaced to the agent as human-readable relative time: `"3 weeks ago, Tuesday 24 Jun 2023, 11:42 PM"`. Harness injects current time at session start so the agent reasons naturally, never arithmetically.
- **text** — transcript from Whisper, presented to the agent with inline timestamps at sentence boundaries:
  ```
  [0:00] So I've been thinking about this career decision a lot lately.
  [0:14] I know I should probably just quit but the mortgage keeps stopping me.
  [0:28] And honestly I think I'm scared of what happens if I actually do it.
  ```
  Timestamps are **seconds into the recording**. Groq Whisper returns both word-level and segment-level timestamps, but the system standardizes on segment boundaries and renders them as readable inline markers. These inline markers are what the agent reads during ingestion to identify provenance spans.
- **touched_nodes** — list of `{ node_id, action }` entries recording what happened during ingestion. Action is one of `created`, `updated`, `deleted`.
- **touched_edges** — list of `{ edge_id, action }` entries. Same action vocabulary.

The bidirectional index (transcript → nodes/edges with actions, and log entries on each node/edge → transcript) serves two purposes: temporal graph traversal — given a date range, jump directly from transcripts into affected graph nodes without an extra search pass — and a full audit trail of every ingestion run, including deletions.

#### Chat Sessions

Chat sessions are tracked alongside transcripts as first-class entities with their own sequential tokens:

```
chat:7
```

A `chat:N` token is minted by the harness when a query/chat session starts. It serves as the provenance source for any graph modifications made during chat — corrections, new context, or updates the user offers conversationally. Chat sessions do not have audio or transcript text; they exist purely as provenance anchors and audit records.

Each chat session record:

- **id** — e.g. `chat:7`
- **timestamp** — when the session started
- **touched_nodes** — list of `{ node_id, action }` entries for graph modifications made during chat
- **touched_edges** — list of `{ edge_id, action }` entries

---

### Layer 2: Semantic Graph

The semantic graph is a derived semantic cache over transcripts, not a canonical store. It is made of nodes and edges. The agent reads the full transcript and builds or updates the graph in one pass, preserving the arc of how a topic starts, changes, and resolves.

All semantic decisions — what deserves a node, how to label a relationship, whether to update or create — are left entirely to the LLM. The ingestion prompt guides the agent to exercise judgment: extract what is meaningfully distinct, emotionally significant, or decision-relevant. Skip the rest.

The graph exists to support retrieval, orientation, and synthesis. It can be rebuilt as prompts, models, or indexing strategy improve.

#### Identifiers

All identifiers are sequential readable tokens per entity type:

```
node:12    edge:4    rec:2    chat:7
```

These tokens are the primary keys — in the database, in the graph, in provenance references, in the agent interface. The global token registry is a permanent first-class artifact of the system. The harness mints new tokens at creation time; the agent never picks its own. As the agent discovers nodes through tool calls, active tokens surface into the session context.

No concurrent writes — all ingestion and processing is sequential. The token registry is a simple counter per entity type.

#### Node Schema

```
id        — e.g. node:12
aliases   — [string]. aliases[0] is the canonical name.
summary   — current best description, rewritten on each update.
             Serves as agent orientation and embedding target for semantic search.
log       — append-only list of entries:
               { transcript_id, timestamp_human_readable, start_offset, end_offset, note }
             transcript_id is rec:N for ingestion writes or chat:N for chat writes.
             start_offset and end_offset are seconds into the recording (null for chat writes).
             note is natural language: what changed, what was reinforced, emotional nuance,
             certainty, stance. The previous summary is automatically archived into the log
             before any rewrite — no state is ever silently lost.
cold_summary — null until logs exceed budget. When present, a natural language arc summary
               covering all over-budget log entries, with the time range they span.
               Generated by a background job. Stored on the node itself.
```

Aliases capture how people refer to the same thing across time — "my dad", "my father", "papa". `aliases[0]` is the canonical handle. The alias list is used by keyword search inside `search_graph` and enriches the embedding target alongside the summary.

There is no type field. A free-form type tag degrades over time — the agent produces "emotion", "feeling", "emotional state" for semantically identical things, making filtering unreliable. The summary carries all semantic meaning and is a better retrieval target.

#### Edge Schema

```
id     — e.g. edge:4
from   — node_id
to     — node_id
label  — free-form natural language. This is the type and name of the relationship.
log    — same structure as node log.
cold_summary — same as node cold_summary.
```

Edges do not have aliases — the label is the relationship's name and there is no parallel ambiguity problem.

#### Log Management

Logs are append-only and grow unboundedly. All log entries stay on the node or edge permanently in FalkorDB — there is no separate cold storage table or archive. The intelligence is entirely in the **read path**.

A configurable token budget (estimated via tiktoken) determines the boundary between "in-budget" and "over-budget" log entries. After each ingestion or chat session that modifies the graph, a background job checks whether any affected node or edge's log exceeds the budget. If it does:

1. The over-budget (older) entries are left in place on the node.
2. A `cold_summary` is generated: a natural language arc summary covering all over-budget entries, noting the time range they span and the key trajectory of change.
3. The `cold_summary` is stored directly on the node, replacing any previous cold summary.

The read tools enforce the budget:

- **`get_node`** returns all in-budget (recent) log entries in full, plus the stored `cold_summary` if one exists. The cold summary is rendered with a self-documenting hint:

  > `"[Cold logs: Mar 2024 → Nov 2024] Career anxiety shifted from external validation to internal clarity. Retrieve full entries via get_cold_logs(node:12)."`

  The agent discovers that deeper history exists only by reading this summary. There is no separate schema field or pointer beyond what's naturally in the data.

- **`get_cold_logs(node_id)`** returns all over-budget log entries in full. The agent only knows to call this if it encounters the cold summary hint while reading a node.

This design keeps the common read path fast and token-efficient while preserving full history on the node for when the agent needs it.

#### Embeddings

Node embeddings (generated from summary + aliases via gemini-embeddings-001) power the semantic half of `search_graph`. Embeddings are updated **lazily as a background job**: whenever `update_node` changes the summary or aliases, the node is flagged for re-embedding. A background job picks up flagged nodes and regenerates their embeddings.

Updated embeddings are **not available** to subsequent `search_graph` calls in the same session. This is an accepted trade-off — the next session will have fresh embeddings. The keyword half of `search_graph` (which operates on aliases directly) reflects updates immediately.

---

### Layer 3: Themes

Themes are a derived layer on top of the graph. Like the graph, they are a rebuildable cache, not truth. They are the agent's **map** — a compact orientation document that lets the agent make informed tool-call decisions from the first move of any session, without searching blind.

The design principle: themes exist to solve the cold-start problem. An agent opening a session knows nothing about this person's life. Themes give it a terrain map — what the major territories are, what's currently active, and where to jump into the graph. Like a doctor reading a patient chart summary before entering the room, not the full medical history.

#### Theme Schema

```
name     — canonical label (e.g., "career-direction"). Doubles as identifier.
             No IDs — the agent never references themes in tool calls, only nodes.
             Themes are orientation, not operational.
state    — 1-2 sentences: what is currently true about this theme.
anchors  — [node_id, ...]: direct entry points into the graph for this theme.
             These let the agent skip search and jump straight to
             get_node_neighborhood on known territory.
status   — categorical label(s) from: deep | active | emerging | dormant
```

No log, no history, no versioning on themes. Themes are a **living snapshot** of current understanding, not a record. The history of the underlying territory lives in the graph's node logs. This keeps themes cheap to rewrite.

#### Status Labels

Status captures two independent dimensions — **depth** (how rich and interconnected the theme is) and **recency** (how active it is right now). A single heat score collapses these into one number and destroys information the agent needs. Categorical labels preserve both:

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

The priority list is a small artifact stored alongside the themes map. The theme agent rewrites it at the end of every run.

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

Other themes: pottery-class, sleep-routine, apartment-hunt
```

At ~50-80 tokens per theme, a 250-token budget fits roughly 3-5 themes — enough for orientation while leaving room for transcript and tool context.

Themes outside the hot set are still available on demand through `get_theme(name)`. This prevents duplicate theme creation without forcing every theme summary into every session.

#### Theme Agent

The theme agent is the simplest of the three agent modes. It operates on the **delta from the preceding session**, not the full graph. This is why it scales.

**Trigger:** After every ingestion, and after every chat session that modifies the graph. The theme agent runs asynchronously — the user doesn't wait for it. The next session picks up the updated themes. If multiple triggers fire in quick succession, theme agent runs are serialized (queued, not parallel) so each run sees the previous run's updates.

**Input:** Exactly three things:

1. Current complete themes map (including priority order)
2. Session completion payload — from `complete_ingestion` or `deliver_response`, containing summary and touched_nodes/edges with actions (~200 tokens)
3. Read tools — same graph read tools as any other agent mode

The theme agent **never surveys the full graph.** It works from the delta. The preceding session already did the hard work of reading the transcript (or chatting with the user) and deciding what to create and update. The theme agent's job is just: given what just changed, does the map need updating, and what should the priority order be for future sessions?

**Decision flow:**

1. Check if touched nodes fall within existing themes (by matching against anchor lists). If yes → read those nodes, update the theme's state line.
2. Check if new nodes were created that don't belong to any theme. If yes → read their neighborhoods, decide: new theme, or extend an existing theme's anchors?
3. Check if any status labels feel wrong given the update. Adjust.
4. Decide the new priority order for all themes.

At 10 nodes this is trivial. At 500 nodes it's the same difficulty — the agent only looks at the 5-10 nodes that were just touched. The rest of the graph is irrelevant.

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

- **Ingestion** — prioritises consistency, accuracy, and graph coherence.
- **Query/Chat** — prioritises synthesis, surfacing surprising connections, grounding answers in cited transcript text. Can also modify the graph when the user offers corrections or new context.
- **Theme** — takes the voice of a thoughtful observer noticing patterns.

One harness means derived memory is live, not batch-processed. During chat, the user can offer corrections or new context and the agent can update the graph in real time. The transcript layer remains canonical, and the derived layers remain rebuildable caches.

The agent has full autonomy over which tools to call and when. No routing is hardcoded. No tool call budgets or timeouts currently.

### Termination

Each agent mode has its own termination signal — a special tool call the harness catches to close the loop. Each doubles as a session audit log.

**Ingestion:**

```
complete_ingestion(summary_of_what_was_done, touched_nodes, touched_edges)
```

`touched_nodes` is a list of `{ node_id, action }` where action is `created`, `updated`, or `deleted`. Same for `touched_edges`. The payload simultaneously populates the bidirectional index on the transcript record. If the graph was modified, this payload triggers an asynchronous theme agent run.

**Query/Chat:**

```
deliver_response(answer, cited_spans, consulted_nodes)
```

`answer` is the final response delivered to the user. `cited_spans` is a list of `{ transcript_id, start_offset, end_offset }` — the evidence the answer is grounded in. `consulted_nodes` is a list of node IDs the agent read during retrieval, providing an audit trail of graph traversal.

The harness catches this call, delivers `answer` to the user, and closes the loop. If the chat session modified the graph (touched_nodes/edges are tracked by the harness throughout the session), the harness also triggers an asynchronous theme agent run with the accumulated delta.

**Theme:**

```
complete_theme_update(updated_themes, priority_order)
```

`updated_themes` lists which themes were modified, created, or retired. `priority_order` is the full ordered list of active theme names for hot set rendering. The harness persists the new priority order and closes the loop.

---

## Write Architecture

The write flow is prompt-driven, not hardcoded. The agent follows a structured approach without the harness enforcing it mechanically:

1. **Read** — read the full transcript to understand what is being talked about.
2. **Explore** — use read tools to understand the existing graph. Search for relevant nodes, traverse neighborhoods, identify what in the transcript relates to what already exists. This is targeted, not exhaustive — the hot themes block and cold index provide high-level orientation for free.
3. **Plan** — reason about how to integrate the transcript into the graph. Decide what to create, update, or delete. Consider whether something in the transcript refers to an existing node or warrants a new one.
4. **Write** — execute writes in the same loop. The log-based architecture makes mid-loop writes recoverable — every summary rewrite is preserved in the log, so intermediate states are never destructive. The agent can improvise if its plan proves wrong mid-execution.

The harness owns three things regardless of agent autonomy:

- **Token minting** — the agent requests node/edge creation, the harness assigns the next sequential token. The agent never picks its own identifier.
- **Provenance validation** — rules vary by mode (see below).
- **Log management scheduling** — cold summary generation triggered as a background job after sessions that modify the graph.

### Provenance Rules

Provenance requirements differ by agent mode:

- **Ingestion writes** must carry `(rec:N, start_offset, end_offset)` where offsets are seconds into the recording. The harness rejects ingestion writes without valid provenance.
- **Chat writes** carry `(chat:N, null, null)`. The harness accepts null offsets for chat-sourced modifications — there is no audio to reference.
- **Theme agent** writes carry no provenance. Themes are a derived orientation layer, not evidence-grounded artifacts. This is intentional.
- **Deletes** carry no provenance — the node or edge is being removed, and there is nowhere to store provenance on a deleted entity. The deletion reason is captured in the `delete_node`/`delete_edge` call and in the session's completion payload via the `deleted` action on touched_nodes/edges.

### Write Tools

```
create_node(aliases, summary, provenance)
update_node(node_id, new_summary?, new_aliases?, log_entry?, provenance)
create_edge(from_node_id, to_node_id, label, provenance)
update_edge(edge_id, new_label?, log_entry, provenance)
delete_node(node_id, reason)
delete_edge(edge_id, reason)
```

`update_node` accepts partial updates — any combination of `new_summary`, `new_aliases`, and `log_entry`. The harness automatically archives the old summary into the log before applying a new one.

No merge tool. Merge is composed from `create_node` + `update_edge` + `delete_node`. No special casing.

One operation per call. Keeps each write inspectable and the log clean.

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

Returns the target node with: all aliases, full summary, last 2-3 log entries. Plus for each neighbor: edge label, neighbor id, canonical name, one-line neighbor summary. Enough to understand local graph structure and recent history without full depth.

### Tier 4 — Full node detail

```
get_node(node_id)
```

Returns: all aliases, full summary, all in-budget log entries in full, edge list with labels only. If a `cold_summary` exists on the node, it is appended after the in-budget entries:

> `"[Cold logs: Mar 2024 → Nov 2024] Career anxiety shifted from external validation to internal clarity. Retrieve full entries via get_cold_logs(node:12)."`

The agent discovers the cold log archive exists only by reading this summary. There is no separate schema field or pointer. If the agent never needs deep history, it never knows to ask.

### Cold logs

```
get_cold_logs(node_id)
```

Returns all over-budget log entries in full. Not discoverable through the schema — discoverable through the data. The agent only knows to call this if it naturally encounters the cold summary hint while reading a node via `get_node`.

### Transcript Tools

```
list_transcripts(date_range, limit)
get_transcript_span(transcript_id, start_offset, end_offset)
```

`list_transcripts` enables temporal queries. Combined with the bidirectional index, the agent can move from a date range directly into affected graph nodes.

`get_transcript_span` takes time offsets in seconds and returns the corresponding transcript text. During ingestion, the agent reads the inline timestamps in the transcript to identify relevant spans and records those offsets as provenance on every write. At query time, the agent reads `start_offset` and `end_offset` directly from node log entries and passes them through to retrieve exact quotes for citation.

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
3. `get_node_neighborhood` gives local graph context.
4. `get_node` for full detail when needed.
5. `get_transcript_span` grounds the answer in the user's exact words.
6. `deliver_response` delivers the final answer with cited spans and consulted nodes.

The graph and themes guide navigation; they do not serve as the final evidentiary layer. The query agent is required to cite transcript references in its answers. Grounding responses in cited spans significantly reduces hallucination, and if a cache summary and transcript evidence disagree, transcript evidence wins.

> **Future consideration: bi-temporal versioning.** The log approach works for v0. As the system matures, edges may benefit from explicit temporal validity markers (`t_valid`, `t_invalid`) to let the agent query "what was true as of date X" structurally rather than by interpreting logs. See Graphiti (arxiv 2501.13956).

> **Future consideration: composite retrieval.** Consider tools that fuse vector search with graph traversal in a single call — returning semantically similar nodes and their neighborhoods together. Mem0 and Reflect show dual-path retrieval significantly outperforms either alone.
