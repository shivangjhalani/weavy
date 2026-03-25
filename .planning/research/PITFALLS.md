# Pitfalls Research

**Domain:** LLM-powered audio journaling memory system (backend)
**Researched:** 2026-03-25
**Confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: Entity Proliferation (Duplicate Nodes)

**What goes wrong:**
LLM creates near-duplicate nodes without a disambiguation gate. "Father", "Dad", "Papa", "Vishal" become 4 separate nodes instead of 1.

**Why it happens:**
Without pre-creation similarity checks, every new surface form becomes a new node. The graph degrades rapidly.

**How to avoid:**
Vector similarity check against existing node aliases/summaries before any `CREATE NODE` call. Three-tier disambiguation: exact alias match → fuzzy similarity → LLM reasoning.

**Warning signs:**
Graph has many nodes with similar summaries. Same person/concept appears multiple times in query results.

**Phase to address:** Phase 2 (Ingestion) — disambiguation must ship with graph writes from day one.

---

### Pitfall 2: Schema Type Drift

**What goes wrong:**
Free-form schema means the LLM uses inconsistent type strings across sessions: `Person`/`person`/`human`/`individual` for the same concept type.

**Why it happens:**
No vocabulary guidance in the ingestion prompt. LLM picks whatever feels right in context.

**How to avoid:**
Inject a vocabulary registry (list of existing node/edge types) into every ingestion prompt. LLM should prefer existing types and only create new ones when genuinely needed.

**Warning signs:**
`MATCH (n) RETURN DISTINCT labels(n)` shows many near-synonym types.

**Phase to address:** Phase 2 (Ingestion) — include type registry in ingestion prompt design.

---

### Pitfall 3: Log Overflow

**What goes wrong:**
Append-only logs on nodes/edges hit context window limits at ~50 entries per node. Agent can't read the full log, loses historical arc.

**Why it happens:**
Compression is treated as an optimization to add later, not a core feature.

**How to avoid:**
Token-budgeted compression baked in from day 1. After writing a new log entry, check token count. If over budget, compress older entries while preserving inflection points.

**Warning signs:**
Nodes that the user frequently discusses have logs exceeding the token budget. Agent responses about long-running themes become shallow.

**Phase to address:** Phase 2 (Ingestion) — compression logic alongside log writing.

---

### Pitfall 4: Agentic Loop Without Termination

**What goes wrong:**
Query agent over-retrieves (infinite tool call loops) or under-retrieves (gives up too early with thin answers).

**Why it happens:**
No hard limits on tool calls. Agent decides "I need more context" indefinitely, or conversely answers from first search without checking quality.

**How to avoid:**
Hard tool-call budget enforced in harness code, not just prompts. E.g., max 8 tool calls per query. Harness forces answer after budget exhausted.

**Warning signs:**
Query latency varies wildly (1s to 30s+). Some queries trigger dozens of tool calls.

**Phase to address:** Phase 1 (Agent Harness) — build budget enforcement into the loop from the start.

---

### Pitfall 5: RAGAS False Confidence

**What goes wrong:**
RAGAS scores look great (high faithfulness, relevance) but the system fails on temporal/evolution queries — the most important query type for LifeOS.

**Why it happens:**
Standard RAGAS measures grounding but doesn't test "how has X changed over time?" or "what was I feeling about X in January vs now?" — the queries that define LifeOS's value.

**How to avoid:**
Hand-craft 10-15 evolution/temporal queries as primary eval signal alongside RAGAS. E.g., "How has my view of [topic] changed?" with expected arc.

**Warning signs:**
High RAGAS scores but subjectively poor answers to "how have I changed?" type questions.

**Phase to address:** Phase 5 (Evaluation) — design temporal eval suite alongside RAGAS.

---

### Pitfall 6: FalkorDB Silent Full Scans

**What goes wrong:**
Queries that look fast on small graphs become catastrophically slow as the graph grows. `WHERE n.name = 'X'` does a full scan without explicit indexes.

**Why it happens:**
FalkorDB has no auto-indexing. Developers assume indexes exist because queries work.

**How to avoid:**
Create indexes at initialization: `CREATE INDEX` on all properties used in WHERE clauses (name, aliases, type, transcript_id). Include index creation in setup scripts.

**Warning signs:**
Query latency increases linearly with graph size even for simple lookups.

**Phase to address:** Phase 1 (Core + Storage) — index creation in FalkorDB setup.

---

### Pitfall 7: Stale Embeddings

**What goes wrong:**
Updating a node's summary without re-embedding it breaks vector search. The embedding represents the old summary; semantic search returns wrong results.

**Why it happens:**
Summary update and embedding update are separate operations. Developer updates one and forgets the other.

**How to avoid:**
Single `update_node` function that always re-embeds atomically. Never expose separate "update summary" and "update embedding" operations.

**Warning signs:**
Vector search returns nodes whose summaries don't match the query despite high similarity scores.

**Phase to address:** Phase 1 (Core + Storage) — atomic update functions from the start.

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Entity proliferation | Phase 2 (Ingestion) | Query for duplicate-looking nodes after test ingestion |
| Schema type drift | Phase 2 (Ingestion) | `RETURN DISTINCT labels(n)` should show clean types |
| Log overflow | Phase 2 (Ingestion) | Verify compression triggers on high-activity nodes |
| Agentic loop termination | Phase 1 (Harness) | Verify max tool calls enforced in test queries |
| RAGAS false confidence | Phase 5 (Evaluation) | Temporal query suite passes alongside RAGAS |
| FalkorDB full scans | Phase 1 (Storage) | EXPLAIN on common queries shows index usage |
| Stale embeddings | Phase 1 (Storage) | Update node, verify vector search finds it |

---
*Pitfalls research for: LLM-powered audio journaling memory system*
*Researched: 2026-03-25*
