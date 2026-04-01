# Pitfalls Research

**Domain:** AI-powered voice journaling with LLM-driven semantic knowledge graph
**Researched:** 2026-04-01
**Confidence:** HIGH (architecture-derived) / MEDIUM (LLM/graph ecosystem patterns from training data, unverifiable against live docs)

---

## Critical Pitfalls

### Pitfall 1: Node Proliferation — The Graph Becomes Noise

**What goes wrong:**
The ingestion agent creates a new node for every slightly-different mention of the same concept across recordings. After 50 recordings, "career anxiety", "work stress", "job pressure", "career worries", and "professional uncertainty" exist as five separate nodes with near-identical summaries and no edges connecting them. The graph becomes too dense to navigate and semantic search starts returning all five weakly-matched nodes instead of the one authoritative one.

**Why it happens:**
The LLM has no graph-scope awareness at ingestion time — it sees the current transcript and whatever nodes it retrieves via search. If the search doesn't surface an existing related node (due to lexical mismatch, low embedding similarity, or simply not searching broadly enough), the agent creates rather than merges. The problem compounds: proliferated nodes have shorter logs and thinner summaries, making them even harder to find later, which causes more proliferation.

**How to avoid:**
1. Require the ingestion prompt to explicitly mandate a search-before-create discipline: the agent must call `search_graph` and inspect results before creating any node. The prompt must frame creation as the last resort, not the default.
2. The `search_graph` tool must surface aliases and partial matches, not just semantic similarity. "Career anxiety" and "career anxieties" being different embeddings is not a reason to miss the existing node.
3. Include the current node count in the ingestion system prompt context. An agent that sees "current graph: 847 nodes" will exercise more discipline than one seeing a blank canvas.
4. Build a post-ingestion health metric: ratio of `create_node` calls to `update_node` calls per session. If it trends above ~0.5 after 20+ sessions, something is wrong.

**Warning signs:**
- Node count growing faster than transcript count (>3-4 nodes per recording is a red flag past early sessions)
- Multiple nodes with near-identical canonical names (`aliases[0]`) surfacing in the same `search_graph` result
- The same real-world concept (e.g., "fear of failure") appearing under 3+ different node IDs
- Hot themes losing their anchor node coherence (anchors pointing to 2-3 nodes that should be 1)

**Phase to address:**
Ingestion agent phase — ingestion prompt design and the `search_graph` tool's alias-aware search must both be implemented before any real data is loaded. Cannot be retrofitted cleanly.

---

### Pitfall 2: Silent Summary Drift — Nodes Lose Meaning Over Time

**What goes wrong:**
The node summary is rewritten on every update. After 40 rewrites over 6 months, the summary for "career-direction" has been rewritten by 40 different agent calls, each pulling slightly differently from the current transcript context. The summary starts accurate, becomes generic, then becomes a bland average of all mentions, losing the specific emotional texture that made it useful. Semantic search degrades because the embedding target has drifted toward a centroid that doesn't represent any real statement. Users stop getting accurate answers to questions like "how has my thinking about my career changed?" — the summary already homogenized the change away.

**Why it happens:**
Each summary rewrite is a fresh LLM generation conditioned primarily on the current transcript and the old summary. The LLM tends to smooth and synthesize rather than preserve tension and contradiction. The log preserves the history, but the summary — the primary embedding target for search — absorbs the latest without holding the arc.

**How to avoid:**
1. The ingestion prompt must instruct the agent that summary rewrites should preserve the *current distinct state* with its specific tensions and contradictions, not converge toward an averaged description.
2. Consider banning summary rewrites for minor log additions — the agent should only rewrite the summary when something substantively changed. The prompt can enforce "only rewrite summary if the core state has changed, not just because new evidence was added."
3. Add the previous summary as visible context when asking the agent to rewrite — not just in the archived log, but explicitly surfaced in the `update_node` tool response so the agent can see what it is replacing.
4. The v5 architecture already archives old summaries into the log before rewrite (INGEST-08), which is correct. But the log archive must be surface-tested: periodically check that `get_node_log_archive` for a core node actually reads like a coherent arc, not a series of bland rewrites.

**Warning signs:**
- Core node summaries becoming increasingly abstract and general over time
- Query answers becoming less specific and less grounded in exact user language
- The same node's `get_node` summary and `get_node_log_archive` entries feeling tonally disconnected
- Users reporting that answers feel like "summaries of summaries" rather than things they actually said

**Phase to address:**
Ingestion agent phase (prompt design) and Query evaluation phase (qualitative graph audit after 10+ sessions).

---

### Pitfall 3: Incomplete Graph Updates — The Provenance Gap

**What goes wrong:**
The ingestion agent creates nodes and edges, but some writes are executed without `(transcript_id, start_offset, end_offset)`. This happens when: (a) the agent infers a connection that isn't explicitly stated in the transcript and attaches it to approximate offsets, (b) the agent writes a structural edge ("relates to") with no clear transcript anchor, or (c) the agent runs out of context budget and starts writing without going back to verify offsets. Six months later, queries can't be grounded in cited spans for 30% of nodes because the provenance is missing or wrong. The "your own words" guarantee breaks.

**Why it happens:**
Provenance offsets require the agent to match what it's writing back to a specific timestamp marker in the transcript. If the agent has already moved past that part of the transcript in its reasoning, it may pick the closest plausible offset or invent one. The spec says the harness must reject writes without provenance (WRITE-02), but a wrong offset that happens to be in-range passes validation and silently corrupts the citation chain.

**How to avoid:**
1. The harness must validate provenance strictly: `start_offset` and `end_offset` must be non-null, `end_offset > start_offset`, and both within the transcript's duration. Reject anything outside these bounds.
2. The harness should additionally verify that `get_transcript_span(transcript_id, start_offset, end_offset)` returns non-empty text. A write whose offsets point to silence is a signal of a fabricated provenance.
3. The ingestion prompt should enforce quoting the relevant span before writing: "Before creating or updating a node, state the exact sentence(s) from the transcript that justify this write. Identify the timestamp marker just before that sentence."
4. Tool call audit: after ingestion, log the distribution of provenance offsets across writes. Clustering (many writes pointing to the same offset range) indicates the agent is reusing one anchor rather than tracking each write to its source.

**Warning signs:**
- Multiple writes pointing to identical `(start_offset, end_offset)` pairs
- Provenance offsets always round numbers (0, 30, 60, 120) rather than Whisper's actual sentence boundaries
- `get_transcript_span` returning short fragments (under 10 words) for many provenance calls
- Query citations that quote text that doesn't feel related to the node they're attached to

**Phase to address:**
Ingestion agent phase — provenance validation must be enforced in the harness from day one, before any real ingestion runs. Retroactive provenance repair is high-cost.

---

### Pitfall 4: Agentic Loop Runaway — Infinite Tool Calls on Ambiguous Transcripts

**What goes wrong:**
The ingestion agent enters a loop where: it searches for a node, finds near-matches but can't decide if they're the same thing, searches again with a different query, reads neighborhoods, reads full nodes, searches again, and never commits to a write. The loop burns through the token budget without completing ingestion. The transcript is left partially ingested (some writes occurred before the loop stalled), the bidirectional index is incomplete, and `complete_ingestion` is never called. The theme agent never fires. The next session starts without the new transcript being reflected in the graph.

**Why it happens:**
Node disambiguation is genuinely hard, and a well-instructed agent will be thorough. But "be thorough" without a hard decision protocol becomes infinite research. The LLM defaults to gathering more evidence when uncertain, and there is always more evidence to gather.

**How to avoid:**
1. Set a hard tool call budget in the harness: ingestion aborts and calls `complete_ingestion` with a `partial=true` flag if tool calls exceed N (e.g., 60). The partial flag triggers a re-run in the next session.
2. The ingestion prompt must include an explicit disambiguation decision rule: "If after two `search_graph` calls and one `get_node_neighborhood` you cannot confidently determine if this is an existing node, create a new node. Prefer over-creation to stalling. Merges can happen later."
3. Build a timeout watchdog at the harness level (not just token budget): wall-clock timeout of 2-3 minutes per ingestion session triggers graceful termination.
4. Implement idempotent write behavior: if the harness detects a loop (same tool+arguments called 3 times within a session), inject a "commit what you have and terminate" message.

**Warning signs:**
- Ingestion sessions taking >3x longer than the transcript duration
- Tool call logs showing repeated `search_graph` with the same or near-identical queries
- `complete_ingestion` never being called in a session (check via the bidirectional index — a transcript with no `touched_nodes` after its timeout window)
- Token usage per ingestion session growing without bound across recordings

**Phase to address:**
Ingestion harness phase — tool call budget and timeout must be first-class harness concerns, not afterthoughts. The loop control must be tested against ambiguous transcripts before release.

---

### Pitfall 5: Log Compression Destroying the Arc

**What goes wrong:**
The log compression job runs on a node with 30 entries. The LLM compresses entries 1-25 into a single arc summary. The compression happens to be run during a period when the most recent entries reflect a temporary regression (e.g., "returned to old anxiety pattern after vacation"). The arc summary emphasizes the regression because it was the freshest context in the compression window. Future reads of this node present a distorted emotional arc that doesn't match the actual trajectory. The archived raw entries exist but the inline compression entry — the first thing any agent reads — misrepresents the node's history.

**Why it happens:**
LLM summarization is context-window biased: recent entries carry more weight even when told to "preserve the arc." A compression that spans 18 months but is generated in a single pass will subtly over-represent whatever was emotionally salient when the compression was triggered.

**How to avoid:**
1. The compression prompt must explicitly instruct: "Write the arc chronologically, not as a current-state description. State what the trajectory was, including reversals. Do not editorialize the final state."
2. The compression must retain the first entry verbatim (or nearly so) as the arc's anchor point — the origin of a node is high-signal.
3. After compression, the harness should run a sanity check: `get_node` on the compressed node and verify the inline compression entry mentions both the start date and end date of the compressed range and includes at least one reversal/contradiction if the raw log contained one.
4. Cold storage of pre-compression entries is non-negotiable (GRAPH-03 specifies this correctly). Verify cold storage is actually being written before the inline entry is replaced.

**Warning signs:**
- Compression entries reading like current-state descriptions ("X is resolved") rather than arcs ("X started as Y, shifted through Z, and appears resolved as of date W")
- Dates in compression entries being missing or approximate
- Cold storage query (`get_node_log_archive`) returning empty or fewer entries than expected after compression runs
- Query agent citing the compression entry's synthesized language directly as if it were the user's words

**Phase to address:**
Log compression background job phase — the compression prompt must be treated as critically as the ingestion prompt. Compression is a lossy operation and its quality degrades silently.

---

### Pitfall 6: Theme Hot Set Becoming Stale — Cold Themes Being Functionally Dead

**What goes wrong:**
The hot set of k themes is determined by the theme agent's editorial judgment after each ingestion. After 6 months of consistent journaling about career, relationships, and creativity, the hot set solidifies around those three. A new significant topic emerges (health anxiety, say) and gets captured as a theme. But because it starts as `emerging` with a short state and few anchors, the theme agent keeps it out of the hot set for several sessions. Meanwhile the ingestion agent, starting fresh each session with only the hot themes rendered, repeatedly creates new nodes related to "health anxiety" without connecting them to the existing `health-anxiety` theme because that theme isn't in context. The cold theme's anchors never get updated. After 3 weeks the cold theme is stale and the graph has a cluster of orphaned health-related nodes with no thematic orientation.

**Why it happens:**
The hot-set selection is editorial, which is correct, but the cold-index is only names. An ingestion agent that doesn't call `get_theme(name)` for cold themes will miss their anchors entirely. The agent has no incentive to scan cold themes during ingestion — the workflow directs it to read the transcript and update the graph, not to audit cold themes.

**How to avoid:**
1. The ingestion prompt should include explicit instruction: "Before finalizing new node creation, check whether the node's subject appears in the cold theme index. If yes, call `get_theme(name)` to retrieve its anchors before deciding whether to create or update."
2. The theme agent's hot-set selection should include a freshness rule: if a theme has not had its anchors referenced in 3+ sessions, it must either enter the hot set briefly (to be re-anchored) or get flagged for retirement review.
3. Build a cold theme staleness metric: any theme whose anchors haven't been touched in N sessions (where N > hot-set selection period) should be surfaced to the theme agent on its next run for explicit re-evaluation, not silently left stale.

**Warning signs:**
- Cold themes having anchor nodes that haven't been updated in a long time while transcripts mention the same topic
- New sessions consistently creating nodes whose canonical names match cold theme names
- Graph clusters (via `get_node_neighborhood`) with no path to any themed node
- A theme's `anchors` list pointing to nodes with logs that are very old relative to recent sessions on that topic

**Phase to address:**
Theme agent phase — the theme agent's hot-set selection logic and the ingestion prompt's cold-theme-check behavior must be co-designed. They are coupled.

---

### Pitfall 7: FalkorDB Array Fields Behaving as Single Values

**What goes wrong:**
FalkorDB is a Redis module. Node properties that are arrays (e.g., `aliases`, the log list) are stored as Redis values. The Python client may silently serialize/deserialize these differently depending on the property type used. A developer storing `aliases` as a list property finds that Cypher queries using `IN aliases` work in small tests but break on production data where the stored value has been double-serialized as a JSON string inside a list, or vice versa. Similarly, log entries stored as a list of maps may be returned as strings, requiring manual deserialization on every read.

**Why it happens:**
FalkorDB supports a subset of property types: string, integer, float, boolean, array, and point. Complex nested structures (a log entry is a dict with 5 fields) must either be stored as JSON strings inside the array or as separate nodes. The decision made at schema design time locks in the serialization contract for the entire project. If the implementation starts storing log entries as JSON strings and later switches to structured properties, all existing data is incompatible.

**How to avoid:**
1. Make an explicit, documented decision at project start: log entries are either stored as JSON strings within an array property (simple but requires explicit parsing) or as separate `LogEntry` nodes connected by edges (verbose but queryable via Cypher). Pick one and document it in the schema spec.
2. Write a data access layer (DAL) that abstracts all FalkorDB reads/writes. Every read goes through the DAL, which handles deserialization. No raw Cypher responses in business logic.
3. Validate round-trip serialization for all array fields in the first integration test: create a node with a 3-entry log, read it back, assert the deserialized structure is exactly equal to the input.
4. FalkorDB vector index creation requires explicit schema declaration (`CREATE VECTOR INDEX`). If the index is not created before the first write, embedding-based search silently falls back to brute-force scan and gives no error. Index creation must be part of the database initialization script, not runtime code.

**Warning signs:**
- `search_graph` returning nodes with truncated or mangled summaries
- Aliases list returning a single concatenated string instead of a list
- Log entries returning as escaped JSON strings requiring manual parsing
- Vector search returning zero results despite nodes existing with embeddings

**Phase to address:**
Graph storage phase (FalkorDB schema design) — before any agent code is written. Schema decisions propagate everywhere.

---

### Pitfall 8: Whisper Hallucination on Silence and Noise

**What goes wrong:**
Whisper generates text for recordings that contain long silences, background noise, or filler audio (coughing, "um", music in background). The hallucinated text ranges from generic phrases ("Thank you for watching") to confabulated content that sounds like the user said something they didn't. These hallucinations enter the ingestion pipeline, get processed by the agent as real statements, and end up in the graph as nodes with provenance pointing to spans of silence. The user queries their graph months later and gets answers citing things they never said.

**Why it happens:**
Whisper was trained to generate transcripts for content-dense audio. On sparse audio, it fills with training data patterns rather than outputting silence or a low-confidence signal. Whisper's default behavior does not flag confidence per segment — it just outputs text.

**How to avoid:**
1. Use `whisper-timestamped` or the official Whisper Python library's word-level probability output. Filter segments where average log-probability falls below a threshold (typically -1.0 is a standard filter point for low-confidence hallucinations).
2. Post-process transcripts to flag and optionally strip segments marked as silence (Whisper marks these as `[MUSIC]`, `[APPLAUSE]`, or similar meta-tokens in some models). Never feed these to the ingestion agent.
3. Set a minimum recording duration (e.g., 5 seconds) and minimum non-silence duration before ingestion is triggered. Very short recordings with long silence ratios are more likely to hallucinate.
4. Store the raw Whisper output JSON (with confidence scores) alongside the rendered transcript so hallucination filtering can be improved retroactively.

**Warning signs:**
- Transcripts containing phrases like "Thank you", "See you next time", "Subscribe" that don't fit voice journal context
- Transcript spans with provenance offsets pointing to the beginning or end of a recording (silence padding zones)
- Node summaries citing specific factual claims that the user reports not having made
- Very short log entries (2-3 words) with provenance

**Phase to address:**
Transcription pipeline phase — Whisper integration must include confidence filtering before any ingestion pipeline is built.

---

### Pitfall 9: Hybrid Search Returning Semantic Neighbors Instead of Exact Matches

**What goes wrong:**
`search_graph` uses hybrid keyword + semantic search. When a user asks "what did I say about Dad last month?", the semantic search component returns nodes broadly related to "family", "relationships", "father figures" alongside the actual "Dad/Father" node. The agent starts exploring the wrong neighborhood first. When users ask about specific named people (a colleague, a friend), proper nouns may not have strong semantic embeddings and get buried under topically-adjacent but person-different results. The agent traverses neighbors of the wrong node, spends tool budget, and either times out or gives an answer grounded in the wrong person's context.

**Why it happens:**
Semantic embeddings are terrible at proper nouns, abbreviations, and personal identifiers. "Dad" and "David" may be far apart in embedding space while "father", "mentor", and "guidance" are close together — but the user means a specific person, not the concept of fatherhood. Keyword search handles exact names well but misses plurals and morphological variants. Without proper weighting, semantic wins by default and drowns proper-noun precision.

**How to avoid:**
1. The alias system in the node schema (all surface forms that have resolved to a node) is the correct solution. Keyword matching must run against the full alias list, not just `aliases[0]`. The `search_graph` implementation must explicitly check all aliases.
2. Exact-match results (alias hits) should be boosted to the top of the result set before semantic scores are considered. A node that exactly matches a search term should always appear first.
3. The `search_graph` tool response should indicate whether each result was a keyword match or a semantic match — so the agent can prioritize keyword matches for proper-noun queries and semantic matches for concept queries.
4. Test the search tool against a dataset with 50+ nodes, including at least 10 named people nodes, before integrating with the agent. Confirm that querying a person's name always surfaces their node as the first result.

**Warning signs:**
- Agent traversing neighborhoods of "relationship dynamics" nodes when looking for a specific person
- `search_graph` results never leading with the alias-matched node
- User-reported answers that describe the right concept but are attributed to the wrong person
- Agent calling `get_node_neighborhood` on 3+ different nodes before landing on the right one for a person-specific query

**Phase to address:**
Search tool implementation phase — keyword/alias boost must be implemented and tested before the query agent is built on top of it.

---

### Pitfall 10: Token Counter Drift in Log Budget Enforcement

**What goes wrong:**
Log compression fires when a node's log exceeds a token budget. The budget is checked by counting tokens in the log entries. If the token counting is inconsistent (e.g., estimated using whitespace splitting vs. actual BPE tokenizer counts), nodes get compressed too early (destroying history prematurely) or never compressed (letting context budgets blow up at query time). Edge case: if the token count estimate is wrong by 15%, a node with 1800 actual tokens may never trigger compression if the budget is set at 2000 and the counter reports 1700.

**Why it happens:**
Token counting is a precision-critical operation that developers often approximate. Using `len(text.split())` or `len(text) // 4` instead of the actual tokenizer produces errors that accumulate per log entry. At 30 log entries, a 5% per-entry error can result in a 150% total budget misestimate.

**How to avoid:**
1. Use the actual tokenizer for the model being used (e.g., `tiktoken` for OpenAI models, `transformers` AutoTokenizer for Anthropic/others). Never use approximations for budget-critical decisions.
2. Token budget check must include not just the log entries but also the node's summary and alias list — these appear in the same `get_node` response and consume context budget equally.
3. Set the compression trigger at 80% of the intended budget, not 100%. The safety margin ensures that log entries written between the check and the background compression job running don't push the node over budget before compression fires.
4. Log the token count and compression trigger events for each node during development. Verify against actual LLM token usage during test sessions.

**Warning signs:**
- Nodes with very long logs appearing in `get_node` responses that overflow visible context
- Compression running on nodes with very few log entries (over-aggressive trigger)
- Compression never running on long-lived nodes despite many updates (budget miscalculation)
- LLM context window errors during `get_node` calls for heavily updated nodes

**Phase to address:**
Log compression background job phase — must use real tokenizer from day one, not approximations.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Approximate token counting (split-based) | Faster, no dependency | Budget drift; compression misfires at scale | Never — use real tokenizer from day one |
| Storing log entries as JSON strings in array property | Simpler schema | Manual deserialization everywhere; Cypher queries can't introspect log fields | Only if log entries are never queried structurally via Cypher |
| Skipping alias-match boosting in search | Simpler search impl | Proper nouns get buried; agent navigates wrong nodes | Only in single-user MVP with 0 named people nodes |
| No tool call budget on ingestion harness | Simpler loop control | Runaway loop burns token budget on ambiguous transcripts | Never — add budget before first real ingestion |
| Using single cold storage location for all node archives | Simple implementation | Can't distinguish which archive belongs to which node without loading all archives | Never — key cold storage by node_id from day one |
| Skipping Whisper confidence filtering | Faster transcription pipeline | Hallucinated text enters graph, corrupts provenance | Only for developer testing, never for user data |
| Hardcoding hot-set k without recalibration | Simple deployment | Hot set eats context budget as themes grow; k=5 may be fine at 10 themes, wrong at 80 | Only during initial development with <10 themes |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| FalkorDB Python client (falkordb package) | Reusing a single `Graph` object across threads without a connection pool | Use `FalkorDB` client's connection pool; create one connection per operation or use async client with proper lifecycle |
| FalkorDB vector index | Assuming index is created automatically on first vector property write | Explicitly call `CREATE VECTOR INDEX` on schema initialization; absence of index causes silent brute-force fallback |
| FalkorDB Cypher queries | Using `MATCH (n) WHERE n.id = $id` for every lookup | Create unique indexes on `id` properties at schema init; without index, every node lookup is O(n) graph scan |
| Whisper Python library | Using `model.transcribe()` default settings, getting no word-level timestamps | Pass `word_timestamps=True` to `transcribe()`; the inline sentence timestamp rendering (VOICE-02) requires this |
| Whisper on long recordings (>10 min) | Memory spike loading the full audio into VRAM at once | Use chunked inference with `--chunk_length` or streaming approaches; 30-minute recordings with `large` model can OOM on consumer GPUs |
| Anthropic SDK tool calling | Agent tool call response parsing failing on multi-step tool use blocks | Handle `tool_use` content blocks explicitly; the SDK returns a list of content blocks, not a single response, and tool results must be returned in a specific message structure |
| FalkorDB `appendonly yes` persistence | Assuming `appendonly yes` in docker is sufficient for durability under fast shutdown | `appendonly yes` uses AOF rewriting; fast kill of container before rewrite completes can corrupt AOF — use `fsync=always` policy for personal data, or mount a volume and test recovery |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Loading full themes map into every ingestion/query prompt | Prompt size growing linearly with theme count; LLM latency increasing | Hot/cold split (already in v5 design) — enforce k themes max in hot set, names only in cold index | ~30+ themes at 80 tokens each = 2400 tokens always in context |
| Full node log in `get_node_neighborhood` response | Neighborhood responses consuming most of context budget | Return only last 2-3 log entries in neighborhood; full log available via `get_node` only | 5-hop neighborhood with 10-entry logs = potentially 5000+ tokens per neighborhood call |
| Embedding all fields on node creation | Slow ingestion pipeline; embedding calls made per-write | Embed only the summary (the search target); embed in batch at end of ingestion, not per-write | First few recordings: tolerable. After 50 writes per session: 50 individual embedding API calls |
| Searching the full graph on every `search_graph` call | `search_graph` latency growing with graph size | Use the vector index from day one; ensure keyword index also exists on alias arrays | Vector scan without index is O(n) at 1000 nodes, O(10n) at 10000 |
| Background theme agent run blocking next ingestion | User waits while theme agent finishes before next recording can be processed | Enforce async background job; use a task queue (e.g., a simple asyncio queue or Celery task) | With 50+ themes, theme agent can take 20-30+ seconds; synchronous would make every ingestion feel slow |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Storing raw transcripts in plaintext in a volume-mounted Docker container without encryption | User's most intimate thoughts accessible to anyone with filesystem access | Encrypt the SQLite/AOF files at rest using SQLCipher or filesystem-level encryption; this is a personal diary, not analytics data |
| Exposing FalkorDB port 6379 on 0.0.0.0 in development | Any process on the machine (or network, if firewall is loose) can read/write the user's personal graph | Bind to 127.0.0.1 only; add Redis AUTH password even in dev; the devenv.nix already maps to -p 6379:6379 which binds to all interfaces by default |
| Including raw transcript text in LLM API requests without rate limiting or request logging | Intimate user content sent to Anthropic API; no audit trail of what left the device | This is a known and accepted tradeoff (LLM is remote); but log all API requests with timestamps and sizes so the user can audit what was sent |
| Provenance offsets leaking between users if multi-user is ever added | One user's transcript provenance resolving against another user's transcript | Sequential IDs (rec:7) are global; if multi-user is ever added, all IDs must be namespaced by user. Document this constraint explicitly in the codebase now. |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Showing the graph construction process to the user during ingestion | User interprets tool calls and intermediate states as the "answer"; feels like watching a loading spinner with confusing output | Ingestion is a background process; user gets a simple completion notification ("3 nodes updated, 1 new theme detected"), not a tool call transcript |
| Answering queries without citing the user's own words | Answers feel like AI-generated summaries, not reflections of what the user actually said; trust erodes | Query agent must cite `get_transcript_span` quotes in every answer; "you said [exact quote] on [date]" is the product's core trust mechanism |
| Showing the graph structure directly to the user | Graph nodes and edges are an internal implementation detail; users don't think in knowledge graphs | Surface the graph's meaning (themes, patterns, connections) in natural language, not as a node browser |
| Silent ingestion failures | User thinks their recording was processed; graph is actually unchanged | Always surface ingestion status explicitly: success, partial (with reason), or failure. A silent failure is worse than a visible one. |
| Theme count growing without limit | Hot themes eventually need to be restricted to k, which means some themes disappear from the map silently | Theme retirement must be an explicit event the user can understand; "your meditation practice theme has been marked dormant" is better than it silently dropping from context |

---

## "Looks Done But Isn't" Checklist

- [ ] **Ingestion:** Often appears complete when `complete_ingestion` fires, but the bidirectional index (transcript `touched_nodes`/`touched_edges`) may not be populated if the completion call failed to include the payload correctly — verify the bidirectional index after every ingestion, not just the graph writes.
- [ ] **Log compression:** Appears to work when the inline compression entry appears, but cold storage may not have been written — verify `get_node_log_archive` returns the pre-compression entries before deleting them from the live log.
- [ ] **Provenance:** Appears correct when all writes have non-null provenance fields — verify by calling `get_transcript_span` for 5 random provenance references and confirming the returned text is semantically related to the node it is attached to.
- [ ] **Hot/cold theme rendering:** Appears correct when k themes are in the hot set — verify that a query whose subject is a cold theme still reaches the correct nodes via `get_theme(name)` + anchor traversal, not just via search.
- [ ] **FalkorDB persistence:** Appears durable when data survives a graceful restart — verify recovery after a hard kill (`docker kill`) of the FalkorDB container, which exercises AOF truncation recovery.
- [ ] **Whisper timestamps:** Appears aligned when short recordings transcribe correctly — verify with a 15-minute recording that provenance offsets at minute 12 actually return text from that part of the recording, not from minute 1 (off-by-one in segment accumulation is common).
- [ ] **Alias search:** Appears to work when exact-name queries return the right node — verify with an alias (not the canonical name) as the search query. "Papa" should return the same node as "Father" and "Dad".

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Node proliferation (many duplicate nodes) | HIGH | Rebuild from transcripts: wipe derived graph, re-run ingestion with improved disambiguation prompt. All transcript provenance is preserved; graph reconstruction is the design's safety net. |
| Silent summary drift | MEDIUM | Export all node summaries and logs. Re-run `update_node` with a re-synthesis prompt over each node's log history. Expensive in LLM calls but no data loss. |
| Incomplete provenance on existing nodes | HIGH | No automated recovery. Must re-run ingestion for affected transcripts (identified via bidirectional index gaps) with stricter provenance enforcement. |
| Log compression destroyed arc | MEDIUM | Pre-compression entries are in cold storage (if correctly implemented). Restore from cold storage, delete the compression entry, rebuild compression with corrected prompt. |
| Stale cold themes | LOW | Re-run theme agent with full graph read access, ignoring delta restriction, for one pass. This is expensive but the theme agent is the only component that has full authority over theme state. |
| FalkorDB AOF corruption | HIGH | Restore from the most recent clean AOF snapshot in the mounted volume. Replay any ingestions that occurred after the snapshot by re-running them from transcripts. |
| Whisper hallucinations in existing data | MEDIUM | Re-transcribe affected recordings with confidence filtering enabled. Identify nodes with provenance pointing to likely-hallucinated spans via `get_transcript_span` inspection. Delete affected graph writes and re-ingest. |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Node proliferation | Ingestion agent (prompt + search tool) | Run 10 test ingestions; count unique nodes created vs. expected; check for semantic duplicates manually |
| Summary drift | Ingestion agent (prompt design) + query evaluation | After 20+ sessions, audit 5 core nodes: read their log arc vs. their current summary; verify the summary still reflects the arc's current state |
| Incomplete provenance | Ingestion harness (validation layer) | Verify 100% of writes have valid provenance on first real ingestion run; spot-check `get_transcript_span` for 10 random provenance references |
| Agentic loop runaway | Ingestion harness (tool call budget + timeout) | Test with deliberately ambiguous transcript (mentions same person by 3 different names); confirm loop terminates within budget |
| Log compression arc loss | Log compression job (prompt + cold storage) | After first compression run, verify cold storage populated, verify arc mentions start date + end date + at least one change |
| Stale cold themes | Theme agent (hot-set selection + staleness rule) | After 20+ sessions, verify cold themes have been re-evaluated at least once; check cold theme anchor freshness |
| FalkorDB array serialization | Graph storage phase (schema + DAL) | Round-trip test: write node with 3-entry log, read back, assert exact equality |
| Whisper hallucinations | Transcription pipeline (confidence filter) | Test with 30-second silence recording; verify no text output; test with background noise recording |
| Hybrid search missing proper nouns | Search tool implementation (alias boost) | Query for 10 named people by alias; verify each surfaces as first result |
| Token counter drift | Log compression job (real tokenizer) | Write log entries until budget triggers; verify actual token count at trigger matches expected |

---

## Sources

- Architecture analysis of Memory-v5.md (2026-04-01) — HIGH confidence; pitfalls derived from spec ambiguities and known LLM behavior patterns
- Evolution analysis of Memory-v1 through v5 — design decisions in the version history reveal which problems the author already discovered and solved, and which remain open (node disambiguation, compression quality)
- FalkorDB Python client patterns — MEDIUM confidence; based on Redis module behavior and Cypher graph DB patterns; specific FalkorDB quirks unverifiable without live docs access
- Whisper hallucination behavior — HIGH confidence; well-documented behavior of the model on sparse/silent audio, consistent across multiple community reports in training data
- Agentic loop failure modes — HIGH confidence; documented in Anthropic's own agent building guides and widely observed in production agentic systems
- Graph knowledge base degradation over time — MEDIUM confidence; derived from academic literature on knowledge graph maintenance and LLM extraction quality studies (pre-August 2025 training cutoff)

---
*Pitfalls research for: AI voice journaling with LLM-driven semantic knowledge graph (Arachne)*
*Researched: 2026-04-01*
