# Feature Research

**Domain:** AI-powered voice journaling with semantic graph memory (private, mobile-first)
**Researched:** 2026-04-01
**Confidence:** MEDIUM — all competitor analysis drawn from training data (cutoff Aug 2025); no live product access. Named products (Day One, Reflect, Mem, Rewind, Obsidian, Roam Research, Notion AI) are well-represented in training data. Confidence is lower for very recent feature additions or pricing changes.

---

## Competitive Reference Products

Before the feature tables, a brief characterization of each reference product informs where each feature convention comes from:

| Product           | Category               | Key differentiator                                                       |
| ----------------- | ---------------------- | ------------------------------------------------------------------------ |
| **Day One**       | Traditional journaling | Polished UX, media-rich entries, timeline, On This Day                   |
| **Reflect Notes** | Networked notes + AI   | Backlink graph, daily notes, GPT summaries, Roam-like linking            |
| **Mem**           | AI-first note capture  | Auto-organization via AI, smart search, no manual folders                |
| **Rewind**        | Passive life capture   | Records everything (screen, mic), queryable retrospectively              |
| **Obsidian**      | PKM / local-first      | Local markdown files, plugins, graph view, bidirectional links           |
| **Roam Research** | Networked thought      | Bullet-based outliner, block references, daily notes, query blocks       |
| **Notion AI**     | Workspace + AI         | Block-based docs, databases, AI summarize/generate over existing content |

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete or broken for the target use case.

| Feature                                | Why Expected                                                                       | Complexity | Competitor Reference                         | Notes                                                                                                                                                                  |
| -------------------------------------- | ---------------------------------------------------------------------------------- | ---------- | -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Voice recording with one-tap start** | Primary capture method for voice-first app; friction at capture destroys the habit | LOW        | All voice apps                               | Must be one tap from locked screen or app launch. No setup before recording.                                                                                           |
| **Automatic transcription**            | Without text, voice is a black box — unsearchable, unquotable                      | MEDIUM     | Rewind, Day One (limited), voice memo apps   | Whisper is already chosen. Sentence-level timestamps are non-negotiable for provenance.                                                                                |
| **Search over entries**                | Users need to find what they said; no search = pile of opaque recordings           | MEDIUM     | Day One, Mem, Reflect, Obsidian              | Hybrid keyword + semantic is stronger than keyword alone. Required for MVP.                                                                                            |
| **Chronological entry list**           | Users orient by "when did I record this?" first                                    | LOW        | All journaling apps                          | Date-ordered list is the default navigation surface.                                                                                                                   |
| **Entry playback / transcript view**   | Users want to revisit what they said in full                                       | LOW        | Day One, Rewind                              | Display transcript with inline timestamps. Source audio should be retained from day one; playback is a near-term surface and text is still required.                   |
| **Cross-session recall**               | The whole value prop depends on not losing what was said                           | HIGH       | Mem, Reflect, Rewind                         | This IS the semantic graph. Without it, Arakne is just a voice memo app.                                                                                              |
| **Privacy / explicit data control**    | Personal thoughts are extremely sensitive; users need explicit trust signals       | MEDIUM     | Obsidian (fully local), Day One (E2E option) | Privacy is a first-class user concern for journaling. At minimum: clear data policy, no third-party ad/analytics, clear provider boundaries, and user-controlled data. |
| **Mobile app (iOS and/or Android)**    | Voice capture happens in-the-moment on mobile                                      | HIGH       | All                                          | Voice journaling only works if the device is always with you. Web-only fails.                                                                                          |
| **Readable entry history**             | Users must be able to scroll back through what they recorded                       | LOW        | All                                          | Required for trust that data is being captured and kept.                                                                                                               |

### Differentiators (Competitive Advantage)

Features that set Arakne apart. Not assumed, but create strong "aha" moments.

| Feature                                                     | Value Proposition                                                                                                                                     | Complexity | Competitor Reference                                                                                                                                | Notes                                                                                                                                                 |
| ----------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Semantic graph memory (nodes + edges)**                   | Understands _connections_ between thoughts, not just keyword co-occurrence. Finds that the same worry keeps appearing under different surface topics. | HIGH       | Reflect (backlinks, manual), Roam (manual block refs), Obsidian (manual) — all require user effort to link. Arakne builds the graph automatically. | Core differentiator. All competitors require manual linking. Arakne is the only one that infers relationships from speech.                           |
| **Open-ended natural language query over personal history** | "What have I been struggling with most this quarter?" answered from your own words with citations                                                     | HIGH       | Rewind (query over screen/audio), Mem (AI search), Notion AI (query over docs)                                                                      | Rewind is passive capture; answers are not grounded in cited spans. Mem is not voice-first. Arakne's provenance-grounded citation is unique.         |
| **Cited answers (provenance to transcript spans)**          | Every answer links back to the exact words you said — no hallucination, no generic advice                                                             | HIGH       | None found — Rewind is closest but cites screen captures, not transcript offsets                                                                    | The `get_transcript_span` architecture makes this possible. Critical for trust.                                                                       |
| **Theme tracking (emerging / active / dormant / deep)**     | Shows which concerns are intensifying vs. resolving over time without any manual categorization                                                       | HIGH       | Reflect (manual tags), Day One (tags), Mem (auto-tags)                                                                                              | Multi-dimensional status (depth + recency as separate axes) is novel. Competitor auto-tags are flat single-dimension labels.                          |
| **Voice-first, speech-natural capture**                     | Captures the arc of spoken thought, not just extracted facts. The full transcript is canonical.                                                       | MEDIUM     | Day One (typing primary, voice secondary), Mem (typing primary)                                                                                     | Designing around speech means preserving rambling, hedging, emotional tone — not just facts. Chunk-free ingestion is the key implementation decision. |
| **"Your own words" identity**                               | Answers are grounded in exact quotes, not AI paraphrase                                                                                               | HIGH       | None at this level                                                                                                                                  | This is the antidote to "generic AI advice." The app is a mirror, not a generator.                                                                    |
| **Graph rebuilding from transcripts**                       | User can trust that no data is silently lost or corrupted — the graph is a cache, not truth                                                           | HIGH       | None found explicitly                                                                                                                               | Obsidian approaches this with plain files. Arakne's explicit guarantee is stronger and operationalized.                                              |
| **Pattern surfacing across time**                           | "You've circled back to this question 7 times since January"                                                                                          | HIGH       | Rewind (to a limited extent, for calendar/screen), no journaling app                                                                                | Emerges from theme depth + log history. Requires sustained use to deliver.                                                                            |
| **Session orientation via themes hot set**                  | Agent already knows the terrain of your life before it starts reading — fast, accurate answers from first query                                       | MEDIUM     | None — competitors either search cold or require user to navigate                                                                                   | The cold-start problem is genuinely solved architecturally, not by UX tricks.                                                                         |

### Anti-Features (Deliberately NOT Building)

Features from the project's explicit Out of Scope plus inferred from Vision.md's "What Arakne Is Not" section.

| Feature                                               | Why Requested                                                            | Why It's Wrong for Arakne                                                                                                          | What to Do Instead                                                                                                                                   |
| ----------------------------------------------------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Streaks and gamification**                          | Habit-building, engagement metrics, DAU optimization                     | Creates guilt when users miss days. Turns self-reflection into a chore. Arakne's value is calm, not pressure.                      | No streaks. No notifications guilt-tripping. Users come when they have something to say.                                                             |
| **Task/checklist management**                         | Users naturally mix action items into journaling sessions                | Turns Arakne into a Notion/Todoist competitor. Scope creep. The journaling value prop gets diluted.                                | If a user mentions a to-do in speech, the agent captures it as a decision or intention node — not a managed task list.                               |
| **Social / sharing features**                         | Community and accountability feel natural for personal growth            | Personal thoughts are extremely private. Social pressure changes what users say. v1 is private.                                     | Keep data private and user-controlled. No public entries, no sharing, no followers.                                                                  |
| **Real-time streaming transcription**                 | Feels snappier, shows transcript forming as you speak                    | Increases latency complexity, requires streaming Whisper setup, adds infrastructure cost. Batch post-processing is sufficient.      | Process audio after recording ends. Show a processing indicator.                                                                                     |
| **Raw audio-only archive**                            | "Keep everything" feels safer to users                                   | Without meaning attached, raw audio is just a pile. Unsearchable, unquotable, cognitively overwhelming to revisit.                  | Store audio for playback and audit, but always pair it with transcript retrieval and semantic understanding. The transcript remains canonical.       |
| **Clinical / diagnostic features**                    | Mental health apps are adjacent; users in distress may want more         | Outside scope, liability risk, requires clinical validation. Not therapy.                                                           | Witness the user's inner state clearly; don't diagnose or prescribe. Recommend professional help if appropriate via prompting, not product features. |
| **Rigid note structure (folders, tags, hierarchies)** | Users expect organization tools from productivity apps                   | Imposes mental overhead before capture ("where does this go?"). Kills voice-first spontaneity.                                      | The graph structures automatically. No manual taxonomy required.                                                                                     |
| **Daily prompts / journaling guides**                 | Journaling apps typically offer prompts to overcome blank-page paralysis | Voice capture has no blank page. The user speaks freely. Prompts would impose a structure that contradicts Arakne's core use case. | Let users speak naturally. Agent finds structure.                                                                                                    |
| **Calendar integration / event logging**              | Life-logging apps often pull in calendar events                          | Moves product toward Rewind/life-log territory. Arakne is inner life, not external events.                                         | If users mention external events in speech, those become context nodes — not a calendar feature.                                                     |
| **Export to markdown / Obsidian / Roam**              | Power-user demand, portability                                           | Reasonable v2+ feature but creates maintenance burden and may confuse positioning. Not blocking.                                    | v1: transcripts are plaintext and recoverable. Export as stretch goal.                                                                               |

---

## Feature Dependencies

```
[Voice Recording]
    └──requires──> [Transcription (Whisper)]
                       └──requires──> [Ingestion Agent]
                                          └──requires──> [Semantic Graph (FalkorDB)]
                                          └──requires──> [Theme Agent] (async, non-blocking)

[Natural Language Query]
    └──requires──> [Semantic Graph] (populated, not empty)
    └──requires──> [Query Agent]
    └──requires──> [Transcript Span Retrieval] (for citations)
    └──requires──> [Several recorded sessions] (value emerges over time, not immediately)

[Cited Answers]
    └──requires──> [Provenance on every write] (transcript_id + offsets on every node/edge log entry)
    └──requires──> [Transcript Span Retrieval]

[Theme Tracking]
    └──requires──> [Semantic Graph] (populated with nodes)
    └──requires──> [Theme Agent]
    └──enhances──> [Natural Language Query] (cold-start orientation)

[Pattern Surfacing]
    └──requires──> [Theme Tracking] (with history)
    └──requires──> [Sustained use] (weeks/months of data)

[Search (hybrid keyword + semantic)]
    └──requires──> [Transcription]
    └──requires──> [Graph nodes with summaries] (embedding targets)

[Chronological Entry List]
    └──requires──> [Transcription] (so entries have readable previews)
```

### Dependency Notes

- **Voice Recording requires Transcription:** The entire downstream pipeline — graph, query, themes — is gated on having clean transcripts with timestamps. Whisper with sentence-level timestamp rendering must work before anything else.

- **Natural Language Query requires a populated graph:** The query agent has nothing to work with until at least a few sessions have been ingested. The cold-start UX problem is real: the app feels empty to new users until data accumulates. This is not a bug but a design constraint to communicate.

- **Cited Answers require provenance discipline at write time:** Every node log entry must carry `(transcript_id, start_offset, end_offset)`. This is a harness-enforced constraint, not an optional feature. Without it, the citation feature cannot be built later without a graph rebuild.

- **Pattern Surfacing requires sustained use:** This is the "months in" value prop from Vision.md. It cannot be shown to a new user. The early-session experience must still feel valuable without it (entry transcript view, immediate themes orientation).

- **Theme Tracking enhances Natural Language Query:** Themes solve the cold-start problem per query session. Without themes, the query agent must search blind. With themes, it starts oriented.

- **Search enhances all retrieval:** Hybrid search is the foundation of `search_graph`. Semantic search quality depends on embedding targets (node summaries). Keyword search covers proper nouns and aliases. Both are needed.

---

## MVP Definition

### Launch With (v1)

Minimum viable for Arakne's core value proposition: "speak, understand, retrieve."

- [ ] **Voice recording with one-tap start** — the capture surface. Everything else is downstream.
- [ ] **Whisper transcription with sentence-level timestamps** — canonical record. Blocks all downstream.
- [ ] **Ingestion agent with semantic graph** — graph build from transcript. Core intelligence.
- [ ] **Theme agent (async)** — orientation layer. Required for query cold-start to not feel broken.
- [ ] **Natural language query with cited answers** — the "aha" moment. Validates the core value prop.
- [ ] **Chronological entry list with transcript view** — trust signal. Users need to see their recordings exist.
- [ ] **Search (hybrid keyword + semantic)** — fallback navigation. Users who can't form a query need search.
- [ ] **Privacy: private/user-controlled data handling** — prerequisite for user trust with sensitive content.

### Add After Validation (v1.x)

Add when core loop is validated (users record and query repeatedly).

- [ ] **Pattern surfacing with temporal framing** — "You've returned to this theme 5 times since February." Trigger: users have 4+ weeks of data and query about their own patterns.
- [ ] **Entry playback (audio)** — Source audio is retained from day one, so playback is a near-term surface. Text transcript still covers the core retrieval need.
- [ ] **Graph rebuild from transcripts** — Admin/recovery feature. Trigger: first graph corruption incident or major model upgrade requiring re-ingestion.
- [ ] **On This Day / temporal flashbacks** — "A year ago you were thinking about X." Day One proved this creates delight. Trigger: users have 1+ year of data.
- [ ] **Mobile widget / quick-capture shortcut** — Reduces friction to sub-2-second capture. Trigger: user feedback that opening app is too slow.

### Future Consideration (v2+)

Defer until product-market fit is established.

- [ ] **Android support** — iOS first for quality control. Defer until iOS is proven.
- [ ] **Export (transcripts + graph)** — Portability and power-user demand. Defer: adds maintenance surface.
- [ ] **Multi-language transcription** — Whisper supports it, but prompt engineering for non-English needs validation. Defer.
- [ ] **Bi-temporal graph versioning** — "What was I thinking as of this date?" structurally. Memory-v5.md flags this as a future consideration (Graphiti arxiv 2501.13956). Defer.
- [ ] **Composite retrieval (vector + graph in one call)** — Performance optimization. Memory-v5.md flags Mem0/Reflect as reference. Defer.

---

## Feature Prioritization Matrix

| Feature                                    | User Value | Implementation Cost | Priority |
| ------------------------------------------ | ---------- | ------------------- | -------- |
| Voice recording (one-tap)                  | HIGH       | LOW                 | P1       |
| Whisper transcription with timestamps      | HIGH       | MEDIUM              | P1       |
| Ingestion agent + semantic graph           | HIGH       | HIGH                | P1       |
| Chronological entry list + transcript view | HIGH       | LOW                 | P1       |
| Natural language query with citations      | HIGH       | HIGH                | P1       |
| Theme agent (async)                        | HIGH       | HIGH                | P1       |
| Search (hybrid)                            | HIGH       | MEDIUM              | P1       |
| Privacy / user-controlled data handling    | HIGH       | MEDIUM              | P1       |
| Pattern surfacing (temporal)               | HIGH       | MEDIUM              | P2       |
| Audio playback                             | MEDIUM     | LOW                 | P2       |
| Graph rebuild / recovery                   | MEDIUM     | MEDIUM              | P2       |
| On This Day / flashbacks                   | MEDIUM     | LOW                 | P2       |
| Mobile widget / quick-capture              | MEDIUM     | MEDIUM              | P2       |
| Export (transcripts + graph)               | LOW        | MEDIUM              | P3       |
| Multi-language support                     | MEDIUM     | MEDIUM              | P3       |
| Bi-temporal graph versioning               | LOW        | HIGH                | P3       |

**Priority key:**

- P1: Required for MVP launch — blocks core value delivery
- P2: Add after initial validation — deepens value for returning users
- P3: Future consideration — after product-market fit

---

## Competitor Feature Analysis

| Feature                         | Day One                        | Reflect Notes            | Mem                         | Rewind                   | Obsidian / Roam                         | Arakne Approach                                      |
| ------------------------------- | ------------------------------ | ------------------------ | --------------------------- | ------------------------ | --------------------------------------- | ----------------------------------------------------- |
| **Voice capture**               | Secondary (photo/text primary) | Not primary              | Not primary                 | Passive always-on mic    | Not primary                             | PRIMARY — one-tap, the entire entry surface           |
| **Auto transcription**          | Limited                        | No                       | No                          | Yes (screen+audio)       | No                                      | Yes — Whisper, sentence timestamps, canonical         |
| **AI understanding of content** | Basic summarize                | GPT summarize, backlinks | Auto-organize, smart search | Search over screen/audio | Plugins (Obsidian), query blocks (Roam) | Full semantic graph — connections, not just summaries |
| **Knowledge graph**             | No                             | Backlink graph (manual)  | No                          | No                       | Manual (Obsidian), block refs (Roam)    | Automatic, inferred from speech                       |
| **Natural language query**      | No                             | Limited (AI chat)        | Yes (AI search)             | Yes (query your past)    | Limited                                 | Yes — grounded in cited transcript spans              |
| **Cited answers / provenance**  | No                             | No                       | No                          | Screen captures only     | No                                      | Yes — exact `(transcript_id, offset)` citations       |
| **Theme / pattern tracking**    | Tags (manual)                  | Tags (manual)            | Auto-tags (flat)            | No                       | Tags (manual)                           | Automatic, multi-dimensional status                   |
| **Privacy**                     | E2E encrypt option             | Cloud-based              | Cloud-based                 | Local by default         | Local (Obsidian)                        | Private/user-controlled by design                     |
| **Mobile-first**                | Yes                            | Yes (secondary)          | Yes                         | macOS only (v1)          | No                                      | Yes — primary platform                                |
| **Cold-start orientation**      | None                           | None                     | None                        | None                     | None                                    | Yes — themes hot set per session                      |
| **Streaks / gamification**      | None                           | None                     | None                        | None                     | None                                    | Explicitly none                                       |
| **Social / sharing**            | Optional                       | None                     | None                        | None                     | Publish (Obsidian)                      | Explicitly none (v1)                                  |

### Key Observations

1. **No competitor does voice-first + auto semantic graph.** Day One is polished journaling but typing-first. Reflect is note-linking but manual. Mem is capture-and-search but not voice-native. The gap is real.

2. **Citation quality is universally poor.** Rewind cites screen captures. Mem surfaces relevant notes but doesn't quote within them. No competitor guarantees "these words came from your recording at 0:14." Arakne's provenance architecture fills a genuine gap.

3. **Automatic relationship inference doesn't exist anywhere.** Obsidian and Roam are the best knowledge graph tools but require the user to create the links. The work of "this feeling about my career is connected to my relationship with my father" is left to the user. Arakne's LLM-driven graph inference is the core differentiator.

4. **Theme tracking is entirely manual everywhere.** Day One and Obsidian use user-defined tags. Mem auto-tags but it's flat and keyword-driven. Nobody has a multi-dimensional status model (depth + recency) auto-maintained by an LLM.

5. **Mobile voice UX pattern (from market):** One-tap record button, prominent on home screen. Waveform visualization during recording for audio feedback. Haptic feedback on start/stop. Processing indicator after stop. Entry list shows first sentence of transcript as preview. These are the interaction conventions users expect from voice-first mobile apps.

6. **The cold-start user experience gap.** Every AI memory app (Mem, Reflect) has the same problem: new users see an empty product. Arakne has this too. But the themes architecture provides faster value than competitors — after the first 2-3 sessions, themes emerge and query quality improves noticeably. Messaging needs to set appropriate expectations ("value grows with use").

---

## Arakne-Specific Feature Constraints

These constraints are derived from the project's stated design philosophy and are binding:

| Constraint                                            | Source                   | Implication                                                                                                              |
| ----------------------------------------------------- | ------------------------ | ------------------------------------------------------------------------------------------------------------------------ |
| All semantic decisions delegated to LLM               | Memory-v5.md, PROJECT.md | No rigid extraction schema, no hardcoded node types — cannot add a "tag this entry as X" feature                         |
| Graph and themes must be rebuildable from transcripts | PROJECT.md               | Cannot allow any graph state that doesn't trace back to a transcript + offset                                            |
| Provenance on every write                             | PROJECT.md               | Every UI interaction that creates data must carry transcript reference — no "manual add" features that bypass provenance |
| Sequential readable IDs, no UUIDs                     | PROJECT.md               | Internal ID scheme; UX hides IDs from user but they are the backbone of citations                                        |
| No type field on nodes                                | Memory-v5.md             | Cannot build features that filter by "node type" — all semantics live in summary                                         |

---

## Mobile UX Patterns for Voice Capture

Based on established patterns from voice-first mobile apps (Otter.ai, voice memo apps, Rewind mobile UX research):

| Pattern                               | What It Is                                                   | Why It Works                                         | Notes                                                                                                  |
| ------------------------------------- | ------------------------------------------------------------ | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| **Large persistent record button**    | Full-width or center-dominant capture CTA on home screen     | Reduces friction — no navigation before recording    | Standard for all voice apps. Must be visible without scrolling.                                        |
| **Background recording support**      | App can record while screen is locked or another app is open | Users often record while driving, walking, commuting | Requires background audio permission. Critical for the "speaking while doing something else" use case. |
| **Waveform / level meter feedback**   | Visual indication that mic is active and picking up audio    | Reassurance that recording is working                | Absence creates anxiety ("is it capturing?"). Even a simple pulsing animation works.                   |
| **Instant stop = save**               | Stopping the recording immediately commits it                | No "discard?" confirmation on stop                   | Users trust the app more when capture feels irrevocable. Undo is less important than certainty.        |
| **Processing indicator after stop**   | Shows transcription + ingestion are happening                | Manages expectation that AI processing takes time    | Must not block the next recording. Fire-and-forget feel is the goal.                                   |
| **First-sentence transcript preview** | Entry list shows opening words of transcript                 | Users recognize entries by how they started speaking | Better than a timestamp-only list. Day One does this with the first sentence of text.                  |
| **Relative timestamps**               | "3 hours ago", "Yesterday", "Last Tuesday"                   | Matches how humans think about recency               | Arakne's memory architecture already specifies this for agent prompts — should match in UI.           |
| **Swipe to playback / expand**        | Secondary action reveals full transcript or plays audio      | Keeps list clean without hiding data                 | Common iOS list interaction pattern.                                                                   |

---

## Sources

- **Day One** — training data, feature set through Aug 2025 (MEDIUM confidence)
- **Reflect Notes** — training data, feature set through Aug 2025 (MEDIUM confidence)
- **Mem** — training data, feature set through Aug 2025 (MEDIUM confidence)
- **Rewind** — training data, feature set through Aug 2025 (MEDIUM confidence)
- **Obsidian** — training data, feature set through Aug 2025 (MEDIUM confidence)
- **Roam Research** — training data, feature set through Aug 2025 (MEDIUM confidence)
- **Notion AI** — training data, feature set through Aug 2025 (MEDIUM confidence)
- **Otter.ai** — training data, voice capture UX patterns (MEDIUM confidence)
- **Arakne Vision.md / Memory-v5.md / PROJECT.md** — authoritative project source (HIGH confidence)
- **Graphiti (arxiv 2501.13956)** — referenced in Memory-v5.md for bi-temporal versioning (cited by project team)
