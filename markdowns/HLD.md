# LifeOS Architecture

This document defines how LifeOS works as a system. It is intentionally written in plain English, with enough depth to remove ambiguity while keeping the big picture clear.

The goal is not to describe code or schemas. The goal is to describe the architecture decisions that shape behavior, so product and engineering stay aligned as the app evolves.

---

## 1) Purpose and Architectural Direction

LifeOS is a single-user audio journaling system that turns spoken journals into a long-term memory surface.

The architecture is designed for five outcomes:

1. Capture should be effortless and available offline.
2. Processing should convert raw speech into structured memory automatically.
3. Retrieval should work from vague, fragmentary user cues, not precise keywords.
4. The system should preserve provenance and traceability across all derived memory layers.
5. Privacy should be strong by default, while still allowing server-side intelligence.

To support this, LifeOS uses a **client-server architecture with local-first capture**:

- The client handles recording and offline queueing.
- The server performs transcription, memory extraction, graph updates, and retrieval.
- Data is server-readable for processing and encrypted at rest.

This is the chosen path because it is materially easier to build and maintain for temporal graph memory and reliable retrieval across devices, while still preserving an offline-first user experience for capture.

---

## 2) Product Boundaries and Non-Goals

LifeOS is scoped as:

- Single-user only.
- Journal-first capture: one recording equals one journal.
- Fully automatic segmentation and memory extraction.
- Transcript editing is not allowed in V1.
- User-facing output is meaning-focused, not file-list-focused.

LifeOS is explicitly not:

- A productivity manager.
- A task or streak tracker.
- A therapy product.

Open-loop resurfacing logic, safety guardrails, and user-driven metadata correction are intentionally deferred. The architecture keeps room for them later, but they are not part of core V1 behavior.

---

## 3) Big Picture: End-to-End Flow

At a high level, every journal follows the same lifecycle:

1. User records offline or online on the client.
2. Client stores the recording locally and queues it if offline.
3. When online, the client uploads the recording to the server.
4. Server transcribes audio with timestamps.
5. Transcript is treated as canonical truth.
6. Server derives higher memory layers from transcript:
   - Episode units (fewer, larger units)
   - Topic threads (including non-adjacent span reconnection, such as A -> B -> A)
   - Metadata extraction
   - Session summary
   - Temporal graph updates
   - Stable memory updates
7. Retrieval indexes are updated from these derived layers.
8. User can explore results in:
   - A chronological journal view
   - A cluster-oriented view

Processing is incremental and per-journal. The system updates memory after every journal, not in coarse periodic batches.

---

## 4) Core Conceptual Layers

LifeOS memory is organized into a layered model:

### Layer 0: Raw Audio

- Original recording file for each journal.
- Retained permanently unless manually deleted.
- Exists as the capture artifact and audit anchor.

### Layer 1: Transcript (Canonical Source of Truth)

- Timestamped transcript derived from audio.
- Contains segment/sentence-level timing suitable for simple citations.
- All higher layers are derived from transcript, not from each other.

### Layer 2: Episodes and Topic Threads

- Journal content is reorganized into fewer, larger episode units.
- Episode boundaries are automatic and topic-shift driven.
- If confidence is low, system prefers fewer larger units over forced granular splitting.
- Topic thread logic reconnects non-contiguous spans when the same topic returns later in the same journal or across journals.

This layer is the bridge between raw language and memory structure.

### Layer 3: Temporal Graph Memory (Backend-Facing)

- Stores extracted entities, themes, emotional context, unresolved tensions, and cross-episode links.
- Supports multiple edge types between the same pair of nodes.
- Supports directional edges when useful for retrieval and reasoning.
- Uses temporal behavior: facts can become outdated or superseded rather than simply overwritten.

This is the deep memory substrate for agentic graph retrieval.

### Layer 4: Stable Small Memory

- Compact, explicit long-lived memory derived over time.
- Updated by LLM processing after each journal.
- Holds durable context about recurring people, projects, and patterns.
- Exists as explicit stored records, not on-demand-only recomputation.

This layer provides stable context for retrieval and future model reasoning.

---

## 5) Journal Processing Architecture

### 5.1 Capture and Ingestion

- One recording always maps to one journal.
- Client stores local capture first.
- Upload and processing can happen later when connectivity is available.

### 5.2 Transcription

- Server transcribes audio to timestamped text.
- Transcript is immutable in V1 from the user’s perspective.
- Transcript becomes the canonical data source for all downstream memory work.

### 5.3 Episode Construction

- LLM-based pass transforms transcript into fewer, larger episodes.
- System detects topic shifts while allowing return-to-topic patterns.
- Topic-threading links rejoin same-topic spans that are not adjacent.

The objective is structural coherence, not maximal segmentation granularity.

### 5.4 Metadata Extraction

Required metadata per episode:

- Capture time and journal reference
- Transcript citations (span/timestamp references)
- Themes/topics
- Emotion/tone labels (discrete labels)
- Confidence scores on extracted model outputs

Optional metadata per episode:

- Learnings
- Open questions
- Other higher-order interpretations

Theme behavior:

- Themes are open-ended labels.
- Extraction pass receives existing known themes and can either match or create new labels.

Entity behavior:

- When person/entity mapping is uncertain, system force-matches to best existing entity (no provisional unresolved entity in V1).

### 5.5 Summary Generation

- System produces a one-shot session summary after processing.
- Summary is episode-derived and tied back to transcript evidence.
- Summary is a user-facing synthesis, not a replacement for primary memory layers.

### 5.6 Graph and Stable Memory Updates

- Temporal graph is updated after each processed journal.
- Stable small memory is updated after each processed journal.
- No periodic global reprocessing in V1.

---

## 6) Retrieval Architecture

Retrieval is designed around uncertainty and partial recall.

### 6.1 Query Entry

- Primary entry point is free-text search.
- User starts broadly; system narrows in guided steps.

### 6.2 Retrieval Behavior

System retrieval combines signals from:

- Transcript content
- Episode structure and topic threads
- Temporal graph relationships
- Stable memory context

This is treated as a single unified memory system from a product perspective, even if internally represented with multiple retrieval strategies.

### 6.3 Response and Evidence

- Default responses prioritize concise meaning.
- Citation details appear only when user expands.
- Simple citation granularity (segment/sentence with timestamps) is preferred to keep implementation simple and reliable.

### 6.4 Low-Confidence Handling

- When confidence is low, system asks clarifying follow-up questions instead of pretending certainty.

This behavior supports the retrieval-success goal better than forced answers.

---

## 7) User-Facing Information Architecture

LifeOS exposes two primary exploration surfaces:

### 7.1 Chronological Journal View

- Timeline of journals and their summaries.
- Supports grounded reflection over time.

### 7.2 Cluster View

- Intuitive thematic grouping derived from episode/topic relationships.
- Designed to help users navigate meaning, not graph topology.

The backend graph remains an internal memory substrate; users interact with clusters, themes, and narrative organization rather than explicit node-edge mechanics.

---

## 8) Provenance, Traceability, and Lifecycle Integrity

A core architectural requirement is that every derived artifact can be traced back to source.

### 8.1 Event-Sourced Memory Evolution

- Derived memory changes are appended as events rather than silently replacing history.
- This preserves a historical trail for debugging, trust, and future product features.
- User-facing reproducibility of old answers is not a V1 goal, but system traceability is still maintained.

### 8.2 Derivation Lineage

Every derived object should carry lineage references to:

- Journal
- Transcript revision
- Processing pass

This enables deterministic cleanup and re-derivation.

### 8.3 Deletion Semantics (Hard Delete)

If a user deletes a journal, deletion cascades across all memory layers:

- Raw audio
- Transcript
- Episodes
- Metadata
- Graph edges/nodes derived from that journal
- Stable memory contributions attributable to that journal
- Retrieval indexes/caches derived from that content

Deletion should be architecturally first-class, not an afterthought.

---

## 9) Future-Proofing for Transcript Editing

Transcript editing is not available now, but groundwork is intentionally set.

If transcript editing is added later:

1. A new transcript revision is created (old revision remains in event history).
2. All dependent layers are re-derived from the updated transcript revision.
3. Invalidated derivations from prior revision are retired cleanly.
4. Retrieval indexes are refreshed for affected content.

Because all higher layers are transcript-derived and lineage-linked, this change remains manageable instead of destabilizing the memory system.

---

## 10) Privacy and Security Posture

Selected posture for V1:

- Client-server processing model.
- Server-readable data for model processing.
- Encryption at rest on server.
- No journal-level exclusion controls in V1.
- No special safety guardrail system in V1.

This posture favors delivery speed and retrieval quality while maintaining baseline privacy protections and clear deletion behavior.

---

## 11) Architectural Choices That Keep V1 Minimal

The architecture is intentionally narrow in scope:

- No manual metadata editing.
- No manual episode manipulation.
- No user-curated graph editing.
- No periodic full-memory reinterpretation.
- No proactive open-loop resurfacing logic yet.
- No model transparency UI in V1.

Despite this, the core architecture still supports strong retrieval and durable memory because it preserves source truth, traceability, temporal graph updates, and stable-memory accumulation.

---

## 12) Success Criteria and What This Architecture Optimizes

Primary success metric: **retrieval success rate**.

This architecture optimizes retrieval success by:

1. Structuring speech into topic-coherent units.
2. Linking non-contiguous topic returns through threads.
3. Preserving temporal, relational, and emotional context.
4. Maintaining stable long-term memory alongside episodic details.
5. Providing evidence on demand without cluttering initial responses.
6. Using clarifying follow-up when confidence is low.

The intended user outcome is simple: the system should reliably help users find and understand their own past thinking, even when they only remember fragments.
