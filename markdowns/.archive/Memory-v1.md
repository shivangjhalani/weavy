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

I want to build one modular harness for the agent to be able to control all things, this single agent with it's whole arsenal is what runs during

    1. Ingestion of a transcript,
    2. During query / chat time and
    5. Memo work.

One advantage of a unified harness: the user can tell the agent about things during chat - corrections, clarifications, context - and the agent can modify the memory layer in real time. Memory is live, not just a batch-processed artifact.

Harness = LLM in an agentic loop + Tools

Question: HOW do I give the agent a very natural & native view of the graph so that the agent can reason well over the graph for both writing and querying tasks.
