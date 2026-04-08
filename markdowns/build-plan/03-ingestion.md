# Ingestion Plan

## Goal

Implement transcript-first memory construction as the first end-to-end vertical slice, while modeling chat sessions from day one as canonical sources.

## Scope

This phase covers:
- storing transcripts
- loading full transcript context into ingestion mode
- exploring the graph
- writing semantic changes with provenance
- shared workflow finalization after completion

This phase does not require:
- full conversational query UX
- rebuild tooling
- background workers

## Input Shape

The first ingestion entrypoint should take a transcript id, not raw audio.

Reason:
- keep the first working path narrow
- separate speech-to-text concerns from memory-system behavior
- make evals easier to author and replay

Raw audio retention can still exist in canonical storage, but the ingestion runner should operate on a normalized transcript record.

## Ingestion Workflow

### Step 1: Load Transcript

Read the `Transcript` node by id and render:
- transcript metadata
- full transcript text
- hot theme block
- cold theme index

Rules:
- no transcript chunking in v1
- no selective transcript loading

### Step 2: Run Ingestion Harness

The model should:
- read the full transcript
- inspect relevant graph state through read tools
- decide what to create, update, or delete
- write graph changes with transcript provenance
- end with `complete_ingestion(summary)`

### Step 3: Post-Run Processing

After successful completion, finalize the workflow through the shared finalizer.

The finalizer should:
- mark the transcript ingestion lifecycle as `completed`
- trigger theme maintenance only if graph mutation occurred
- leave the transcript recoverable if the run failed

Manual `weavy update-themes` should remain available as a repair/rebuild path, not as the normal ingestion path.

## Tool Surface for Ingestion

Read tools:
- `search_graph`
- `get_node_neighborhood`
- `get_node`

Write tools:
- `create_node`
- `update_node`
- `delete_node`
- `create_edge`
- `update_edge`
- `delete_edge`

Completion:
- `complete_ingestion`

## Provenance Requirements

Every node write must include:
- `source_id = rec:N`
- `start_offset`
- `end_offset`
- `note`

Validation behavior:
- offsets must be valid transcript offsets
- invalid or missing provenance fails the write
- provenance enforcement should happen in the graph write path itself

## Graph Write Rules During Ingestion

- Prefer updating an existing node when the transcript clearly refers to the same concept
- Create new nodes only when a distinct concept or entity is warranted
- Use deletes rarely and explicitly
- Never perform hidden normalization outside the tool layer

The code should not attempt to second-guess the model's semantic choice beyond strict validation and storage constraints.

## Transcript Span Handling

Implement a narrow helper for transcript span extraction.

Requirements:
- use normalized inline timestamp markers as the source format
- map requested second offsets back to text deterministically
- fail on out-of-range offsets

Do not add:
- approximate offset matching
- fuzzy timestamp repair
- transcript chunk indexes in v1

## Embeddings During Ingestion

Two acceptable paths:

### Option A

Do not enable semantic search in the first ingestion milestone.

### Option B

Generate embeddings synchronously after node summary or alias changes.

Recommendation:
- start with Option A for the first ingest milestone
- add embeddings immediately after the graph write path is stable

## Acceptance Criteria

- a transcript can be ingested into an empty graph
- a transcript can update a non-empty graph
- every node write creates a valid log entry
- touched nodes and edges are captured in the run trace
- theme maintenance runs after successful graph mutation
- transcript lifecycle is explicit: `pending -> running -> completed` or `failed`
