# Data Model Plan

## Goal

Implement the `Memory-v5` storage model directly in FalkorDB with minimal translation layers. The code should preserve the exact architectural distinction between canonical sources, the semantic graph, themes, and the singleton system state.

## Store Structure

Everything except raw audio files lives in FalkorDB.

Node labels:

```text
(:SemanticNode)
(:Transcript)
(:ChatSession)
(:Theme)
(:System)
```

Edge types:

```text
(:SemanticNode)-[:RELATES]->(:SemanticNode)
(:Theme)-[:ANCHORS]->(:SemanticNode)
```

## Canonical Source Nodes

### Transcript

Properties:
- `id`: `rec:N`
- `audio_path`
- `timestamp`
- `text`

Implementation notes:
- `text` should be stored in normalized inline timestamp format
- `timestamp` should be stored once in canonical form and rendered for the agent on read
- transcript ids are sequential and human-readable

### ChatSession

Properties:
- `id`: `chat:N`
- `timestamp`
- `messages`

Implementation notes:
- `messages` are stored as a JSON-serialized array of `{role, content}`
- the stored chat is canonical and should not be rewritten during normal operation

## Semantic Graph Nodes

### SemanticNode

Properties:
- `id`: `node:N`
- `aliases`: array of strings
- `summary`
- `embedding`
- `total_log_count`
- `log`: array of JSON strings

Rules:
- `aliases[0]` is the canonical label surfaced to the agent
- no `type` property
- `embedding` may start as nullable if semantic search is deferred, but the field should exist in the data model
- `total_log_count` counts only regular entries, not fences

## Semantic Edges

### RELATES

Properties:
- `id`: `edge:N`
- `label`

Rules:
- edge identity is explicit
- no edge logs
- edge history is represented indirectly through node logs

## Theme Nodes

### Theme

Properties:
- `name`
- `state`
- `status`

Rules:
- no theme ids; `name` is the identifier
- anchors are not stored as arrays and must only exist as `ANCHORS` edges
- themes have no logs or version history

## System Node

Properties:
- `next_node_id`
- `next_edge_id`
- `next_rec_id`
- `next_chat_id`
- `theme_priority_order`
- `log_token_budget`
- `hot_theme_token_budget`

Rules:
- exactly one `System` node should exist
- initialization should fail if multiple `System` nodes exist
- the code should not infer missing counters; missing required properties are an error

## Log Model

Logs live only on `SemanticNode` and are stored as JSON-serialized strings in chronological order.

### Regular Entry

```json
{
  "source_id": "rec:7",
  "timestamp": "...",
  "start_offset": 14,
  "end_offset": 28,
  "note": "..."
}
```

Chat-driven regular entries use:
- `source_id = chat:N`
- `start_offset = message_index`
- `end_offset = null`

### Fence Entry

```json
{
  "is_fence": true,
  "timestamp": "...",
  "note": "...",
  "entries_behind": 30,
  "date_range": ["...", "..."]
}
```

Rules:
- logs are append-only
- fences are never rewritten
- hot segment is everything after the last fence
- cold segment is everything at or before the last fence

## Provenance Rules

### Ingestion Mode

Node writes require:
- `source_id = rec:N`
- `start_offset` and `end_offset` in seconds into the transcript

### Query/Chat Mode

Node writes require:
- `source_id = chat:N`
- `start_offset = message_index`
- `end_offset = null`

### Theme Mode

- no provenance on theme writes

### Delete Operations

- deletes have no persisted provenance
- delete calls must require a reason string
- the reason should be captured in traces, not persisted into graph history

## ID Minting Plan

Implement ID minting in the store layer only.

Rules:
- use the `System` node counters as the source of truth
- do not let agents propose ids
- do not use UUIDs
- increment counters atomically within the write operation that creates the entity

## Read Rendering Rules

Tool responses should convert internal storage into agent-facing structures.

Examples:
- deserialize log JSON into structured objects
- render stored timestamps into human-readable strings
- hide storage-specific serialization details from the agent

The implementation should keep this rendering logic in read-tool or model-adapter code, not spread across the codebase.

## Constraints

- No second store for cold data
- No map-valued properties in FalkorDB
- No schema drift from `Memory-v5` without explicit design review
