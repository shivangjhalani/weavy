# LoCoMo benchmark — summary

## Configuration

- **run_id**: 20260718-124526
- **system**: weavy
- **dataset**: locomo
- **n_conversations**: 3
- **n_questions**: 497
- **granularity**: session
- **themes**: False
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
| multi_hop | 17.6% | 74 |
| temporal | 30.0% | 90 |
| open_domain | 23.8% | 21 |
| single_hop | 50.0% | 200 |
| **overall (recall)** | **37.7%** | 385 |
| _adversarial (abstention)_ | 52.7% | 112 |

## Efficiency

- **Answer tokens / question**: 21361.0
- **Ingest tokens (total)**: 1,416,742
- **Answer latency**: p50 6663.2 ms · p95 15947.5 ms
- **Cost (USD)**: ingest $0.2428 · answer $1.6272 · judge $0.019 · **total $1.8891**

## Published reference lines

> Self-reported, run on different harnesses/SDK versions. Treat as fuzzy context (±10pts is normal for this benchmark), not head-to-head.

| System | Metric | Score | Source |
|---|---|---|---|
| Mem0 | LLM-judge (J), overall | ~66.9 | Mem0 paper (arXiv:2504.19413) |
| Mem0g (graph) | LLM-judge (J), overall | ~68.4 | Mem0 paper (arXiv:2504.19413) |
| Zep | LLM-judge (J), overall | 58.4 – 75.1 (disputed) | Zep blog / getzep zep-papers Issue #5 |
| LangMem | LLM-judge (J), overall | ~58 | Mem0 paper (arXiv:2504.19413) |
| OpenAI Memory | LLM-judge (J), overall | ~52 | Mem0 paper (arXiv:2504.19413) |
