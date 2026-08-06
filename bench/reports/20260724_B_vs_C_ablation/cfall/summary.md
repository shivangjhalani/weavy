# LoCoMo benchmark — summary

## Configuration

- **run_id**: 20260723-194141
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
| multi_hop | 36.5% | 74 |
| temporal | 46.7% | 90 |
| open_domain | 33.3% | 21 |
| single_hop | 55.5% | 200 |
| **overall (recall)** | **48.6%** | 385 |
| _adversarial (abstention)_ | 38.4% | 112 |

## Efficiency

- **Answer tokens / question**: 31047.0
- **Ingest tokens (total)**: 0
- **Answer latency**: p50 7878.9 ms · p95 19601.8 ms
- **Cost (USD)**: ingest $0.0 · answer $2.3593 · judge $0.0194 · **total $2.3787**

## Published reference lines

> Self-reported, run on different harnesses/SDK versions. Treat as fuzzy context (±10pts is normal for this benchmark), not head-to-head.

| System | Metric | Score | Source |
|---|---|---|---|
| Mem0 | LLM-judge (J), overall | ~66.9 | Mem0 paper (arXiv:2504.19413) |
| Mem0g (graph) | LLM-judge (J), overall | ~68.4 | Mem0 paper (arXiv:2504.19413) |
| Zep | LLM-judge (J), overall | 58.4 – 75.1 (disputed) | Zep blog / getzep zep-papers Issue #5 |
| LangMem | LLM-judge (J), overall | ~58 | Mem0 paper (arXiv:2504.19413) |
| OpenAI Memory | LLM-judge (J), overall | ~52 | Mem0 paper (arXiv:2504.19413) |
