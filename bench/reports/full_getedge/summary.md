# LoCoMo benchmark — summary

## Configuration

- **run_id**: 20260627-150201
- **system**: weavy
- **dataset**: locomo
- **n_conversations**: 10
- **n_questions**: 1986
- **granularity**: session
- **themes**: True
- **caller_context**: True
- **langfuse**: False
- **llm_model**: gpt-4o-mini
- **embedding_model**: text-embedding-3-small
- **judge_model**: gpt-4o-mini
- **ingest_workers**: 10
- **query_workers**: 16

## Accuracy by category (LLM-judge / J score)

| Category | Accuracy | n |
|---|---|---|
| multi_hop | 28.0% | 282 |
| temporal | 19.6% | 321 |
| open_domain | 22.9% | 96 |
| single_hop | 31.5% | 841 |
| **overall (recall)** | **27.9%** | 1540 |
| _adversarial (abstention)_ | 73.1% | 446 |

## Efficiency

- **Answer tokens / question**: 42739.6
- **Ingest tokens (total)**: 6,313,189
- **Answer latency**: p50 11966.8 ms · p95 46153.7 ms
- **Cost (USD)**: ingest $1.0483 · answer $12.9379 · judge $0.076 · **total $14.0623**

## Published reference lines

> Self-reported, run on different harnesses/SDK versions. Treat as fuzzy context (±10pts is normal for this benchmark), not head-to-head.

| System | Metric | Score | Source |
|---|---|---|---|
| Mem0 | LLM-judge (J), overall | ~66.9 | Mem0 paper (arXiv:2504.19413) |
| Mem0g (graph) | LLM-judge (J), overall | ~68.4 | Mem0 paper (arXiv:2504.19413) |
| Zep | LLM-judge (J), overall | 58.4 – 75.1 (disputed) | Zep blog / getzep zep-papers Issue #5 |
| LangMem | LLM-judge (J), overall | ~58 | Mem0 paper (arXiv:2504.19413) |
| OpenAI Memory | LLM-judge (J), overall | ~52 | Mem0 paper (arXiv:2504.19413) |
