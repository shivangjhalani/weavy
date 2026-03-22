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

Talking is the most natural way most people process things.
LifeOS catches what you say, organizes it, and gives it back in a way that's actually useful — so the thinking you're already doing doesn't get lost.

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
- Your recurring themes and how they evolve emotionally over time
- The decisions you made and and what was driving them
- Insights - moments of realization - accumulated and held
- The things you keep coming back to without realizing it.

Six months from now, you can look back at yourself and understand your own arc. You can ask it things about yourself and get answers grounded in what you've actually said.

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

# The Memory

> Question is: How do you represent a human's evolving inner life in a data structure that supports arbitrary, open-ended queries without baking in assumptions and heuristics about what questions will be asked?

#### Goal

Design representation to be maximally expressive, and delegate query strategy entirely to the agent at query time.
That leads to

1. LLM-Defined Semantic Graph: I do not design schema and structure, I define the most abstract, universally valid structure - and leave all semantic decisions to the LLM. This ensures that the app becomes moe powerful as models become better
2. Agentic retrieval: Tell LLM what is available, and it will figure out how to find the answer.

The structure that I believe is universally valid for journaling:

1. Things (concepts, people, emotions, decisions, questions, themes): nodes
2. Relationships between things: edges with free-form natural language labels
3. Temporal metadata on every node and edge
4. The raw episodes (episode = chunk of journal that talks about one thing)

This I believe is heuristic free.

## Three layered memory

### Layer 1: Episodic

Episode = Chunk of a journal talking about one thing.
This is the source of truth, everything can be reconstructed from here.

Each episode is a json with the following fields (Not set in stone, can change as I learn more, but this is the starting point):

1. Journal it belongs to
2. Absolute timestamp (Recording start time + offset time from whisper json)
3. Title (4-6 word description)
4. Summary (embedding of this summary is generated to represent this episode, this is what episode search is run against)
5. Text (Raw transcript text for that episode, this is what gets fed to the LLM for synthesis)

### Layer 2: Semantic Graph

In this layer, episodes are fed in sequentially in batches (episodes from same journal batched together come in at once)

This layer is a knowledge graph where an LLM extracts things, and relationships from each episode and updates / adds on to the graph.
I don't define the entity types or relationship types in advance. A node might be "my relationship with my father", "the startup idea from March", or "fear of disappointing people" - whatever the LLM judges to be meaningfully distinct from what already exists. Edges are also free-form: "is a source of", "conflicts with", "evolved into", "father of".

For each episode, LLM extracts (subject, relation, object). Crucially, for each extracted thing, the LLM also queries the existing graph to determine whether subject and object is a new node or a reference to an existing one, and if that relation exists already or a similar relation can be updated and not create a new relation. Node disambiguation is difficult, need to figure out how to do. (Semantic search over all subjects and objects with the extracted things and then letting LLM decide if they are the same thing I think is one way to bring out possibly same nodes). "Father" and "Vishal" are same, but it is possible that "Father" is mentioned before and "Vishal" name later.

A full fledged AI agent should be able to morph the graph however it wants. It should be able to create new things, update/append existing, delete, merge, search, etc every node and relation. Need a nice harness around the agent.

Both nodes and edges also carry additional data, need to think more on this but for now this is what I have thought of: temporal metadata: when first mentioned, when last mentioned, and a history of emotional valence over time.

The graph grows organically.

> Doubt: can layer 1 (episode segmentation from transcript) and work of layer 2 (extraction of things and relationships) be done in just one LLM API call? Or would it hurt?

### Layer 3: The Themes

It is an additional layer on top of the graph which handles the big picture. These are memos, they are like a thoughtful observer writing notes about patterns they're noticing: recurring tensions, shifts in dominant concerns, emerging clarity about something previously confused.

The question here is how will the AI agent figure out which episodes and graph nodes to see and create memos.

These memos live as text with embeddings.
They contain additional data like which graph nodes / episodes they are inferred from. (Again, need to think more here)

---

# The retrieval

User -> Query -> Agent
Agent knows about the 3 memory layers, decides which one (or more) to access, runs in a loop till it has an answer.

---

# The Agent Harness

I want to build one modular harness for the agent to be able to control all things and then selectively allow particular tools to be accessed by the agent at particular times of the pipeline.
