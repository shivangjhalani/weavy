## Episode Segmentation Evaluation Plan (Ragas + LiteLLM, Gemini 2.5/3 Flash)

### Summary
- Build a new, standalone eval pipeline (ignore `experiments-old` entirely) for transcript-to-episode segmentation.
- Use your Whisper JSONs in `private/transcripts/*.json` as source data (17 files, 637 total segments from current corpus scan).
- Create heavy pseudo-gold labels using an LLM labeling agent, then run systematic experiments comparing segmentation strategies and Gemini model variants via LiteLLM.
- Use Ragas for experiment orchestration + LLM-judge metrics, plus deterministic boundary metrics for objective scoring.

### Interfaces and Data Contracts
- Add normalized transcript dataset (JSONL): `private/evals/episode_segmentation/datasets/transcripts_normalized.jsonl`
- Add gold labels dataset (JSONL): `private/evals/episode_segmentation/datasets/gold_episodes_llm.jsonl`
- Add predictions per run (JSONL): `private/evals/episode_segmentation/runs/<run_id>/predictions.jsonl`
- Add evaluation rows for Ragas (JSONL): `private/evals/episode_segmentation/runs/<run_id>/ragas_samples.jsonl`
- Add leaderboard/report (CSV + JSON): `private/evals/episode_segmentation/reports/`

Required record shapes:
- `TranscriptRecord`: `journal_id`, `source_file`, `duration_sec`, `language`, `full_text`, `segments[]`
- `Segment`: `segment_id`, `start_sec`, `end_sec`, `text`, `avg_logprob`, `no_speech_prob`
- `Episode`: `episode_id`, `start_segment_id`, `end_segment_id`, `start_sec`, `end_sec`, `theme`, `title`, `summary`, `thread_key`, `confidence`
- `GoldRecord`: `journal_id`, `episodes[]`, `label_model`, `prompt_version`, `label_timestamp`

### Dataset Preparation Workflow
1. Parse Whisper JSONs from `private/transcripts`.
2. Normalize segment data from `segments[]` (not only root `text`), drop empty segments, preserve timestamps.
3. Build one `TranscriptRecord` per journal with stable `journal_id` from filename.
4. Generate heavy pseudo-gold labels with LLM agent for all transcripts.
5. Run LLM-based QA pass on gold labels to enforce constraints:
- Full coverage of segments exactly once.
- No gaps, no overlaps, no out-of-range segment ids.
- Episode is one coherent major theme.
- Variable episode size allowed (no fixed min/max).
6. Save gold dataset + quality flags.

### Gold Labeling Prompt (for your lightweight LLM agent)
```text
You are labeling audio-journal transcripts into EPISODES.

Goal:
Segment each journal into 1 or more contiguous episodes.
Each episode must represent one coherent major topic/theme.
Episode length is variable; no fixed min/max.
If a journal is clearly single-theme, return one episode.

Input:
- journal_id
- ordered segments: [{segment_id, start_sec, end_sec, text}]

Output:
Return STRICT JSON with this schema:
{
  "journal_id": "<string>",
  "episodes": [
    {
      "episode_id": "E1",
      "start_segment_id": <int>,
      "end_segment_id": <int>,
      "start_sec": <number>,
      "end_sec": <number>,
      "theme": "<2-6 words>",
      "title": "<short human-readable title>",
      "summary": "<1-2 sentence summary grounded in covered segments>",
      "thread_key": "<stable topic key; reuse if this topic reappears later>",
      "confidence": <0.0-1.0>
    }
  ],
  "notes": "<short note on hard boundary decisions>"
}

Hard constraints:
1) Episodes must be contiguous and in order.
2) Every segment must belong to exactly one episode.
3) No overlap, no gaps.
4) start_segment_id/end_segment_id must map to provided segments.
5) Do not invent facts not present in transcript.
6) Boundaries should align to topic shifts, not sentence grammar alone.
7) If a topic returns later, create a new episode but reuse thread_key.

Boundary quality guidance:
- Split when the speaker clearly changes subject/intent/problem space.
- Do NOT split for minor tangent unless it persists.
- Prefer fewer, coherent episodes over fragmented micro-splits.

Return only valid JSON, no markdown.
```

### Experiment Matrix
Run each config on full dataset:

Baselines:
- `B1`: single-episode baseline (whole transcript = one episode)
- `B2`: fixed-window baseline (e.g., every N segments / fixed time)

LLM segmenters (LiteLLM only):
- `S1`: direct segmentation prompt (balanced)
- `S2`: conservative prompt (fewer/larger episodes)
- `S3`: hierarchical segmentation (chunk long transcripts, then merge boundaries)

Model policy:
- Segmenter model: Gemini 2.5 Flash only (via LiteLLM `gemini/...`)
- Gemini 3.0 is not used for segmentation

Judge variants:
- Primary judge: Gemini 3.0 Flash
- Sensitivity run: Gemini 2.5 Flash judge

Total recommended runs:
- 5 prediction runs: `B1`, `B2`, `S1`, `S2`, `S3`
- 10 eval passes total:
  - 5 with primary judge (3.0)
  - 5 with sensitivity judge (2.5)

### Metrics and Scoring
Deterministic (non-LLM):
- Boundary Precision/Recall/F1 (tolerance ±1 segment)
- Boundary Precision/Recall/F1 (tolerance ±10 seconds)
- Episode count error (absolute)
- Partition validity rate (coverage/no-overlap)
- Segment-weighted IoU against gold spans

Ragas LLM metrics (SingleTurnSample-based):
- `RubricsScore`: topic-match quality vs gold (1-5 rubric)
- `AspectCritic`: single-topic coherence (binary)
- `AspectCritic`: summary/theme grounded in episode text (binary)
- `DiscreteMetric`: boundary naturalness (0/1/2) using local left/right context

Aggregate ranking:
- Primary rank by boundary F1 (±1 seg), tie-break by rubric topic-match mean, then coherence.

### Implementation Constraints
- All model calls must go through LiteLLM.
- For Ragas LLM usage, initialize with LiteLLM client (not provider SDK directly), e.g. `llm_factory(..., provider="litellm", client=litellm.completion)`.
- Keep Gemini models with `gemini/` prefix to avoid accidental Vertex routing.
- Keep `litellm.drop_params=True`; verify provider/model support with `get_supported_openai_params(...)`.

### Test Plan
- Parser tests for Whisper JSON normalization (including empty segment handling).
- Gold-label validator tests (coverage, overlap, ordering).
- Prompt-output schema tests (strict JSON parse + required fields).
- One-transcript smoke run for each segmenter strategy.
- End-to-end run on all transcripts with report generation.
- Reproducibility check at `temperature=0` for deterministic configs.

### Assumptions and Defaults
- `experiments-old` remains fully excluded.
- Heavy gold labeling is LLM-generated + LLM-QA (not manual human labels).
- Default optimization target is Gemini 2.5 Flash and Gemini 3 Flash (LiteLLM Gemini provider).
- If local env still lacks `ragas` import, first run environment sync before execution.
- Existing Whisper format is trusted: root `text/duration/language/task` + `segments[{id,start,end,text,...}]`.

### Source Docs
- Ragas experimentation: https://docs.ragas.io/en/stable/concepts/experimentation/
- Ragas evaluation dataset: https://docs.ragas.io/en/stable/concepts/components/eval_dataset/
- Ragas schema (SingleTurnSample fields): https://docs.ragas.io/en/stable/references/evaluation_schema/
- Ragas model customization with LiteLLM: https://docs.ragas.io/en/stable/howtos/customizations/customize_models/
- LiteLLM Gemini provider: https://docs.litellm.ai/docs/providers/gemini
- LiteLLM completion params (`response_format`, `drop_params`): https://docs.litellm.ai/docs/completion/input
