# LoCoMo benchmark — summary

## Configuration

- **run_id**: 20260718-130627
- **system**: weavy
- **dataset**: locomo
- **n_conversations**: 3
- **n_questions**: 497
- **granularity**: session
- **themes**: True
- **caller_context**: True
- **langfuse**: True
- **llm_model**: gpt-4o-mini
- **embedding_model**: text-embedding-3-small
- **judge_model**: gpt-4o-mini
- **ingest_workers**: 10
- **query_workers**: 16

## Accuracy by category (LLM-judge / J score)

| Category | Accuracy | n |
|---|---|---|
| multi_hop | 20.3% | 74 |
| temporal | 35.6% | 90 |
| open_domain | 23.8% | 21 |
| single_hop | 59.5% | 200 |
| **overall (recall)** | **44.4%** | 385 |
| _adversarial (abstention)_ | 56.2% | 112 |

## Efficiency

- **Answer tokens / question**: 21983.1
- **Ingest tokens (total)**: 1,838,179
- **Answer latency**: p50 6733.7 ms · p95 17106.1 ms
- **Cost (USD)**: ingest $0.3035 · answer $1.6774 · judge $0.0192 · **total $2.0001**

## Published reference lines

> Self-reported, run on different harnesses/SDK versions. Treat as fuzzy context (±10pts is normal for this benchmark), not head-to-head.

| System | Metric | Score | Source |
|---|---|---|---|
| Mem0 | LLM-judge (J), overall | ~66.9 | Mem0 paper (arXiv:2504.19413) |
| Mem0g (graph) | LLM-judge (J), overall | ~68.4 | Mem0 paper (arXiv:2504.19413) |
| Zep | LLM-judge (J), overall | 58.4 – 75.1 (disputed) | Zep blog / getzep zep-papers Issue #5 |
| LangMem | LLM-judge (J), overall | ~58 | Mem0 paper (arXiv:2504.19413) |
| OpenAI Memory | LLM-judge (J), overall | ~52 | Mem0 paper (arXiv:2504.19413) |
