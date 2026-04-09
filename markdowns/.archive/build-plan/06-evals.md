# Eval Plan

## Goal

Build a strong agent-eval system for this research MVP. The eval stack should measure the quality of the full memory workflow, not generic retrieval metrics.

## Eval Principles

- run the real harness, not mocks of the decision loop
- capture full traces for every eval case
- combine deterministic checks with LLM-as-judge scoring
- optimize for understanding regressions in agent behavior
- avoid RAG-specific metrics that do not match the system design

## Eval Scope

The eval system should cover:
- ingestion behavior
- theme-update behavior
- query-answer behavior
- chat-correction behavior
- deletion and graph-maintenance behavior

It should not focus on:
- generic top-k retrieval metrics
- synthetic benchmark-style RAG scoring

## Scenario Format

Each scenario should declare:
- scenario id
- mode under test
- canonical source fixtures
- optional initial graph state
- user question if applicable
- expected high-level behaviors
- deterministic assertions
- judge rubric

Suggested fixture categories:
- transcript-only ingestion
- repeated concept across transcripts
- emotional state evolution
- multi-source query using transcript and chat evidence
- user correction that changes graph interpretation
- node deletion and theme cleanup

## Deterministic Checks

Implement explicit checks for:
- valid sequential ids
- valid provenance on node writes
- required completion tool usage
- required citations for query answers
- touched entity tracking integrity
- shared workflow-finalizer behavior
- explicit transcript run-state transitions
- theme priority order integrity
- anchor validity

These checks should fail the eval immediately and clearly.

## LLM Judge Scoring

Use LLM-as-judge for semantic quality questions that deterministic checks cannot answer.

Judge dimensions:
- duplicate-node avoidance
- graph coherence
- node-summary quality
- theme usefulness
- answer grounding
- faithfulness to user evidence
- appropriateness of graph writes during chat

Implementation notes:
- keep judge prompts versioned
- store judge outputs alongside traces
- use the same scenario inputs across model/prompt variants

## RAGAS Usage

`ragas` is optional support infrastructure, not the design center.

Allowed uses:
- report organization
- judge orchestration helpers
- experiment scaffolding if it fits the agent-eval workflow

Avoid:
- shaping the memory system to fit RAGAS' retrieval-oriented assumptions

## Eval Runner

The eval runner should:
1. initialize or load fixture state
2. execute the real harness flow
3. capture traces and outputs
4. run deterministic checks
5. run judge scoring
6. persist a comparable result artifact

Suggested outputs:
- status
- deterministic pass/fail summary
- judge scores
- trace path
- graph diff summary

## Regression Reporting

Compare runs by:
- prompt version
- model version
- tool-surface version
- scenario id

Reports should make it easy to answer:
- what got worse
- what got better
- whether the regression was structural or semantic

## Acceptance Criteria

- scenarios can be run repeatedly against the real harness
- failures are diagnosable from saved traces
- both memory quality and answer quality are visible in results
- prompt/model changes can be compared without manual reconstruction
