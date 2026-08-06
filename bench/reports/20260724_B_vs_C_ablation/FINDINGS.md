# Navigational graph memory (B) vs. graph + raw-text fallback (C)

**Question.** Can a *pure* Model B system (semantic graph is the sole search surface;
raw episodes reachable only by navigation) match Model C (graph primary + a demoted
raw-text search tier) on LoCoMo — and what would close any gap?

**Answer, stated plainly and against my prior prediction: no.** On this dataset C beats
the best B variant by ~5.7 points overall (paired McNemar p ≈ 0.018) *and* is cheaper and
faster. My pre-registered prediction that "B + forced episode navigation lands within noise
of C" was **falsified**.

## Method

Controlled ablation isolating exactly one variable: *how raw episode text is reached at
query time.* Everything upstream is held byte-identical.

1. Ingested 3 LoCoMo conversations once (themes on, gpt-4o-mini, text-embedding-3-small)
   → one pristine semantic graph per conversation.
2. `GRAPH.COPY`'d each into three identical copies: `base_*`, `bnav_*`, `cfall_*`.
3. Applied one change per condition:
   - **base** — shipping pure-B query prompt (navigate via `mentioned_by`/`get_session`).
   - **bnav** — B + a *mandatory* pre-abstention step: `list_sessions` over the inferred
     time window, then read candidate episodes. Reaches raw text **by graph navigation**.
   - **cfall** — B + a demoted `search_episodes` tool (vector search over raw-text chunks),
     usable only after graph retrieval fails. Reaches raw text **by direct vector search**.
4. Answered all 497 questions/condition against the shared indexes (answer-only, no
   re-ingest), same judge (gpt-4o-mini LLM-as-J).

Because all three share the identical graph *and* the identical stored episodes, the only
thing under test is the retrieval path to ground truth: **navigate vs. vector-search.**

## Results (LoCoMo J score, 3 conversations, 1 seed)

| Condition | overall | single | multi | temporal | open | adversarial↑ | tok/q | $/run | p50 |
|---|---|---|---|---|---|---|---|---|---|
| base (pure B) | 41.0% | 51.0 | 29.7 | 31.1 | 28.6 | 42.9 | 42,917 | $3.25 | 8.9s |
| bnav (B + forced nav) | 42.9% | 51.5 | 31.1 | 34.4 | 38.1 | 41.1 | 42,022 | $3.18 | 8.3s |
| **cfall (Model C)** | **48.6%** | **55.5** | **36.5** | **46.7** | 33.3 | 38.4 | **31,047** | **$2.36** | **7.9s** |

Paired vs. base: bnav net **+7** questions (35 recovered / 28 regressed); cfall net **+29**
(53 / 24). Direct cfall vs. bnav: net **+22 / 385**, McNemar two-sided **p ≈ 0.018**.

## What the data says (mechanism, not just scores)

1. **C wins decisively, and the win is real, not noise.** +5.7 overall vs. the best B, at
   p ≈ 0.018 on a *single* 3-conversation run. The gap is largest on **temporal (+12.3)** and
   **multi-hop (+5.4)** — the classes that hinge on recovering a specific dated utterance.

2. **The win is a capability gap, not a prompt artifact.** bnav has the *same* raw episodes
   and is explicitly ordered to read them before abstaining — it just reaches them by
   `list_sessions → get_session`. That navigation depends on the session *summary* flagging
   the relevant detail and on picking the right episode among many; when the distilled layer
   didn't surface the cue, the agent picks wrong or gives up. cfall's vector search goes
   straight to the chunk that literally contains the answer, regardless of whether the entity
   was indexed or linked. **This is precisely the "recall cliff" the navigational-memory
   design doc predicted — and it is load-bearing, not hypothetical.**

3. **C is cheaper and faster, overturning the "chatty fallback" assumption.** cfall used
   **28% fewer tokens** (31K vs 43K/q) and lower p50/p95 latency. Reason: a direct hit ends
   the run in fewer turns, whereas pure-B agents burn turns reformulating `search_graph`
   before abstaining. The fallback isn't a tax on top of B — it *replaces* B's most wasteful
   failure mode.

4. **Forced navigation (bnav) is a band-aid, not a fix.** +1.9 overall, and it regressed
   almost as many questions as it recovered (28 vs 35), mostly single-hop — pushing the agent
   to read whole episodes injects noise on questions it used to get right.

5. **The one real cost of C: abstention precision.** Adversarial abstention falls
   monotonically 42.9 → 41.1 → 38.4. The more aggressively a system reaches for an answer,
   the more it takes the bait on false-premise questions. C's recall gain (+7.6) dwarfs its
   abstention loss (−4.5) on the LoCoMo headline, but in a product this is the knob that
   trades "answers more" against "makes things up."

## Threats to validity (declared)

- **Single seed, 3/10 conversations.** The *direction* is significant by paired McNemar, but
  absolute magnitudes will move ±several points on the full set / other seeds. The ranking
  (C > bnav ≥ base) is the durable claim, not "48.6%".
- **Judge = generator model (gpt-4o-mini).** Shared across conditions, so it doesn't bias the
  *comparison*, but absolute scores inherit judge lenience.
- **Chunking is crude** (~1200-char line-based). C's numbers are a *floor*; a better locator
  would only widen the gap.
- Not tested: whether a stronger ingestion model shrinks the gap by indexing more entities.
  Plausible it narrows, implausible it closes — raw-text search also gets the un-extractable
  incidental details by construction.

## Bottom line for the architecture

Pure B is the right *purity* statement but the wrong *product* choice: it leaves ~6–8 points
of recall on the table and is simultaneously more expensive. The elegant system is **not**
"graph as sole surface." It is a distilled graph as the primary, structured surface **plus a
strictly-demoted raw-text tier as the recall floor** — reached only after graph retrieval,
never ranked against it. That is Model C, implemented cleanly (a separate tier the agent
falls to), which is categorically different from the *flat-union* Model A the original
refactor correctly deleted. See `DESIGN.md`.
