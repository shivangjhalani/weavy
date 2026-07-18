# LoCoMo benchmark — summary

## Configuration

- **run_id**: 20260718-102256
- **system**: weavy
- **dataset**: locomo
- **n_conversations**: 3
- **n_questions**: 45
- **granularity**: session
- **themes**: True
- **caller_context**: True
- **langfuse**: False
- **llm_model**: gpt-4o-mini
- **embedding_model**: text-embedding-3-small
- **judge_model**: gpt-4o-mini
- **ingest_workers**: 3
- **query_workers**: 8

## Accuracy by category (LLM-judge / J score)

| Category | Accuracy | n |
|---|---|---|
| multi_hop | 33.3% | 15 |
| temporal | 8.3% | 24 |
| open_domain | 50.0% | 4 |
| single_hop | 50.0% | 2 |
| **overall (recall)** | **22.2%** | 45 |

## Efficiency

- **Answer tokens / question**: 34300.8
- **Ingest tokens (total)**: 1,303,953
- **Answer latency**: p50 8455.2 ms · p95 31735.3 ms
- **Cost (USD)**: ingest $0.2192 · answer $0.2357 · judge $0.0018 · **total $0.4567**

## Published reference lines

> Self-reported, run on different harnesses/SDK versions. Treat as fuzzy context (±10pts is normal for this benchmark), not head-to-head.

| System | Metric | Score | Source |
|---|---|---|---|
| Mem0 | LLM-judge (J), overall | ~66.9 | Mem0 paper (arXiv:2504.19413) |
| Mem0g (graph) | LLM-judge (J), overall | ~68.4 | Mem0 paper (arXiv:2504.19413) |
| Zep | LLM-judge (J), overall | 58.4 – 75.1 (disputed) | Zep blog / getzep zep-papers Issue #5 |
| LangMem | LLM-judge (J), overall | ~58 | Mem0 paper (arXiv:2504.19413) |
| OpenAI Memory | LLM-judge (J), overall | ~52 | Mem0 paper (arXiv:2504.19413) |
