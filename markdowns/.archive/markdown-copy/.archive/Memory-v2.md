# The Memory

> Question is: How do you represent a human's evolving inner life in a data structure that supports arbitrary, open-ended queries without baking in assumptions and heuristics about what questions will be asked?

## Goal

Design representation to be maximally expressive, and delegate query strategy entirely to the agent at query time.
That leads to

1. LLM-Defined Semantic Graph: I do not design schema and structure, I define the most abstract, universally valid structure - and leave all semantic decisions to the LLM. This ensures that the app becomes more powerful as models become better
2. Agentic retrieval: Tell LLM what is available, and it will figure out how to find the answer.

The structure that I believe is universally valid for journaling:

1. Things (concepts, people, emotions, decisions, questions, themes): nodes
2. Relationships between things: edges with free-form natural language labels
3. The raw transcripts (source of truth, everything can be reconstructed from here)

This I believe is heuristic free.

General-Purpose > Human-Engineered with heuristics and constraints and specialised knowledge. And this is what I want to bake into the design, I want to let the LLM free with minimal necessary designs.

## Core idea

The raw transcript is the only canonical record.

Everything else is derived from it.

## Memory Layers

### Layer 1: Transcripts

The transcript is the source of truth.

The full transcript is stored as-is, and the ingest agent reads the whole thing when updating memory. This matters because the meaning of a thought often depends on the full arc of the recording (chunking into episodes can be lossy).

Each transcript is a record with the following fields:

1. Unique transcript ID
2. Recording timestamp — when the user made this recording. This is the only timestamp that matters; it represents the user's lived time and is passed to the ingest agent in the prompt so the LLM can reason about relative time naturally.
3. Raw text (from Whisper JSON)
4. Episode spans: ranges inside the transcript, where each range covers one coherent theme / topic completely.
    For each episode span:
    - `start_offset`
    - `end_offset`
    - a 1-2 line summary
    - an embedding of that summary (to help in retrieval)

These episode spans are created during ingestion as a side effect of graph writing. They are only a retrieval aid. They are not a source-of-truth memory layer.

The graph carries provenance back to the transcript using:

- `transcript_id`
- `start_offset`
- `end_offset`

At query time, if the agent needs raw text, it pulls the relevant transcript ranges directly.

### Layer 2: Semantic Graph

Made of Things and Relationships.

The full transcript is fed to the ingest agent at once. The agent reads it whole and builds or updates the graph. This is better than chunk-by-chunk writing because the agent can see the full shape of the recording: how a topic starts, changes, and resolves.

This layer is a knowledge graph where an LLM extracts things and relationships from each transcript and updates or adds to the graph. Entity types, relationship types, and all semantic decisions are left entirely to the LLM. A node might be "my relationship with my father", "the startup idea from March", or "fear of disappointing people". Edges are also free-form: "is a source of", "conflicts with", "evolved into", "father of" — or anything the LLM judges most accurate.

A full fledged AI agent should be able to morph the graph however it wants. It should be able to create new things, update/append existing, delete, merge, search, etc. every node and relation.

#### Node and edge structure

Both nodes and edges carry:

- **A current summary** — the LLM's best present-tense description of this thing or relationship, rewritten on each update.
- **A log** — an append-only list of entries, each written by the LLM when it touches this node or edge. Each log entry contains:
  - the recording timestamp of the transcript that caused this update
  - a natural language note describing what changed or was reinforced, including any nuance about certainty, emotional tone, or stance (e.g. "user expressed this as a fear, not a commitment")

  The log is how change is represented over time. There is no invalidation mechanism — instead, the summary reflects the current state, and the log contains the full history of how it got there, including reversals, contradictions, and evolution, all in natural language.

- **Supporting transcript references**, each stored as `(transcript_id, start_offset, end_offset)`

#### Node disambiguation

Node disambiguation is the hardest part. The approach:

1. Semantic search over existing nodes using the new candidates
2. Let the LLM decide whether they are the same thing

Example: "Father" and "Vishal" may be the same node, even if the name appears later.

#### Log compression

Logs grow unboundedly. At ingestion time, after writing a new log entry, check whether the total log for that node or edge exceeds a token budget. If it does, schedule (or lazily perform) a compression pass: the LLM rewrites the older entries into a single condensed entry that preserves the arc of change, while keeping recent entries intact. The raw transcripts are always available for full reconstruction, so no information is permanently lost.

### Layer 3: The Themes

Themes are a derived layer on top of the graph.

They are memos: notes from a thoughtful observer about patterns they are noticing.

These memos live as text with embeddings. They also carry references to the graph nodes and transcript spans they were inferred from, so the chain of evidence always points back to the source.

---

## The Retrieval

User → Query → Agent
Agent knows about the memory layers, decides which one (or more) to access, runs in a loop until it has an answer. No routing is hardcoded — the agent is told what layers exist and what each contains, and decides its own retrieval strategy per query.

---

## The Agent Harness

One modular harness for the agent to control all things. This single agent with its whole arsenal runs during:

1. Ingestion of a transcript
2. Query / chat time
3. Memo work

One advantage of a unified harness: the user can tell the agent about things during chat — corrections, clarifications, context — and the agent can modify the memory layer in real time. Memory is live, not just a batch-processed artifact.

**Harness = LLM in an agentic loop + Tools**

Same harness, different agent roles: ingestion, query, and memo work each get a different system prompt calibrated to that task. The ingestion role prioritises consistency and accuracy. The query role prioritises synthesis and surfacing surprising connections. The memo role takes the voice of a thoughtful observer.

---

## Question: HOW do I give the agent a very natural & native view of the graph so that the agent can reason well over the graph for both writing and querying tasks.

#### Issue 1: Blind start

When the agent has to undertsand the graph at any time for reasons like searching at query time or updating at ingestion time.

When the agent receives a query or a new transcript, in order to understand the graph for reasons, it has to make its first tool call with zero graph context, and will try to find parts of graph where the agent might find the answer using similarity search first and then maybe traversing the graph a bit.

The themes layer solves for this. The themes layer can be always in context, treated as a map, it provides the high level structure of the graph.

Using this information + the semantic search which would also work regardless of the map, agent can make intelligent first tool calls and drill down deeper better.

One more advantage keeping the theme layer in conext would have is the agent would also not start the conversation with the user being blank.

#### Issue 2: How does the agent ask for the graph and how is graph presented to the agent?

A graph is internally stored as let's say adjacency list in some json format. Is dumping the graph node json that it asked for good?
