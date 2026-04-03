# The Memory

> How do you represent a human's evolving inner life in a data structure that supports arbitrary, open-ended queries without baking in assumptions about what questions will be asked?

## Goal

Design representation to be maximally expressive, and delegate strategy entirely to the agent.
The bitter lesson coded.

That leads to:
1. **LLM-Defined Semantic Graph** — no engineered schema. The most abstract, universally valid structure is defined, and all semantic decisions are left to the LLM. The system becomes more powerful as models improve.
2. **Agentic retrieval** — tell the LLM what is available, and it figures out how to find the answer.

The structure that is universally valid for journaling:

1. Things (concepts, people, emotions, decisions, questions, themes): nodes
2. Relationships between things: edges with free-form natural language labels
3. The raw transcripts: source of truth. Everything can be reconstructed from here.

**No rigid extraction schema.** The LLM is not asked to extract `(subject, relation, object)` triples or conform to any fixed graph pattern. It is free to create whatever nodes and relationships it judges best — an event node connecting multiple entities, a feeling logged inside a relationship edge, a standalone concept. Structure emerges from the LLM's judgment guided by prompt-level directions, not from hardcoded constraints.

---

## Core idea

The raw transcript is the only canonical record. Everything else is derived from it.

---

## Memory Layers

### Layer 1: Transcripts

The transcript is the source of truth.

The full transcript is stored as-is. The ingest agent reads the whole thing when updating memory — the meaning of a thought often depends on the full arc of the recording, and chunking is lossy.

Each transcript record:

1. **Transcript ID** — a readable sequential token (e.g. `rec:7`). This is the primary key everywhere, including in the database. No UUIDs (LLMs can hallucinate UUIDs when wanting to access.
2. **Recording timestamp** — stored internally as datetime, always surfaced to the agent as human-readable relative time: `"3 weeks ago, Tuesday, 24 Jun 2023, 11:42 PM"`. For same-day recordings, relative ordering is preserved ("earlier today", "last night"). The harness injects the current time at the start of every session so the agent reasons about time naturally, never arithmetically.
3. **Raw text** (from Whisper JSON)
4. **Touched nodes** — list of node IDs affected during ingestion of this transcript.
5. **Touched edges** — list of edge IDs affected during ingestion of this transcript.

The bidirectional index (nodes → transcript, transcript → nodes/edges) serves two purposes. It enables temporal graph traversal: given a date range, the agent can jump directly from a set of transcripts into the graph nodes they affected, without an extra search pass. It also makes every ingestion run fully auditable.

Graph nodes and edges carry provenance back to the transcript using `(transcript_id, start_offset, end_offset)`.

---

### Layer 2: Semantic Graph

Made of Things and Relationships.

The full transcript is fed to the ingest agent at once. The agent reads it whole and builds or updates the graph. This lets the agent see how a topic starts, changes, and resolves — something chunk-by-chunk processing destroys.

Entity types, relationship types, and all semantic decisions are left entirely to the LLM. A node might be "my relationship with my father", "the startup idea from March", or "fear of disappointing people". Edges are also free-form: "is a source of", "conflicts with", "evolved into" — or anything the LLM judges most accurate. The agent can create new nodes, update or append to existing, delete, search, or restructure anything in the graph.

The ingestion prompt guides the agent to exercise judgment — not every sentence deserves a node. Extract what is meaningfully distinct, emotionally significant, or decision-relevant, and skip the rest. This is prompting for judgment, not a schema constraint.

#### Identifiers

All identifiers across every layer are sequential readable tokens per entity type:

```
node:12    edge:4    rec:2
```

These tokens ARE the primary keys — in the database, in the graph, in provenance references, in the agent interface. No UUIDs anywhere. The global token registry is a first-class persistent artifact of the system, maintained permanently. As the agent discovers nodes through tool calls, active tokens are surfaced into the session context. New nodes minted during ingestion are assigned permanent tokens immediately at creation time.

This is not just ergonomic. LLMs hallucinate high-entropy identifiers like UUIDs — they reproduce them with typos, truncations, and fabrications. Short, typed tokens give the agent a clean vocabulary it can reliably reuse.

#### Node and edge structure

Both nodes and edges carry:

- **A current summary** — the LLM's best present-tense description of this thing or relationship, rewritten on each update. Serves as both a quick-orientation surface for the agent and an embedding target for semantic search. Before any rewrite, the previous summary is appended to the log automatically, so no state is ever silently lost.
- **A log** — an append-only list of entries written by the LLM each time it touches this node or edge. Each entry contains:
  - The recording timestamp of the transcript that caused this update
  - A natural language note describing what changed or was reinforced, including nuance about certainty, emotional tone, or stance (e.g. "user expressed this as a fear, not a commitment")

  The log is how change is represented over time. The summary reflects current state. The log contains the full history of how it got there — reversals, contradictions, evolution — all in natural language. Logs are returned on demand, not by default.

- **Supporting transcript references** — each stored as `(transcript_id, start_offset, end_offset)`. At query time, the agent can pull exact transcript text to ground answers in the user's own words, reducing hallucination.

> **Future consideration: bi-temporal versioning.** The log-based approach works for v0. As the system matures, edges may benefit from explicit temporal validity markers (`t_valid`, `t_invalid`) alongside the log. This would let the agent query "what was true as of date X" structurally rather than by interpreting logs. See Graphiti (arxiv 2501.13956) for reference.

#### Node disambiguation

The agent should have the ability to use it's search tools however it likes to go through things like aliases of nodes and semantic searches over some content of the nodes to find potential matches, and then apply its reasoning to determine if they are the same thing and then should it update the existing node / edges or create a new one or delete the existing one to merge old info and new info into a new one.

Shared transcript references (via the bidirectional index) are strong evidence of same-entity — the agent can inspect which transcripts touched each node as part of its disambiguation reasoning.

#### Log compression

Logs grow unboundedly. After writing a new log entry, check whether the total log exceeds a token budget. If it does, the LLM compresses older entries into a single condensed entry that preserves the arc of change, keeping recent entries intact. A pointer is added to the summary directing the agent to full archived logs for deep dives. Archived logs of a node can be puled through a tool call.

---

### Layer 3: Themes

Themes are a derived layer on top of the graph.

They are memos: notes from a thoughtful observer about patterns emerging across the graph. They live as natural language text with embeddings, and carry references to the graph nodes and transcript spans they were inferred from. The chain of evidence always points back to the source.

Themes serve a critical architectural role: they are always in context as a map. The agent starts every ingestion or query session already knowing the high-level terrain of the graph, without any tool call. This solves the cold-start problem — the agent never begins blind.

#### Theme salience and heat

Each theme carries a **heat** value representing current salience.

- Themes gain heat when: a new recording touches them, the user queries something related, or the memo agent reinforces them.
- Heat decays over time naturally.
- Only the top-k themes (above a salience threshold) are included in the always-in-context map. Cooler themes remain accessible on demand via `get_theme_detail` but do not occupy the working context.

---

## The Agent Harness

**Harness = LLM in an agentic loop + a unified pool of tools**

One harness runs during all three modes: ingestion, query/chat, and memo work. Same tools, different system prompts calibrated to each role:

- **Ingestion** — prioritises consistency, accuracy, and graph coherence.
- **Query** — prioritises synthesis, surfacing surprising connections, grounding in cited transcript text.
- **Memo** — takes the voice of a thoughtful observer noticing patterns.

One harness means memory is live, not batch-processed. During chat, the user can offer corrections, clarifications, or new context, and the agent can update the memory layers in real time.

The agent has full autonomy over which tools to call and when, guided by tool descriptions and system prompt. No routing is hardcoded.

### Termination: completion signals

The agent is not given rigid loop control. Instead, deliberate completion signals are designed into the tool interface. When the agent finishes ingestion, it calls:

```
complete_ingestion(summary_of_what_was_done, touched_nodes, touched_edges)
```

This call IS the termination condition — the harness catches it and closes the loop. The `touched_nodes` and `touched_edges` payload also populates the bidirectional index on the transcript record for free, with no extra work. The completion call doubles as a session audit log.

This is not a constraint on autonomy. It is good engineering: the agent declares done, the harness records it.

---

## The Tool Interface

**Read tools are coarse. Write tools are atomic.**

Reads are how the agent orients — you want it to pull neighborhoods, summaries, and context in as few calls as possible. Writes are where things go permanently wrong — updates, node creation. Those are deliberate, one operation at a time.

**Tool responses are briefings, not database dumps.**

Responses are formatted for reasoning, not completeness. Structured natural language, not raw JSON. The agent gets enough to decide what to do next — logs are available on demand, not injected by default.

### Read Tools

The agent moves top-down through three tiers:

**Tier 1 — always in context, no tool call:**

The themes map. The agent starts every session oriented at the high level.

**Tier 2 — first tool call, orientation:**

```
search_graph(query, filter_by_type?, limit)
```

Hybrid search: keyword and semantic fused internally. The agent does not control the alpha — a sensible default is set by the harness. One tool, no retrieval-mechanics decisions imposed on the agent. Returns a structured briefing of the top-k most relevant nodes with summaries and immediate connections.

Direct string search (for proper nouns, names, specific identifiers) is handled by the same tool internally — embeddings alone do not reliably handle exact names.

**Tier 3 — deliberate traversal:**

```
get_node_neighborhood(node_id, depth)
```

Called when the agent knows where it is going. Returns the node (all details), its edges, and one-line summaries of neighbors.

**Transcript tools:**

```
list_transcripts(date_range, limit)
get_transcript_span(transcript_id, start_offset, end_offset)
```

`list_transcripts` enables temporal queries ("how has my thinking changed since January?"). Combined with the bidirectional index on each transcript, the agent can move directly from a temporal starting point into affected graph nodes.

**Themes tools:**

```
get_theme_detail(theme_id)
```

For themes below the heat threshold that are not in the always-in-context map.

### Tool Categories

```
Graph Read
Graph Write
Transcript Access
Themes Access
Completion
```

Write tools are designed to be atomic and deliberate.

---

## Retrieval

**User → Query → Agent → Tools (loop) → Answer**

The agent knows what layers exist and what each contains. It decides its own retrieval strategy per query. No routing is hardcoded.

The typical retrieval arc:
1. Themes map orients the agent at high level.
2. `search_graph` lands on the most relevant nodes.
3. `get_node_neighborhood` gives local graph context.
4. `get_transcript_span` grounds the answer in the user's exact words.

> **Note on citations.** Requiring the agent to ground responses in cited transcript references reduces hallucination significantly (NotebookLM research: ~40% → ~13%). The query agent should be required to cite transcript references in its answers.

> **Future consideration: hybrid retrieval tools.** Beyond per-layer search, consider composite tools that fuse vector search with graph traversal in a single call — returning semantically similar nodes and their graph neighborhoods together. Mem0 and Reflect show dual-path retrieval significantly outperforms either alone.
