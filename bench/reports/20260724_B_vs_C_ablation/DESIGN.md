# The elegant memory layer: tiered retrieval over one ground truth

A design informed by the B-vs-C ablation (`FINDINGS.md`). The guiding rule: **every part
must earn its place with a mechanism *and*, where possible, a measured win.** Below, claims
are tagged **[evidence]** (backed by the ablation) or **[hypothesis]** (reasoned, not yet
tested here).

## The one idea

Memory is **two layers and three retrieval tiers, never a flat union.**

```
                         ┌─────────────────────────────────────────┐
   WRITE                 │  Episodes  (immutable raw text, dated)    │   ← ground truth
   text ──ingest──▶      │      │ distil                             │
                         │      ▼                                    │
                         │  Semantic graph (entities + relations)    │   ← distilled index
                         │      +                                    │
                         │  Raw-text chunk index (episode spans)     │   ← recall floor
                         └─────────────────────────────────────────┘

   READ  ──▶  tier 1: graph search + traverse ──hit──▶ answer   (precise, multi-hop, cheap)
                         │ miss
                         ▼
              tier 2: raw-text vector search ──hit──▶ answer     (recall floor, dated detail)
                         │ miss
                         ▼
              tier 3: "no record"                                (calibrated abstention)
```

The tiers are **strictly ordered and never merged into one ranked list.** Tier 2 is consulted
only when tier 1 fails to answer. That ordering is the whole design — it is what makes this
Model C (a demoted floor) and not the Model A flat-union that competes index against ground
truth and was correctly deleted.

## Why each piece exists (and why not less)

### Two storage layers

- **Episodes — immutable, verbatim, dated.** The only thing that is *true* by construction.
  Never mutated, never deleted, never summarized in place. Everything else is derived and
  disposable. **[evidence]** Both winning conditions ultimately answer hard questions by
  reading an episode; the distilled layer alone is lossy.

- **Semantic graph — one node per entity, one embedding, edges carry embedded facts.** The
  structured surface: entity identity, relationships, multi-hop, temporal logs. **[evidence]**
  Keep the single-vector node (aliases + summary) and drop note-history stuffing / dual
  embeddings — the ablation ran on exactly this shape and it was sufficient; the graph tier
  answered the majority of single-hop and relational questions cheaply.

### Two indexes, one job each

- Graph vector+keyword index over nodes/edges → tier 1.
- Raw-text chunk index over episode spans → tier 2.

No third index, no per-node second vector. **[evidence]** The dual-embedding machinery the
prior refactor removed stays removed; nothing in the results needed it.

### Why the raw-text tier is not optional (the reversal)

The navigational-purity design treated raw-text search as a crutch that "hides ingestion
laziness." The ablation says otherwise: **[evidence]** the raw-text tier delivered +5.7 pts
overall, +12 on temporal, at **lower** token cost and latency. It is the dominant recall
mechanism for specific/dated/incidental facts *and* it shortens runs by ending the agent's
reformulation flailing. A mechanism that adds recall while cutting cost is not a crutch — it
is the load-bearing wall. Reaching raw text by graph *navigation* instead (the bnav arm) does
**not** substitute: it depends on the distilled summary having flagged the cue, which is
exactly what fails.

## The read path in full

1. **Tier 1 — graph.** Hybrid search (embedding + keyword) over nodes and edges; traverse
   neighbors for multi-hop; follow `mentioned_by` / edge provenance to read source episodes
   for specifics. Answers structured, relational, and "how is X related to Y" questions with
   precision and — when it hits — the fewest tokens.
2. **Tier 2 — raw text (demoted).** On a tier-1 miss, vector search over episode chunks; read
   the full episode behind a promising span. Recovers dated utterances, attributes stated in
   passing, and anything ingestion never distilled. **Never ranked against tier-1 results.**
3. **Tier 3 — abstain.** Only after both tiers fail: "no record." Preserves false-premise
   refusal.

## The one knob you must expose

**Abstention aggressiveness.** **[evidence]** Adversarial abstention fell 42.9 → 38.4 as the
system tried harder to answer. Recall and false-premise-resistance trade off directly, so the
threshold ("how much evidence before answering vs. saying no record") must be an explicit,
tunable policy — not an emergent accident of the prompt. Product surfaces that punish
confident wrong answers set it conservative; recall-maximizing evals set it loose.

## What makes it *observable* instead of a hidden net

The original objection to a fallback was that it makes ingestion laziness invisible. Fix that
without giving up the recall: **[hypothesis]** log every tier-2 hit as an *index defect* — the
graph should have answered and didn't. That stream is (a) a direct quality metric for
ingestion and (b) the trigger for a **repair loop**: re-ingest the episode that tier 2 had to
rescue, adding the missing node/alias/edge, so the *next* identical question is answered by
tier 1 (cheaper, structured). The net stops hiding the wound and starts healing it. Untested
here; the ablation only establishes that the tier is worth having.

Also **[hypothesis]**: a write-time navigability check (generate probe questions from a fresh
episode, confirm tier-1 retrieval reaches them, repair on failure) moves the same correction
earlier — from query time to ingest time.

## What to build, in order

1. **Keep** the two-layer store, single-vector nodes, immutable dated episodes. *(shipped)*
2. **Add** the raw-text chunk index + demoted `search_episodes` tier. **[evidence: primary
   recall + cost win]** — this is the one change that moves the number.
3. **Expose** abstention aggressiveness as an explicit policy knob. **[evidence]**
4. **Instrument** tier-2 hits as index-defect signals. **[hypothesis, cheap, high-value]**
5. **Then** consider the repair loop and write-time navigability check. **[hypothesis]**
6. **Later** a sub-episode locator to cut tier-2 read tokens — allowed only if addressed
   through the graph/provenance, never as a competing search surface.

## What *not* to build

- No flat union of chunks and nodes in one ranked list (Model A) — the tiering is the point.
- No second per-node embedding, no note-history stuffing — unneeded at the shape tested.
- No pure-B "graph is the sole surface" stance — **[evidence]** it costs ~6–8 pts of recall
  *and* more money for an architectural purity the benchmark does not reward.
