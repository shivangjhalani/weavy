# LoCoMo benchmark — summary

## Configuration

- **run_id**: 20260723-192507
- **system**: weavy
- **dataset**: locomo
- **n_conversations**: 3
- **n_questions**: 497
- **granularity**: session
- **themes**: True
- **caller_context**: True
- **langfuse**: False
- **llm_model**: gpt-4o-mini
- **embedding_model**: text-embedding-3-small
- **judge_model**: gpt-4o-mini
- **ingest_workers**: 10
- **query_workers**: 6

## Accuracy by category (LLM-judge / J score)

| Category | Accuracy | n |
|---|---|---|
| multi_hop | 31.1% | 74 |
| temporal | 34.4% | 90 |
| open_domain | 38.1% | 21 |
| single_hop | 51.5% | 200 |
| **overall (recall)** | **42.9%** | 385 |
| _adversarial (abstention)_ | 41.1% | 112 |

## Efficiency

- **Answer tokens / question**: 42022.5
- **Ingest tokens (total)**: 0
- **Answer latency**: p50 8250.1 ms · p95 23455.3 ms
- **Cost (USD)**: ingest $0.0 · answer $3.1833 · judge $0.0193 · **total $3.2026**

## Published reference lines

> Self-reported, run on different harnesses/SDK versions. Treat as fuzzy context (±10pts is normal for this benchmark), not head-to-head.

| System | Metric | Score | Source |
|---|---|---|---|
| Mem0 | LLM-judge (J), overall | ~66.9 | Mem0 paper (arXiv:2504.19413) |
| Mem0g (graph) | LLM-judge (J), overall | ~68.4 | Mem0 paper (arXiv:2504.19413) |
| Zep | LLM-judge (J), overall | 58.4 – 75.1 (disputed) | Zep blog / getzep zep-papers Issue #5 |
| LangMem | LLM-judge (J), overall | ~58 | Mem0 paper (arXiv:2504.19413) |
| OpenAI Memory | LLM-judge (J), overall | ~52 | Mem0 paper (arXiv:2504.19413) |
