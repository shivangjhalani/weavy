# LoCoMo benchmark — summary

## Configuration

- **run_id**: 20260627-143614
- **system**: weavy
- **dataset**: locomo
- **n_conversations**: 1
- **n_questions**: 199
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
| multi_hop | 18.8% | 32 |
| temporal | 43.2% | 37 |
| open_domain | 30.8% | 13 |
| single_hop | 40.0% | 70 |
| **overall (recall)** | **35.5%** | 152 |
| _adversarial (abstention)_ | 57.5% | 47 |

## Efficiency

- **Answer tokens / question**: 27301.1
- **Ingest tokens (total)**: 457,387
- **Answer latency**: p50 8424.8 ms · p95 24309.7 ms
- **Cost (USD)**: ingest $0.0777 · answer $0.8325 · judge $0.0077 · **total $0.9178**

## Published reference lines

> Self-reported, run on different harnesses/SDK versions. Treat as fuzzy context (±10pts is normal for this benchmark), not head-to-head.

| System | Metric | Score | Source |
|---|---|---|---|
| Mem0 | LLM-judge (J), overall | ~66.9 | Mem0 paper (arXiv:2504.19413) |
| Mem0g (graph) | LLM-judge (J), overall | ~68.4 | Mem0 paper (arXiv:2504.19413) |
| Zep | LLM-judge (J), overall | 58.4 – 75.1 (disputed) | Zep blog / getzep zep-papers Issue #5 |
| LangMem | LLM-judge (J), overall | ~58 | Mem0 paper (arXiv:2504.19413) |
| OpenAI Memory | LLM-judge (J), overall | ~52 | Mem0 paper (arXiv:2504.19413) |
