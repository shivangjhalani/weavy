<!-- GSD:project-start source:PROJECT.md -->
## Project

**LifeOS**

LifeOS is an audio journaling backend — the memory engine that powers a system where users speak their thoughts and the system remembers. You record, it transcribes (Whisper via Groq), an LLM agent builds an evolving semantic graph of your inner life (FalkorDB), and you can query that graph conversationally. This project is the backend core: memory layers, agent harness, and evaluation — no UI, no API, just runnable Python scripts for experimentation.

**Core Value:** The memory system must faithfully capture, organize, and retrieve a person's evolving inner life from spoken transcripts — without imposing rigid schemas or losing nuance over time.

### Constraints

- **Tech stack**: Python, FalkorDB, Gemini 2.5 Flash, Groq Whisper, gemini-embedding-001 — these are decided
- **Environment**: NixOS + devenv — no global package managers, use uv for Python
- **No rigid schema**: The graph schema must NOT be hardcoded — LLM defines node types, edge types, and all semantic structure
- **Transcript primacy**: Raw transcripts are the only canonical record; everything else is derived and reconstructable
- **Single agent harness**: One harness with role-specific prompts, not separate agent implementations
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Recommended Stack
### Core Technologies (Already Installed)
| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| falkordb | 1.6.0 | Graph + vector storage | Already in devenv, Redis-compatible, native vector index support, Cypher queries |
| google-genai | 1.68.0 | LLM reasoning + embeddings | Gemini 2.5 Flash via native SDK, full function calling support |
| litellm | 1.82.4 | Groq Whisper transcription | Unified API for Groq Whisper calls |
| ragas | 0.4.3 | Query quality evaluation | Established RAG evaluation framework — faithfulness, relevance, groundedness |
| pydantic | 2.12.5 | Data models | Type-safe node/edge/transcript models |
### Supporting Libraries
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-dotenv | installed | .env loading | Config management for API keys |
| pyyaml | 6.0.3 | Config files | Prompt templates and settings |
### Development Tools
| Tool | Purpose | Notes |
|------|---------|-------|
| uv | Python package management | NixOS requirement — fast, reliable |
| ruff | Linting + formatting | NixOS requirement |
| devenv | Environment management | FalkorDB Docker defined here |
## Key Findings
### Drop ChromaDB
### Drop Chonkie
### No Agent Framework Needed
## What NOT to Use
| Avoid | Why | Use Instead |
|-------|-----|-------------|
| ChromaDB / Pinecone / Weaviate | FalkorDB has native vector indexes — separate vector DB adds complexity | FalkorDB vector indexes |
| LangChain / LangGraph for agent logic | Over-abstraction for a single-harness design; google-genai has native function calling | google-genai function calling |
| Chonkie / text chunkers | Architecture explicitly avoids chunking — full transcript to agent | Feed full transcript to LLM |
| SpaCy / fixed NER pipelines | Contradicts LLM-defined schema philosophy | Let Gemini extract entities freely |
## Verification Notes
- FalkorDB Docker `latest` tag — confirm vector index is available in pulled image version
- `google-genai` 1.x tool definition: use `types.Tool` + `types.FunctionDeclaration`, not legacy dict format
- RAGAS 0.4.x requires manual LLM config to use Gemini instead of OpenAI default
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
