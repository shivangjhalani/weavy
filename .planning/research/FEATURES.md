# Feature Research

**Domain:** LLM-powered personal memory/knowledge graph backend (audio journaling)
**Researched:** 2026-03-25
**Confidence:** MEDIUM (training knowledge of mem0, Zep, cognee, graphiti, MemGPT patterns — no live sources available)

---

## Feature Landscape

### Table Stakes (System Is Broken Without These)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Transcript ingestion + storage | Source of truth; all retrieval requires it | LOW | Accept audio file, call Groq Whisper, persist raw text + timestamps |
| Semantic graph write (nodes + edges) | Core memory primitive; without it nothing is remembered | HIGH | LLM-defined types; no hardcoded schema; FalkorDB Cypher writes |
| Node disambiguation (dedup/merge) | Without this, "workout" and "my gym routine" become separate nodes — graph explodes | HIGH | Alias sets → fuzzy similarity → LLM reasoning; hardest single piece |
| Graph read/search (Cypher queries) | Query agent needs to traverse graph; useless without it | MEDIUM | Parameterized Cypher; pattern match, neighbor traversal, property filter |
| Vector search across memory layers | Semantic retrieval when exact graph paths don't exist | MEDIUM | Embed node summaries + episode summaries; cosine similarity lookup |
| Episode span tracking | Links graph nodes back to source transcripts; required for groundedness eval | MEDIUM | episode_id, transcript_id, start_offset, end_offset on all graph writes |
| Append-only node/edge logs | Without this you lose change history; no temporal reasoning possible | MEDIUM | Timestamped log entries on every node; token-budgeted compression needed |
| Basic query retrieval (agent answers questions) | The core user-facing capability | HIGH | Agent must decide retrieval strategy, not follow fixed pipeline |

### Differentiators (What Makes LifeOS Special)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| LLM-defined schema (no rigid types) | Most systems force entity types (Person, Place, Event); LifeOS lets the LLM invent types that fit the person's inner life | HIGH | Requires careful prompting so LLM stays consistent across sessions |
| Theme layer with heat/salience scoring | Surfaces recurring patterns automatically; tells you what matters to you right now vs over time | HIGH | Derived memos, not raw graph nodes; always-in-context map for agent |
| Log compression preserving arc of change | Competitors lose history or keep raw logs forever; token-budgeted compression preserves the story of how thinking evolved | HIGH | Summarize while retaining inflection points, not just latest state |
| Transcript-grounded retrieval | Every answer cites specific transcript offsets — verifiable, not hallucinated | MEDIUM | RAGAS groundedness eval keeps this honest |
| Hybrid vector + graph retrieval | Pure vector search loses relational structure; pure graph loses semantic flexibility; hybrid beats both | HIGH | Graph traversal seeded by vector similarity; or vice versa |
| Memo agent (observer voice) | Periodic pattern detection from above the graph — notices things the ingestion agent misses | MEDIUM | Separate role-specific prompt; runs on schedule, not per-transcript |

### Anti-Features (Deliberately Out of Scope)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Hardcoded entity extraction (NER) | Seems like good structure | Locks schema to what the extractor knows; misses idiosyncratic personal concepts | LLM free-form node creation with disambiguation |
| Rigid memory schema (Person/Event/Place) | Standard knowledge graph practice | Forces personal inner life into categories that don't fit introspective content | Schema-free FalkorDB with LLM-generated type strings |
| Fixed retrieval pipeline (retrieve-then-answer) | Simpler to implement | Fails for complex multi-hop queries about personal history | Agentic retrieval — agent decides strategy per query |
| Real-time streaming ingestion | Feels responsive | Adds complexity, not needed for batch audio journaling | Batch per-file ingestion; run after recording |
| REST/GraphQL API | Standard interface pattern | Premature abstraction before memory engine is validated | Runnable Python scripts for experimentation |
| Multi-user support | Obvious product requirement eventually | Complicates every data model decision; wrong scope now | Single-user local scripts |
| Evaluation on every ingestion | Seems like good quality control | RAGAS calls are expensive; kills iteration speed | Run eval as explicit separate step on test sets |

---

## Feature Dependencies

```
Transcript ingestion
    └──requires──> Episode span tracking
                       └──enables──> Transcript-grounded retrieval
                                         └──enables──> RAGAS evaluation

Semantic graph write
    └──requires──> Node disambiguation (dedup)
    └──requires──> Append-only node/edge logs
                       └──enables──> Log compression

Vector search
    └──requires──> Embeddings (node summaries, episode summaries)
    └──enables──> Hybrid vector+graph retrieval

Theme layer
    └──requires──> Semantic graph (needs populated graph to derive from)
    └──requires──> Vector search (theme embeddings)
    └──enables──> Memo agent

Query agent
    └──requires──> Graph read/search
    └──requires──> Vector search
    └──enhanced-by──> Theme layer (as navigation map)
    └──enhanced-by──> Hybrid vector+graph retrieval
```

### Dependency Notes

- **Node disambiguation requires populated graph:** First ingestion is always a write; disambiguation only activates from the second write onward. Test both paths.
- **Theme layer requires graph:** Themes are derived from the graph, not from raw transcripts. Theme layer cannot ship in the same phase as initial graph construction — it needs data to work with.
- **Log compression requires append-only logs:** Cannot compress what isn't being logged. Log structure must be stable before compression is built.
- **RAGAS evaluation requires episode spans:** Groundedness scoring requires transcript references on every retrieved fact. Eval is blocked until span tracking is solid.

---

## MVP Definition

### Launch With (v1 — Validate the memory loop end-to-end)

- [ ] Transcript ingestion pipeline (audio → Groq Whisper → stored text + timestamps)
- [ ] Semantic graph write with LLM-defined node/edge types (no schema)
- [ ] Node disambiguation (alias + fuzzy + LLM fallback)
- [ ] Episode span tracking on all graph writes
- [ ] Append-only node/edge logs
- [ ] Graph read/search tools (Cypher)
- [ ] Vector search on node + episode summaries
- [ ] Basic query agent (reads graph, answers questions)

### Add After Validation (v1.x — Improve retrieval quality)

- [ ] Log compression — add when log tokens become a bottleneck (watch for >4K tokens per node)
- [ ] Theme layer — add once graph is populated enough to have patterns worth surfacing
- [ ] Memo agent — add once theme layer exists
- [ ] Hybrid vector+graph retrieval — add when pure vector or pure graph retrieval shows clear gaps
- [ ] RAGAS evaluation harness — add once query agent is working; run against test transcript set

### Future Consideration (v2+ — After core is validated)

- [ ] Incremental graph repair (retroactively merge nodes found to be duplicates)
- [ ] Temporal query support ("what was I thinking about 3 months ago?")
- [ ] Cross-session theme drift detection (not just heat, but change over time)

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Transcript ingestion | HIGH | LOW | P1 |
| Semantic graph write (schema-free) | HIGH | HIGH | P1 |
| Node disambiguation | HIGH | HIGH | P1 |
| Episode span tracking | HIGH | MEDIUM | P1 |
| Append-only logs | MEDIUM | LOW | P1 |
| Graph read/search | HIGH | MEDIUM | P1 |
| Vector search | HIGH | MEDIUM | P1 |
| Query agent (basic) | HIGH | HIGH | P1 |
| Log compression | MEDIUM | MEDIUM | P2 |
| Theme layer | HIGH | HIGH | P2 |
| Memo agent | MEDIUM | MEDIUM | P2 |
| Hybrid vector+graph | MEDIUM | HIGH | P2 |
| RAGAS evaluation | MEDIUM | MEDIUM | P2 |
| Temporal queries | MEDIUM | HIGH | P3 |
| Graph repair / retroactive merge | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

---

## Competitor Feature Analysis

| Feature | mem0 | Zep | LifeOS Approach |
|---------|------|-----|-----------------|
| Graph schema | Fixed entity types | Structured (episodes, facts) | Schema-free, LLM-defined types |
| Memory layers | Facts + history | Episodes + facts + graph | Transcripts + graph + themes (3 layers) |
| Retrieval | Semantic search primary | Hybrid (BM25 + vector + graph) | Agentic — agent decides strategy per query |
| Source grounding | No transcript anchoring | Partial (episode references) | Full transcript offset references; RAGAS-evaluated |
| Schema evolution | Rigid (requires migration) | Semi-rigid | Emergent — LLM adapts types as user's vocabulary evolves |
| Temporal reasoning | Limited | Episodes have timestamps | Append-only logs capture arc of change, not just current state |

---

## Sources

- PROJECT.md — LifeOS requirements and design philosophy
- Training knowledge of mem0, Zep/Graphiti, cognee, MemGPT memory architectures (MEDIUM confidence — August 2025 cutoff)
- RAGAS evaluation framework patterns (MEDIUM confidence)
- Note: WebSearch unavailable during this research session; findings based on training knowledge only

---
*Feature research for: LLM-powered personal memory backend (audio journaling)*
*Researched: 2026-03-25*
