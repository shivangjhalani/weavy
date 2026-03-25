# Architecture Research

**Domain:** LLM-powered audio journaling memory system (backend)
**Researched:** 2026-03-25
**Confidence:** HIGH

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Experiment Scripts                         │
│  (ingest.py, query.py, memo.py, eval.py)                    │
├─────────────────────────────────────────────────────────────┤
│                    Agent Harness                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │ Ingest   │  │ Query    │  │  Memo    │  ← role prompts  │
│  │  Role    │  │  Role    │  │  Role    │                   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                  │
│       │              │             │                         │
│       └──────────────┴─────────────┘                        │
│                      │                                       │
│              ┌───────┴───────┐                               │
│              │  Tool Router  │                               │
│              └───────┬───────┘                               │
├──────────────────────┴──────────────────────────────────────┤
│                   Memory Layers                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Transcripts  │  │   Semantic   │  │   Themes     │      │
│  │  (Layer 1)   │  │    Graph     │  │  (Layer 3)   │      │
│  │              │  │  (Layer 2)   │  │              │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
├─────────┴──────────────────┴────────────────┴───────────────┤
│                   Core Infrastructure                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ FalkorDB │  │  Vector  │  │  Gemini  │  │   Groq   │   │
│  │  (graph) │  │  Store   │  │  (LLM +  │  │ (Whisper)│   │
│  │          │  │          │  │  embeds)  │  │          │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | Boundary |
|-----------|----------------|----------|
| **Experiment Scripts** | Entry points for manual testing — each script runs one workflow | Calls agent harness, never touches storage directly |
| **Agent Harness** | Agentic loop: LLM + tools + role-specific system prompt | Owns prompt construction, tool dispatch, loop control |
| **Tool Router** | Dispatches agent tool calls to memory layer implementations | Maps tool names to functions, handles errors |
| **Transcript Store** | Store/retrieve raw transcripts with episode spans | Owns transcript CRUD, episode span indexing |
| **Graph Store** | FalkorDB operations: nodes, edges, summaries, logs, aliases | Owns all Cypher queries, disambiguation logic |
| **Theme Store** | Theme CRUD, heat/salience management, embedding search | Owns theme lifecycle and decay |
| **Vector Store** | Embedding storage and similarity search across all layers | Shared by all memory layers for semantic search |
| **LLM Client** | Gemini API calls for reasoning and embedding generation | Single client, shared across all roles |
| **Transcription** | Audio → text via Groq Whisper API | Stateless transform, called by ingest script |

## Recommended Project Structure

```
lifeos/
├── scripts/              # Manual experiment entry points
│   ├── ingest.py         # Feed audio/transcript, run ingestion
│   ├── query.py          # Ask questions, see retrieval
│   ├── memo.py           # Run theme extraction
│   └── eval.py           # Run RAGAS evaluation
├── agent/                # Agent harness
│   ├── harness.py        # Core agentic loop
│   ├── roles.py          # Role-specific system prompts
│   └── tools.py          # Tool definitions for the agent
├── memory/               # Memory layer implementations
│   ├── transcripts.py    # Transcript storage + episode spans
│   ├── graph.py          # FalkorDB graph operations
│   ├── themes.py         # Theme layer + heat management
│   └── vectors.py        # Vector store + embedding search
├── core/                 # Shared infrastructure
│   ├── llm.py            # Gemini client (reasoning + embeddings)
│   ├── transcribe.py     # Groq Whisper client
│   └── config.py         # Environment config (.env loading)
├── evals/                # Evaluation framework
│   ├── datasets.py       # Test dataset management
│   └── ragas_eval.py     # RAGAS evaluation runner
├── prompts/              # System prompts (text files)
│   ├── ingest.md         # Ingestion role prompt
│   ├── query.md          # Query role prompt
│   └── memo.md           # Memo role prompt
└── data/                 # Local data (gitignored)
    ├── audio/            # Input audio files
    └── transcripts/      # Stored transcripts
```

## Data Flows

### Ingestion Flow

```
Audio File
    ↓
[Groq Whisper] → Raw Transcript
    ↓
[Transcript Store] → Store with timestamp, get transcript_id
    ↓
[Agent Harness / Ingest Role]
    ↓ (reads full transcript)
    ├── Create/update graph nodes & edges (FalkorDB)
    ├── Write episode spans back to transcript record
    ├── Generate embeddings for episodes, node/edge summaries
    └── Store embeddings in vector store
```

### Query Flow

```
User Question
    ↓
[Agent Harness / Query Role]
    ↓ (reads theme map for context)
    ├── Vector search across layers (find relevant nodes, episodes, themes)
    ├── Graph traversal (follow edges from relevant nodes)
    ├── Transcript retrieval (pull raw text for grounding)
    └── Synthesize answer with citations
```

### Memo Flow

```
[Agent Harness / Memo Role]
    ↓ (reads current themes + recent graph activity)
    ├── Identify new patterns across nodes
    ├── Create/update/merge themes
    ├── Adjust heat values
    └── Generate theme embeddings
```

## Build Order (Phase Dependencies)

```
Phase 1: Core + Storage
    └── config, LLM client, transcription, transcript store, FalkorDB graph store
         ↓
Phase 2: Agent Harness + Ingestion
    └── harness loop, ingest role, graph writing tools, episode spans, disambiguation
         ↓
Phase 3: Query Agent + Retrieval
    └── vector store, query role, retrieval tools, hybrid search
         ↓
Phase 4: Theme Layer + Memo Agent
    └── theme store, memo role, heat/salience, theme-as-map
         ↓
Phase 5: Evaluation
    └── RAGAS setup, test datasets, query quality scoring
```

Each phase depends on the previous — cannot query without ingested data, cannot extract themes without a populated graph, cannot evaluate without working queries.

## Anti-Patterns

### 1. Chunking Transcripts Before Agent Sees Them
**Wrong:** Split transcript into chunks, process each independently.
**Why:** Loses the arc of the recording — meaning depends on full context.
**Instead:** Feed full transcript to ingest agent. Episode spans are a side effect, not input.

### 2. Hardcoding Graph Schema
**Wrong:** Define fixed entity types (Person, Place, Event) and relationship types.
**Why:** Bakes in assumptions about what's important. Limits expressiveness.
**Instead:** Let LLM define types freely. Only enforce structural constraints (nodes have summaries, logs, aliases).

### 3. Hardcoding Retrieval Pipeline
**Wrong:** Fixed pipeline: embed query → vector search → rerank → answer.
**Why:** Different queries need different strategies. "How has my relationship with X evolved?" needs graph traversal, not just vector search.
**Instead:** Give agent retrieval tools, let it decide strategy per query.

### 4. Separate Theme Database
**Wrong:** Store themes in a separate system from the graph.
**Why:** Themes reference graph nodes — keeping them separate means broken references.
**Instead:** Themes can be special nodes in FalkorDB or a thin layer that references graph node IDs.

---
*Architecture research for: LLM-powered audio journaling memory system*
*Researched: 2026-03-25*
