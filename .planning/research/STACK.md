# Stack Research

**Domain:** LLM-powered audio journaling memory system (backend)
**Researched:** 2026-03-25
**Confidence:** HIGH (verified against existing pyproject.toml + uv.lock)

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
FalkorDB has native vector index support. Storing vectors in FalkorDB enables hybrid vector+graph queries in a single Cypher statement — no separate vector DB needed.

### Drop Chonkie
The architecture has the ingestion agent read full transcripts — there is no chunking step. Chonkie solves a problem this project explicitly avoids.

### No Agent Framework Needed
`google-genai` 1.68.0 has full native function calling. The single-harness design is ~50 lines of Python. LangGraph/LangChain are transitive deps from RAGAS — don't build logic on them.

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

---
*Stack research for: LLM-powered audio journaling memory system*
*Researched: 2026-03-25*
