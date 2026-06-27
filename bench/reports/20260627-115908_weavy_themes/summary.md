# LoCoMo benchmark — summary

## Configuration

- **run_id**: 20260627-115908
- **system**: weavy
- **dataset**: locomo
- **n_conversations**: 1
- **n_questions**: 5
- **granularity**: session
- **themes**: True
- **caller_context**: True
- **langfuse**: True
- **llm_model**: gpt-4o-mini
- **embedding_model**: text-embedding-3-small
- **judge_model**: gpt-4o-mini
- **workers**: 10

## Accuracy by category (LLM-judge / J score)

| Category | Accuracy | n |
|---|---|---|
| multi_hop | 100.0% | 2 |
| temporal | 0.0% | 2 |
| open_domain | 100.0% | 1 |
| **overall (recall)** | **60.0%** | 5 |

## Efficiency

- **Answer tokens / question**: 31370.0
- **Ingest tokens (total)**: 385,486
- **Answer latency**: p50 7943.7 ms · p95 13655.7 ms
- **Cost (USD)**: ingest $0.065 · answer $0.024 · judge $0.0002 · **total $0.0892**

## Published reference lines

> Self-reported, run on different harnesses/SDK versions. Treat as fuzzy context (±10pts is normal for this benchmark), not head-to-head.

| System | Metric | Score | Source |
|---|---|---|---|
| Mem0 | LLM-judge (J), overall | ~66.9 | Mem0 paper (arXiv:2504.19413) |
| Mem0g (graph) | LLM-judge (J), overall | ~68.4 | Mem0 paper (arXiv:2504.19413) |
| Zep | LLM-judge (J), overall | 58.4 – 75.1 (disputed) | Zep blog / getzep zep-papers Issue #5 |
| LangMem | LLM-judge (J), overall | ~58 | Mem0 paper (arXiv:2504.19413) |
| OpenAI Memory | LLM-judge (J), overall | ~52 | Mem0 paper (arXiv:2504.19413) |
