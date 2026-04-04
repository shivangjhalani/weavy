# Harness and Tooling Plan

## Goal

Build one reusable agent harness that runs ingestion, query, and theme modes with different prompts and allowed tools, but identical execution semantics.

## Core Harness Responsibilities

- render mode-specific context
- expose a validated tool registry
- execute tool calls in a loop
- track touched nodes and edges
- capture a run trace
- terminate only on the mode's completion tool

The harness should not:
- repair malformed tool calls silently
- retry failed tool calls automatically
- decide retrieval strategy itself
- hide model or tool failures

## Harness Inputs

Each run should accept:
- `mode`
- `system_prompt`
- `initial_messages`
- `allowed_tools`
- `completion_tool`
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

### Step 4: Execute Tool

- run the tool
- append structured result to the conversation
- update touched entity tracking if the tool is a write tool
- record the tool call and tool result in the trace

### Step 5: Detect Completion

The run ends only when the model calls the mode's completion tool.

Completion tools:
- ingestion: `complete_ingestion`
- query: `deliver_response`
- theme: `complete_theme_update`

If the model stops without calling completion, fail the run.

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

The harness must track graph mutations centrally.

Track:
- node id
- action: `created | updated | deleted`
- edge id
- action: `created | updated | deleted`

Rules:
- tracking is derived from executed write tools, not from model self-reporting
- the completion payload should not be trusted for this data

## Post-Run Hooks

Use explicit synchronous post-run steps.

### After Ingestion or Query with Graph Writes

Run in order:
1. fence check for touched nodes
2. theme pass

Optional:
3. synchronous embedding update if embeddings are implemented in the same phase

Rules:
- no hidden queue or worker
- if a post-run step fails, surface the failure

## Tool Registry Plan

Keep the registry explicit and static.

Each tool should define:
- name
- request model
- response model
- executor function
- mutation metadata

The registry should not:
- do name aliasing
- support partial argument coercion
- allow unregistered tools

## Trace Storage

Store traces as local artifacts under a deterministic path such as `private/evals/runs/` or a similar debug folder.

Each trace should include:
- prompt inputs
- tool interactions
- completion payload
- failure details

Keep traces readable in raw JSON without requiring a UI.
