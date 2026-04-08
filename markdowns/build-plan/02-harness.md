# Harness and Tooling Plan

## Goal

Build one reusable agent harness that runs ingestion, query, and theme modes with different prompts and allowed actions, but identical execution semantics.

## Core Harness Responsibilities

- render mode-specific context
- expose a static validated action surface
- execute tool calls in a loop
- capture a run trace
- terminate only on the mode's completion tool
- delegate workflow side effects to a shared finalizer

The harness should not:
- repair malformed tool calls silently
- retry failed tool calls automatically
- decide retrieval strategy itself
- hide model or tool failures
- own graph invariants that belong in the memory service

## Harness Inputs

Each run should accept:
- `mode`
- `system_prompt`
- `initial_messages`
- `allowed_actions`
- `run_context`

Suggested `run_context` fields:
- current time
- hot theme block
- cold theme index
- transcript id or chat id if relevant
- model configuration

## Run Loop

### Step 1: Initialize Trace

Create a run trace object before the first model call.

Trace fields:
- `run_id`
- `mode`
- `started_at`
- `input_summary`
- `tool_calls`
- `tool_results`
- `completion_payload`
- `touched_nodes`
- `touched_edges`
- `status`
- `error`

### Step 2: Call Model

Send the prompt and current conversation state to the LLM through LiteLLM.

Rules:
- do not mutate prompts during the run except by appending messages and tool results
- no retry wrapper in v1
- if the model returns invalid tool arguments, fail the run

### Step 3: Validate Tool Call

When the model invokes a tool:
- resolve the registered tool
- parse its arguments through the tool's Pydantic request model
- reject the call if parsing fails

### Step 4: Execute Action

- run the action
- append structured result to the conversation
- record the tool call and tool result in the trace

Rules:
- touched entity tracking should come from the write path, not from the harness inferring mutation semantics itself
- provenance validation should live in the memory service, not in passive wrappers

### Step 5: Detect Completion

The run ends only when the model calls the mode's completion tool.

Completion tools:
- ingestion: `complete_ingestion`
- query: `deliver_response`
- theme: `complete_theme_update`

If the model stops without calling completion, fail the run.

### Step 6: Finalize Workflow

After completion or failure, hand off to a shared workflow finalizer.

The finalizer should own:
- persistence derived from the run
- post-run theme maintenance
- transcript lifecycle cleanup
- failure cleanup

This step must be shared across ingestion, query, and theme modes unless a workflow intentionally opts out.

## Mode Contracts

### Ingestion Mode

Purpose:
- read one canonical source
- inspect current graph state
- write graph changes
- summarize the delta for the theme pass

Allowed write tools:
- graph read tools
- graph write tools
- ingestion completion tool

### Query Mode

Purpose:
- answer a user question
- cite canonical sources
- optionally write graph updates when the user adds or corrects context

Allowed write tools:
- graph read tools
- graph write tools
- canonical source read tools
- theme read tool
- query completion tool

### Theme Mode

Purpose:
- update themes from a known delta
- rewrite the priority order

Allowed write tools:
- graph read tools
- theme tools
- theme completion tool

## Touched Entity Tracking

The system must track graph mutations centrally.

Track:
- node id
- action: `created | updated | deleted`
- edge id
- action: `created | updated | deleted`

Rules:
- tracking is derived from executed write actions, not from model self-reporting
- the completion payload should not be trusted for this data
- the write path should append touched entities directly as part of mutation execution

## Post-Run Hooks

Use explicit synchronous post-run steps through the shared finalizer.

### After Ingestion or Query with Graph Writes

Run in order:
1. theme pass

Optional:
2. synchronous embedding update if embeddings are implemented in the same phase

Rules:
- no hidden queue or worker
- if a post-run step fails, surface the failure clearly
- theme maintenance must not be scattered across mode implementations

## Action Surface Plan

Keep the action surface explicit and static.

Each action should define:
- name
- request model
- response model
- executor function
- mutation metadata

The action surface should not:
- do name aliasing
- support partial argument coercion
- allow unregistered tools

Thin pass-through wrappers should be avoided. If a layer does not add validation, invariants, or translation, collapse it.

## Trace Storage

Store traces in-memory for the runtime path and optionally mirror them to Langfuse or local artifacts for debugging/evals.

Each trace should include:
- prompt inputs
- tool interactions
- completion payload
- failure details

Keep traces readable in raw JSON without requiring a UI.
