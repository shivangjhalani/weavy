# LifeOS

> **Build a garden for your life.**

---

## What It Is

LifeOS is an audio journaling app. You talk, it listens, it remembers.

Most people have a lot going on in their heads and no good way to get it out. Written
journaling is slow and formal. Voice memos disappear into a black hole. Nothing out
there gives you the feeling of building something cumulative. LifeOS fills that gap —
it makes speaking your thoughts worth doing, because what you say gets organized,
held, and stays findable.

---

## The Problem It Solves

Thinking without externalizing tends to circle.
Not from lack of reflection — but because **the mind is a poor witness to its own changes over time.**

Talking is the most natural way most people process things. LifeOS catches what you
say, organizes it, and gives it back in a way that's actually useful - so the thinking
you're already doing doesn't get lost.

---

## Who It's For

The user has a full inner life but no good outlet for it.

- **The Striver** — Seeking better work, clearer goals, a more intentional life.
  Needs to untangle ambitions and track the decisions behind them.

- **The Processor** — Going through something difficult: grief, a breakup, a career
  change. Trying to make sense of complex, shifting emotions.

- **The Thinker** — Constantly losing the thread of their own ideas. Needs to
  offload just to find peace.

What they share: a full inner life, no good outlet, and a quiet cost from keeping
everything inside their head.

---

## What It Does Over Time

LifeOS builds a record of your thinking. Not a log of events — a record of _you_.

- Your open questions and unresolved tensions
- Your recurring topics and how they evolve
- The decisions you made and how you felt about them
- How you've changed — visible to you months later

You can look back at yourself from six months ago and understand your own arc. You
can ask it things about yourself and get answers grounded in what you've actually said.

---

## The Feeling

> _"Calm and safe. Like a personal garden — private, cumulative, yours."_

The metaphor is a garden: organic, tended over time, growing more beautiful the longer
it exists. It is a private sanctuary, not a dashboard.

The emotion the product must deliver: **quiet confidence**. The user leaves feeling
lighter — knowing their thoughts are held somewhere safe, so their head no longer has
to hold all of it.

---

## What It Is NOT

These anti-goals are as important as the goals. Any design decision that drifts toward
these must be rejected.

| Not This            | Why It's Wrong                                                                 |
| ------------------- | ------------------------------------------------------------------------------ |
| A productivity tool | No checklists, due dates, or kanban boards. Not Notion. Not Slack.             |
| A tracker           | No streaks, no gamification, no guilt-trip notifications.                      |
| Therapy             | Not clinical, not diagnostic. A tool for self-witnessing, not treatment.       |
| A black hole        | Never a list of raw audio files. The design must surface _meaning_, not files. |

---

## Memory Architecture

LifeOS is built around a three-phase memory model, grounded in cognitive science.
The central principle: **how well something is encoded determines how well it can
later be retrieved** — not how hard you search at recall time. This means the work
happens upfront, at capture.

---

### Phase 1 — Encoding

The moment of capture. A single audio recording rarely contains a single thought —
it contains several. LifeOS must treat this correctly.

**Episode Segmentation**
A continuous audio dump is broken into discrete, meaningful units called episodes.
Each episode represents a single coherent topic or thought: _"Work anxiety,"
"Unresolved thing with a friend," "Idea about the project."_ These episodes — not
the raw recordings — are the true atomic units of the system.

**Contextual Tagging**
Every episode is anchored with metadata at the moment of encoding:

- Temporal context — when it was captured
- The Journal it belongs to, and the parts of journal it was extracted from
- People and entities mentioned
- Emotional tone and arousal
- Themes and topics
- Learnings
- Open questions
- Links to related past episodes

The richer this metadata, the more powerful retrieval becomes later.

---

### Phase 2 — Storage

Structured episodes with their full context tags, held in a queryable store.

Each episode is linked to:

- The source journal entry and transcript passage (citation-first)
- Thematically related episodes across time
- People and projects that appear across multiple entries
- Its status: resolved, ongoing, or open

Storage is designed around the assumption that **retrieval will always start with
partial, fragmentary cues** — not precise keywords. The data structure must support
that.

---

### Phase 3 — Retrieval

Human memory is cue-driven. Retrieval doesn't happen in one step — it happens as
a **retrieval journey**: start broad with a small contextual cue, surface a subset,
browse it, let more details emerge, narrow further.

The LifeOS interface must support this sequential narrowing:

- **Layer 1** — Summary retrieval: _"Which journal is this from?"_
- **Layer 2** — Passage retrieval: _"Where exactly was this said?"_

A fragmentary memory — a person's name, an emotion, a rough timeframe — should
be enough to begin the journey. The system surfaces the rest.

---

### Memory Layers

| Layer                 | What It Contains                                                                                  | Analog              |
| --------------------- | ------------------------------------------------------------------------------------------------- | ------------------- |
| **Raw Audio**         | Original recording file for each journal, retained permanently                                    | Source artifact     |
| **Transcript**        | Timestamped text derived from audio — canonical source of truth for all higher layers             | Verbatim record     |
| **Episodes & Topics** | Segmented topic blocks with thread reconnection across non-adjacent spans                         | Individual memories |
| **Temporal Graph**    | Entities, themes, emotions, unresolved tensions, and cross-episode links with temporal behavior   | Associative network |
| **Stable Memory**     | Durable facts the system learns over time: recurring people, ongoing projects, long-term patterns | Semantic memory     |

---

### Open Loops — Future Layer (Deferred Beyond V1)

Research on _retrieval-induced forgetting_ shows that selectively surfacing some
memories can passively suppress related but unreviewed ones. If LifeOS only ever
surfaces thoughts users search for, it risks burying the ones they haven't returned to.

**Open loops tracking is memory hygiene, not a task manager.**

When implemented, the system would proactively surface:

- Unresolved questions that haven't been revisited
- Decisions that were made but never followed up
- Topics that recur across entries without resolution

This is architecturally deferred beyond V1, but the memory layers above (particularly
the Temporal Graph and Stable Memory) preserve the data needed to support it later.

---

## Summary

| Dimension              | LifeOS                                                       |
| ---------------------- | ------------------------------------------------------------ |
| **Format**             | Audio journaling — speak, don't type                         |
| **Core output**        | Organized, findable, cumulative record of your thinking      |
| **Atomic unit**        | The episode (a segmented topic block, not the raw recording) |
| **Memory model**       | Encode richly → store with context → retrieve by journey     |
| **Emotional register** | Calm, private, grounding — a garden, not a dashboard         |
| **What it avoids**     | Productivity tools, trackers, gamification, raw file lists   |
| **Long-term value**    | Self-knowledge: patterns, evolution, answered open loops     |
