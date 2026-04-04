# Query and Chat Plan

## Goal

Add user-facing retrieval and grounded answers after the ingestion and theme layers are stable, while preserving the same minimal, explicit execution model.

## Query Principles

- answers must be grounded in canonical transcript or chat sources
- the semantic graph and themes are navigation aids, not final evidence
- query runs may mutate the graph when the user adds or corrects context
- all query behavior runs through the same harness used by ingestion and theme modes

## Read Tool Sequence

Implement read tools in this order:

1. `search_graph`
2. `get_node_neighborhood`
3. `get_node`
4. `get_cold_logs`
5. `list_transcripts`
6. `get_transcript_span`
7. `list_chats`
8. `get_chat`
9. `get_theme`

Reason:
- this matches the progressive disclosure model in `Memory-v5`
- it allows the first query flow to work before deeper optimizations exist

## Query Mode Input

Provide:
- user question
- current time
- hot theme block
- cold theme index
- relevant chat session id if the current interaction is stored canonically at session start

## Deliver Response Contract

The run must terminate via:

```text
deliver_response(answer, cited_sources, consulted_nodes)
```

Requirements:
- `answer` is the user-facing response
- `cited_sources` reference only canonical transcript or chat sources
- `consulted_nodes` are graph nodes actually read during the run

Validation:
- cited source ids must exist
- transcript citations require valid start/end offsets
- chat citations require valid message index and null end offset

## Chat Session Handling

Chat sessions are canonical from day one.

Implementation plan:
- create a `ChatSession` record at the start of a query/chat run
- append user and assistant messages to the canonical session log
- when the model writes to the graph due to user-provided context, provenance must reference the current `chat:N`

Keep this behavior explicit. Do not treat conversational writes as an unlogged side effect.

## Chat-Driven Graph Mutation

Allow the same graph CRUD tools as ingestion.

Rules:
- graph writes during query/chat must use chat provenance
- if no graph writes occur, no theme pass should run
- post-run processing after graph writes is synchronous and identical to ingestion

## Search Implementation

### First Working Version

Implement:
- alias keyword search

Optional in the same phase:
- semantic search over embeddings

If semantic search is not implemented yet:
- do not pretend to return semantic matches
- keep `search_graph` explicitly keyword-only until embeddings exist

### Result Shape

Each hit returns:
- `id`
- canonical alias
- one-line summary
- edge count

Do not overload this tool with full-node detail.

## Node Read Tools

### get_node_neighborhood

Returns:
- full target node summary and aliases
- recent log entries
- neighbor list with edge ids and labels

### get_node

Returns:
- full aliases
- full summary
- total log count
- edge list
- last fence if any
- hot logs
- cold-history hint if applicable

### get_cold_logs

Returns:
- all cold regular entries and fences in chronological order

## Acceptance Criteria

- a query can navigate from themes or search into graph state
- final answers cite transcript or chat spans
- chat-driven corrections can update graph state
- post-run theme maintenance happens only when graph mutation occurs
