#!/usr/bin/env python3
"""Throwaway experimental pipeline for episode segmentation evaluation.

This script intentionally optimizes for speed of iteration, not production rigor.
It ignores `experiments-old` and only works off private/transcripts/*.json.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TRANSCRIPTS_DIR = PROJECT_ROOT / "private" / "transcripts"
DEFAULT_EVAL_ROOT = PROJECT_ROOT / "private" / "evals" / "episode_segmentation"
DEFAULT_DATASETS_DIR = DEFAULT_EVAL_ROOT / "datasets"
DEFAULT_RUNS_DIR = DEFAULT_EVAL_ROOT / "runs"
DEFAULT_REPORTS_DIR = DEFAULT_EVAL_ROOT / "reports"

SEGMENTER_STRATEGIES = ("B1", "B2", "S1", "S2", "S3")

GOLD_LABEL_PROMPT = """You are labeling audio-journal transcripts into EPISODES.

Goal:
Segment each journal into 1 or more contiguous episodes.
Each episode must represent one coherent major topic/theme.
Episode length is variable; no fixed min/max.
If a journal is clearly single-theme, return one episode.

Input:
- journal_id
- ordered segments: [{segment_id, start_sec, end_sec, text}]

Output:
Return STRICT JSON:
{
  "journal_id": "<string>",
  "episodes": [
    {
      "episode_id": "E1",
      "start_segment_id": <int>,
      "end_segment_id": <int>,
      "theme": "<2-6 words>",
      "title": "<short title>",
      "summary": "<1-2 sentence summary>",
      "thread_key": "<stable topic key>",
      "confidence": <0.0-1.0>
    }
  ],
  "notes": "<short note>"
}

Hard constraints:
1) Episodes contiguous and in order
2) Every segment belongs to exactly one episode
3) No overlap, no gaps
4) No made-up facts
5) If topic returns later, create new episode but reuse thread_key
"""

S1_PROMPT = """Segment this transcript into episodes.
Balanced mode:
- split on major topic shift
- avoid tiny fragments
- one episode per coherent major theme
- return strict JSON like {"episodes":[...]} with fields ONLY:
  end_segment_id, theme
- keep `theme` short (2-6 words)
- episodes must cover all segments in order from 0 to max segment id exactly once
- end_segment_id values must be strictly increasing
- last end_segment_id must equal max segment id
"""

S2_PROMPT = """Segment this transcript into episodes.
Conservative mode:
- prefer fewer, larger episodes
- only split on very clear sustained topic shift
- return strict JSON like {"episodes":[...]} with fields ONLY:
  end_segment_id, theme
- keep `theme` short (2-6 words)
- episodes must cover all segments in order from 0 to max segment id exactly once
- end_segment_id values must be strictly increasing
- last end_segment_id must equal max segment id
"""

RUBRICS_TOPIC_MATCH = {
    "score1_description": "Predicted episode topic is wrong and does not match the reference.",
    "score2_description": "Predicted episode topic weakly matches reference but misses core meaning.",
    "score3_description": "Predicted topic mostly matches reference with noticeable omissions.",
    "score4_description": "Predicted topic closely matches reference with minor issues.",
    "score5_description": "Predicted topic fully matches reference and captures the same major theme.",
}


class EpisodeLLMOut(BaseModel):
    episode_id: str = Field(default="E1")
    start_segment_id: int
    end_segment_id: int
    theme: str = Field(default="unknown", max_length=80)
    title: str = Field(default="")
    summary: str = Field(default="")
    thread_key: str = Field(default="", max_length=120)
    confidence: float = Field(default=0.5)


class EpisodesLLMResponse(BaseModel):
    journal_id: str | None = None
    episodes: list[EpisodeLLMOut]
    notes: str | None = None


class EpisodeBoundaryOut(BaseModel):
    end_segment_id: int
    theme: str = Field(default="unknown", max_length=80)


class EpisodesBoundaryResponse(BaseModel):
    episodes: list[EpisodeBoundaryOut]


def load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env")
    except Exception:
        # Keep this intentionally silent/forgiving for throwaway runs.
        pass


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    ensure_parent(path)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def parse_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except Exception:
        return fallback


def normalize_transcript_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw_segments = raw.get("segments") or []
    normalized_segments: list[dict[str, Any]] = []

    for seg in raw_segments:
        text = str((seg or {}).get("text") or "").strip()
        if not text:
            continue
        seg_id = len(normalized_segments)
        start = parse_float((seg or {}).get("start"), 0.0)
        end = parse_float((seg or {}).get("end"), start)
        if end < start:
            end = start
        normalized_segments.append(
            {
                "segment_id": seg_id,
                "source_segment_id": (seg or {}).get("id"),
                "start_sec": start,
                "end_sec": end,
                "text": text,
                "avg_logprob": (seg or {}).get("avg_logprob"),
                "no_speech_prob": (seg or {}).get("no_speech_prob"),
            }
        )

    if not normalized_segments:
        text = str(raw.get("text") or "").strip()
        if text:
            normalized_segments = [
                {
                    "segment_id": 0,
                    "source_segment_id": 0,
                    "start_sec": 0.0,
                    "end_sec": parse_float(raw.get("duration"), 0.0),
                    "text": text,
                    "avg_logprob": None,
                    "no_speech_prob": None,
                }
            ]

    full_text = " ".join(seg["text"] for seg in normalized_segments).strip()
    try:
        source_file = str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        source_file = str(path)

    return {
        "journal_id": path.stem,
        "source_file": source_file,
        "duration_sec": parse_float(raw.get("duration"), 0.0),
        "language": raw.get("language"),
        "full_text": full_text,
        "segments": normalized_segments,
    }


def normalize_transcripts(input_dir: Path, output_jsonl: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for transcript_path in sorted(input_dir.glob("*.json")):
        rows.append(normalize_transcript_json(transcript_path))
    write_jsonl(output_jsonl, rows)
    return rows


def assert_segmenter_model_policy(segmenter_model: str) -> None:
    lower = segmenter_model.lower()
    if "gemini-3" in lower or "3.0" in lower:
        raise ValueError(
            f"SEGMENTER_MODEL must be Gemini 2.5 Flash only. Got: {segmenter_model}"
        )


def single_episode(segments: list[dict[str, Any]], theme: str = "single topic") -> list[dict[str, Any]]:
    if not segments:
        return []
    return [
        {
            "episode_id": "E1",
            "start_segment_id": 0,
            "end_segment_id": len(segments) - 1,
            "start_sec": segments[0]["start_sec"],
            "end_sec": segments[-1]["end_sec"],
            "theme": theme,
            "title": "Single episode",
            "summary": "",
            "thread_key": theme.lower().replace(" ", "_"),
            "confidence": 1.0,
        }
    ]


def validate_episode_partition(episodes: list[dict[str, Any]], num_segments: int) -> None:
    if num_segments <= 0:
        raise ValueError("Transcript has zero segments.")
    if not episodes:
        raise ValueError("No episodes produced.")

    episodes_sorted = sorted(episodes, key=lambda e: int(e["start_segment_id"]))
    expected_start = 0
    for ep in episodes_sorted:
        start_id = int(ep["start_segment_id"])
        end_id = int(ep["end_segment_id"])
        if start_id != expected_start:
            raise ValueError(f"Gap/overlap detected. expected_start={expected_start}, got={start_id}")
        if end_id < start_id:
            raise ValueError(f"Invalid episode range {start_id}-{end_id}")
        if end_id >= num_segments:
            raise ValueError(f"Episode end out of range: {end_id} >= {num_segments}")
        expected_start = end_id + 1
    if expected_start != num_segments:
        raise ValueError(
            f"Coverage incomplete. covered_until={expected_start - 1}, total={num_segments}"
        )


def normalize_episode_fields(
    raw_episodes: list[dict[str, Any]], segments: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not segments:
        return []
    parsed: list[dict[str, Any]] = []
    max_idx = len(segments) - 1
    for i, ep in enumerate(raw_episodes):
        start_id = int(parse_float(ep.get("start_segment_id"), 0))
        end_id = int(parse_float(ep.get("end_segment_id"), start_id))
        if start_id < 0:
            raise ValueError(f"start_segment_id must be >= 0, got {start_id}")
        if end_id < start_id:
            raise ValueError(f"end_segment_id must be >= start_segment_id, got {start_id}-{end_id}")
        if start_id > max_idx or end_id > max_idx:
            raise ValueError(
                f"episode range out of bounds for {len(segments)} segments: {start_id}-{end_id}"
            )

        parsed.append(
            {
                "episode_id": str(ep.get("episode_id") or f"E{i + 1}"),
                "start_segment_id": start_id,
                "end_segment_id": end_id,
                "start_sec": segments[start_id]["start_sec"],
                "end_sec": segments[end_id]["end_sec"],
                "theme": str(ep.get("theme") or "unknown").strip() or "unknown",
                "title": str(ep.get("title") or f"Episode {i + 1}").strip() or f"Episode {i + 1}",
                "summary": str(ep.get("summary") or "").strip(),
                "thread_key": str(ep.get("thread_key") or "").strip()
                or str(ep.get("theme") or "unknown").strip().lower().replace(" ", "_"),
                "confidence": max(0.0, min(1.0, parse_float(ep.get("confidence"), 0.5))),
            }
        )

    return sorted(parsed, key=lambda e: (e["start_segment_id"], e["end_segment_id"]))


def build_episodes_from_end_boundaries(
    boundaries: list[EpisodeBoundaryOut], segments: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not segments:
        return []
    if not boundaries:
        raise ValueError("No episodes returned by model.")

    max_idx = len(segments) - 1
    expected_start = 0
    episodes: list[dict[str, Any]] = []
    for i, boundary in enumerate(boundaries, start=1):
        end_id = int(boundary.end_segment_id)
        if end_id < expected_start:
            raise ValueError(
                f"end_segment_id must be >= expected_start. expected_start={expected_start}, got={end_id}"
            )
        if end_id > max_idx:
            raise ValueError(f"end_segment_id out of range: {end_id} > {max_idx}")
        theme = str(boundary.theme or "unknown").strip() or "unknown"
        episodes.append(
            {
                "episode_id": f"E{i}",
                "start_segment_id": expected_start,
                "end_segment_id": end_id,
                "start_sec": segments[expected_start]["start_sec"],
                "end_sec": segments[end_id]["end_sec"],
                "theme": theme,
                "title": f"Episode {i}",
                "summary": "",
                "thread_key": theme.lower().replace(" ", "_"),
                "confidence": 0.5,
            }
        )
        expected_start = end_id + 1

    if expected_start != len(segments):
        raise ValueError(
            f"Coverage incomplete from boundaries. covered_until={expected_start - 1}, total={len(segments)}"
        )
    return episodes


def segments_as_prompt_lines(segments: list[dict[str, Any]]) -> str:
    lines = []
    for seg in segments:
        lines.append(f'{seg["segment_id"]}: {seg["text"]}')
    return "\n".join(lines)


def parse_structured_content(content: Any, response_model: Any) -> Any:
    if isinstance(content, str):
        return response_model.model_validate_json(content)
    if isinstance(content, dict):
        return response_model.model_validate(content)
    if isinstance(content, response_model):
        return content
    if hasattr(content, "model_dump"):
        return response_model.model_validate(content.model_dump())
    return response_model.model_validate(content)


def call_litellm_structured(
    model: str,
    messages: list[dict[str, str]],
    response_model: Any,
    temperature: float = 0.0,
    max_tokens: int = 2048,
) -> Any:
    import litellm

    litellm.drop_params = True
    response = litellm.completion(
        model=model,
        messages=messages,
        response_format=response_model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return parse_structured_content(response.choices[0].message.content, response_model)


def llm_segment_transcript(
    transcript: dict[str, Any], model: str, prompt_mode: str
) -> list[dict[str, Any]]:
    segments = transcript["segments"]
    max_segment_id = len(segments) - 1
    if prompt_mode == "gold":
        system_prompt = GOLD_LABEL_PROMPT
    elif prompt_mode == "conservative":
        system_prompt = S2_PROMPT
    else:
        system_prompt = S1_PROMPT

    user_prompt = (
        f"journal_id: {transcript['journal_id']}\n"
        f"max_segment_id: {max_segment_id}\n"
        f"segments:\n{segments_as_prompt_lines(segments)}\n"
        "Return strict JSON only."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    if prompt_mode == "gold":
        structured = call_litellm_structured(
            model=model,
            messages=messages,
            response_model=EpisodesLLMResponse,
            temperature=0.0,
            max_tokens=2048,
        )
        episodes = normalize_episode_fields(
            [episode.model_dump() for episode in structured.episodes], segments
        )
    else:
        structured = call_litellm_structured(
            model=model,
            messages=messages,
            response_model=EpisodesBoundaryResponse,
            temperature=0.0,
            max_tokens=2048,
        )
        episodes = build_episodes_from_end_boundaries(structured.episodes, segments)
    validate_episode_partition(episodes, len(segments))
    return episodes


def strategy_b2(segments: list[dict[str, Any]], chunk_size: int) -> list[dict[str, Any]]:
    if not segments:
        return []
    out: list[dict[str, Any]] = []
    idx = 0
    ep_n = 1
    n = len(segments)
    while idx < n:
        end = min(n - 1, idx + chunk_size - 1)
        out.append(
            {
                "episode_id": f"E{ep_n}",
                "start_segment_id": idx,
                "end_segment_id": end,
                "start_sec": segments[idx]["start_sec"],
                "end_sec": segments[end]["end_sec"],
                "theme": "fixed_window",
                "title": f"Fixed Window {ep_n}",
                "summary": "",
                "thread_key": "fixed_window",
                "confidence": 1.0,
            }
        )
        idx = end + 1
        ep_n += 1
    return out


def merge_adjacent_same_theme(episodes: list[dict[str, Any]], segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not episodes:
        return []
    episodes = sorted(episodes, key=lambda e: e["start_segment_id"])
    merged: list[dict[str, Any]] = [episodes[0].copy()]
    for ep in episodes[1:]:
        last = merged[-1]
        if (
            str(ep.get("theme", "")).strip().lower()
            == str(last.get("theme", "")).strip().lower()
            and ep["start_segment_id"] == last["end_segment_id"] + 1
        ):
            last["end_segment_id"] = ep["end_segment_id"]
            last["end_sec"] = segments[ep["end_segment_id"]]["end_sec"]
            last["summary"] = (last.get("summary") or "").strip()
        else:
            merged.append(ep.copy())
    for i, ep in enumerate(merged, start=1):
        ep["episode_id"] = f"E{i}"
    return merged


def strategy_s3_hierarchical(transcript: dict[str, Any], model: str, chunk_size: int) -> list[dict[str, Any]]:
    segments = transcript["segments"]
    if len(segments) <= chunk_size:
        return llm_segment_transcript(transcript, model=model, prompt_mode="balanced")

    episodes: list[dict[str, Any]] = []
    cursor = 0
    while cursor < len(segments):
        local = segments[cursor : cursor + chunk_size]
        local_transcript = {
            "journal_id": f"{transcript['journal_id']}__chunk_{cursor}",
            "segments": [
                {
                    "segment_id": i,
                    "start_sec": seg["start_sec"],
                    "end_sec": seg["end_sec"],
                    "text": seg["text"],
                }
                for i, seg in enumerate(local)
            ],
        }
        local_episodes = llm_segment_transcript(local_transcript, model=model, prompt_mode="balanced")
        for ep in local_episodes:
            g_start = cursor + int(ep["start_segment_id"])
            g_end = cursor + int(ep["end_segment_id"])
            episodes.append(
                {
                    "episode_id": ep["episode_id"],
                    "start_segment_id": g_start,
                    "end_segment_id": g_end,
                    "start_sec": segments[g_start]["start_sec"],
                    "end_sec": segments[g_end]["end_sec"],
                    "theme": ep.get("theme") or "unknown",
                    "title": ep.get("title") or "",
                    "summary": ep.get("summary") or "",
                    "thread_key": ep.get("thread_key") or "",
                    "confidence": ep.get("confidence") or 0.5,
                }
            )
        cursor += chunk_size

    episodes = merge_adjacent_same_theme(episodes, segments)
    validate_episode_partition(episodes, len(segments))
    return episodes


def run_strategy(
    strategy: str,
    transcript: dict[str, Any],
    segmenter_model: str,
    b2_chunk_size: int,
    s3_chunk_size: int,
) -> list[dict[str, Any]]:
    segments = transcript["segments"]
    if strategy == "B1":
        return single_episode(segments, theme="single_topic_baseline")
    if strategy == "B2":
        return strategy_b2(segments, b2_chunk_size)
    if strategy == "S1":
        return llm_segment_transcript(transcript, model=segmenter_model, prompt_mode="balanced")
    if strategy == "S2":
        return llm_segment_transcript(
            transcript, model=segmenter_model, prompt_mode="conservative"
        )
    if strategy == "S3":
        return strategy_s3_hierarchical(transcript, model=segmenter_model, chunk_size=s3_chunk_size)
    raise ValueError(f"Unknown strategy: {strategy}")


def build_journal_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["journal_id"]: row for row in rows}


def greedy_hits(pred: list[float], gold: list[float], tolerance: float) -> int:
    remaining = set(range(len(gold)))
    hits = 0
    for p in pred:
        candidates = [i for i in remaining if abs(gold[i] - p) <= tolerance]
        if not candidates:
            continue
        best = min(candidates, key=lambda i: abs(gold[i] - p))
        remaining.remove(best)
        hits += 1
    return hits


def f1_with_tolerance(pred: list[float], gold: list[float], tolerance: float) -> float:
    if not pred and not gold:
        return 1.0
    if not pred or not gold:
        return 0.0
    hits = greedy_hits(pred, gold, tolerance)
    precision = hits / len(pred) if pred else 0.0
    recall = hits / len(gold) if gold else 0.0
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def boundaries_segment_ids(episodes: list[dict[str, Any]]) -> list[int]:
    if len(episodes) <= 1:
        return []
    return [int(ep["end_segment_id"]) for ep in episodes[:-1]]


def boundaries_seconds(episodes: list[dict[str, Any]]) -> list[float]:
    if len(episodes) <= 1:
        return []
    return [parse_float(ep["end_sec"], 0.0) for ep in episodes[:-1]]


def overlap_segments(a: dict[str, Any], b: dict[str, Any]) -> int:
    start = max(int(a["start_segment_id"]), int(b["start_segment_id"]))
    end = min(int(a["end_segment_id"]), int(b["end_segment_id"]))
    return max(0, end - start + 1)


def align_pred_to_gold(
    pred_eps: list[dict[str, Any]], gold_eps: list[dict[str, Any]]
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    aligned: list[tuple[dict[str, Any], dict[str, Any]]] = []
    if not gold_eps:
        return []
    for pred in pred_eps:
        best = max(gold_eps, key=lambda g: overlap_segments(pred, g))
        aligned.append((pred, best))
    return aligned


def span_text(segments: list[dict[str, Any]], start_id: int, end_id: int) -> str:
    start_id = max(0, min(start_id, len(segments) - 1))
    end_id = max(start_id, min(end_id, len(segments) - 1))
    return " ".join(seg["text"] for seg in segments[start_id : end_id + 1])


class _LiteLLMCompletionsAdapter:
    def __init__(self, default_kwargs: dict[str, Any] | None = None):
        self.default_kwargs = default_kwargs or {}

    def create(self, model: str, messages: list[dict[str, str]], response_model: Any, **kwargs: Any) -> Any:
        import litellm

        litellm.drop_params = True
        merged_kwargs = {**self.default_kwargs, **kwargs}
        response = litellm.completion(
            model=model,
            messages=messages,
            response_format=response_model,
            **merged_kwargs,
        )
        return parse_structured_content(response.choices[0].message.content, response_model)


class _LiteLLMChatAdapter:
    def __init__(self, default_kwargs: dict[str, Any] | None = None):
        self.completions = _LiteLLMCompletionsAdapter(default_kwargs=default_kwargs)


class _LiteLLMClientAdapter:
    def __init__(self, default_kwargs: dict[str, Any] | None = None):
        self.chat = _LiteLLMChatAdapter(default_kwargs=default_kwargs)


def build_ragas_litellm_llm(model: str) -> Any:
    from ragas.llms.litellm_llm import LiteLLMStructuredLLM

    client_adapter = _LiteLLMClientAdapter(default_kwargs={"temperature": 0.0})
    return LiteLLMStructuredLLM(
        client=client_adapter,
        model=model,
        provider="litellm",
        temperature=0.0,
    )


def run_ragas_metrics(
    samples: list[dict[str, Any]],
    judge_model: str,
    show_progress: bool = True,
    max_workers: int = 16,
    batch_size: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    from ragas import EvaluationDataset, evaluate
    from ragas.run_config import RunConfig
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"Importing AspectCritic from 'ragas.metrics' is deprecated.*",
            category=DeprecationWarning,
        )
        warnings.filterwarnings(
            "ignore",
            message=r"Importing RubricsScore from 'ragas.metrics' is deprecated.*",
            category=DeprecationWarning,
        )
        from ragas.metrics import AspectCritic, RubricsScore

    if not samples:
        return [], {}

    llm = build_ragas_litellm_llm(judge_model)
    run_config = RunConfig(max_workers=max_workers)
    metrics = [
        RubricsScore(name="topic_match", rubrics=RUBRICS_TOPIC_MATCH, llm=llm),
        AspectCritic(
            name="single_topic_coherence",
            definition="Is the predicted episode focused on one coherent major topic?",
            llm=llm,
        ),
        AspectCritic(
            name="grounded_in_span",
            definition="Is the predicted episode grounded in retrieved_contexts and consistent with reference?",
            llm=llm,
        ),
    ]
    dataset = EvaluationDataset.from_list(samples)
    result = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=llm,
        run_config=run_config,
        show_progress=show_progress,
        batch_size=batch_size,
        raise_exceptions=True,
    )

    rows: list[dict[str, Any]] = []
    dataset_rows = dataset.to_list()
    for i, score_row in enumerate(result.scores):
        rows.append({**dataset_rows[i], **score_row})
    means = {k: float(v) for k, v in result._repr_dict.items()}
    return rows, means


def preflight_model_call(model: str) -> None:
    import litellm

    litellm.drop_params = True
    try:
        litellm.completion(
            model=model,
            messages=[{"role": "user", "content": "ok"}],
            temperature=0.0,
            max_tokens=1,
        )
    except Exception as exc:
        raise ValueError(
            f"Judge model unavailable: {model}. "
            "Use a valid LiteLLM Gemini model for your key, e.g. gemini/gemini-2.5-flash. "
            f"Original error: {exc}"
        ) from exc


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def get_mean(rows: list[dict[str, Any]], key: str) -> float:
    vals = [parse_float(row.get(key), 0.0) for row in rows if row.get(key) is not None]
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


def limit_rows(rows: list[dict[str, Any]], max_rows: int) -> list[dict[str, Any]]:
    if max_rows <= 0 or len(rows) <= max_rows:
        return rows
    if max_rows == 1:
        return [rows[0]]
    n = len(rows)
    picks = [int(i * n / max_rows) for i in range(max_rows)]
    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    for idx in picks:
        if idx in seen:
            continue
        seen.add(idx)
        out.append(rows[idx])
    i = 0
    while len(out) < max_rows and i < n:
        if i not in seen:
            out.append(rows[i])
            seen.add(i)
        i += 1
    return out


def cmd_normalize(args: argparse.Namespace) -> None:
    rows = normalize_transcripts(args.input_dir, args.output)
    print(f"Normalized {len(rows)} transcripts -> {args.output}")


def cmd_label_gold(args: argparse.Namespace) -> None:
    transcripts = read_jsonl(args.transcripts)
    gold_rows: list[dict[str, Any]] = []
    for t in transcripts:
        episodes = llm_segment_transcript(t, model=args.gold_model, prompt_mode="gold")
        validate_episode_partition(episodes, len(t["segments"]))
        gold_rows.append(
            {
                "journal_id": t["journal_id"],
                "episodes": episodes,
                "label_model": args.gold_model,
                "prompt_version": "gold_v1",
                "label_timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        print(f"Labeled {t['journal_id']}: {len(episodes)} episodes")
    write_jsonl(args.output, gold_rows)
    print(f"Gold labels -> {args.output}")


def cmd_predict(args: argparse.Namespace) -> None:
    assert_segmenter_model_policy(args.segmenter_model)
    transcripts = read_jsonl(args.transcripts)
    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    for s in strategies:
        if s not in SEGMENTER_STRATEGIES:
            raise ValueError(f"Unknown strategy {s}")

    resume_enabled = getattr(args, "resume", True)
    run_dir = args.run_dir
    run_dir.mkdir(parents=True, exist_ok=True)
    for strategy in strategies:
        out_path = run_dir / f"predictions_{strategy}.jsonl"
        rows: list[dict[str, Any]] = []
        done_ids: set[str] = set()

        if resume_enabled and out_path.exists():
            rows = read_jsonl(out_path)
            done_ids = {str(r.get("journal_id")) for r in rows}
            print(f"[{strategy}] resume enabled: loaded {len(done_ids)} completed journals")
        elif out_path.exists():
            out_path.unlink()

        for t in transcripts:
            journal_id = str(t["journal_id"])
            if journal_id in done_ids:
                print(f"{strategy} -> {journal_id} (skipped, already present)")
                continue
            episodes = run_strategy(
                strategy=strategy,
                transcript=t,
                segmenter_model=args.segmenter_model,
                b2_chunk_size=args.b2_segments_per_episode,
                s3_chunk_size=args.s3_chunk_size,
            )
            validate_episode_partition(episodes, len(t["segments"]))
            row = {
                "journal_id": journal_id,
                "strategy": strategy,
                "segmenter_model": args.segmenter_model,
                "episodes": episodes,
            }
            rows.append(row)
            if resume_enabled:
                append_jsonl(out_path, row)
                done_ids.add(journal_id)
            print(f"{strategy} -> {journal_id} ({len(episodes)} episodes)")

        if not resume_enabled:
            write_jsonl(out_path, rows)
        print(f"Wrote {out_path}")


def cmd_evaluate(args: argparse.Namespace) -> None:
    preflight_model_call(args.judge_model)
    if args.ragas_max_workers <= 0:
        raise ValueError("--ragas-max-workers must be > 0")
    ragas_batch_size = args.ragas_batch_size if args.ragas_batch_size and args.ragas_batch_size > 0 else None
    transcripts = build_journal_map(read_jsonl(args.transcripts))
    gold_map = build_journal_map(read_jsonl(args.gold))
    prediction_files = sorted(args.run_dir.glob("predictions_*.jsonl"))
    if not prediction_files:
        raise ValueError(f"No predictions files found in {args.run_dir}")

    leaderboard_rows: list[dict[str, Any]] = []

    for pred_file in prediction_files:
        pred_rows = read_jsonl(pred_file)
        if not pred_rows:
            continue
        strategy = pred_rows[0]["strategy"]
        det_rows: list[dict[str, Any]] = []
        ragas_samples: list[dict[str, Any]] = []

        for pred in pred_rows:
            journal_id = pred["journal_id"]
            transcript = transcripts[journal_id]
            gold = gold_map[journal_id]
            pred_eps = pred["episodes"]
            gold_eps = gold["episodes"]

            pred_boundaries_seg = boundaries_segment_ids(pred_eps)
            gold_boundaries_seg = boundaries_segment_ids(gold_eps)
            pred_boundaries_sec = boundaries_seconds(pred_eps)
            gold_boundaries_sec = boundaries_seconds(gold_eps)

            det_rows.append(
                {
                    "strategy": strategy,
                    "journal_id": journal_id,
                    "boundary_f1_seg_tol1": f1_with_tolerance(pred_boundaries_seg, gold_boundaries_seg, 1),
                    "boundary_f1_sec_tol10": f1_with_tolerance(pred_boundaries_sec, gold_boundaries_sec, 10.0),
                    "episode_count_error_abs": abs(len(pred_eps) - len(gold_eps)),
                    "pred_episode_count": len(pred_eps),
                    "gold_episode_count": len(gold_eps),
                }
            )

            for pred_ep, gold_ep in align_pred_to_gold(pred_eps, gold_eps):
                pred_text = span_text(
                    transcript["segments"],
                    int(pred_ep["start_segment_id"]),
                    int(pred_ep["end_segment_id"]),
                )
                ragas_samples.append(
                    {
                        "user_input": (
                            "Evaluate predicted episode quality. "
                            f"Journal={journal_id} Strategy={strategy}"
                        ),
                        "response": json.dumps(
                            {
                                "theme": pred_ep.get("theme"),
                                "title": pred_ep.get("title"),
                                "summary": pred_ep.get("summary"),
                            },
                            ensure_ascii=False,
                        ),
                        "reference": json.dumps(
                            {
                                "theme": gold_ep.get("theme"),
                                "title": gold_ep.get("title"),
                                "summary": gold_ep.get("summary"),
                            },
                            ensure_ascii=False,
                        ),
                        "retrieved_contexts": [pred_text],
                    }
                )

        write_csv(args.run_dir / f"deterministic_{strategy}.csv", det_rows)
        raw_sample_count = len(ragas_samples)
        ragas_samples = limit_rows(ragas_samples, args.ragas_max_samples)
        if len(ragas_samples) != raw_sample_count:
            print(
                f"Eval {strategy} | ragas_samples: {raw_sample_count} -> {len(ragas_samples)} "
                f"(ragas_max_samples={args.ragas_max_samples})"
            )
        else:
            print(f"Eval {strategy} | ragas_samples: {len(ragas_samples)}")
        write_jsonl(args.run_dir / f"ragas_samples_{strategy}.jsonl", ragas_samples)

        det_mean_seg = get_mean(det_rows, "boundary_f1_seg_tol1")
        det_mean_sec = get_mean(det_rows, "boundary_f1_sec_tol10")
        det_mean_count_error = get_mean(det_rows, "episode_count_error_abs")

        judge_model = args.judge_model
        print(
            f"Eval {strategy} | judge={judge_model} | workers={args.ragas_max_workers} "
            f"batch_size={ragas_batch_size}"
        )
        ragas_rows, ragas_means = run_ragas_metrics(
            ragas_samples,
            judge_model=judge_model,
            show_progress=args.ragas_show_progress,
            max_workers=args.ragas_max_workers,
            batch_size=ragas_batch_size,
        )
        write_jsonl(args.run_dir / f"ragas_rows_{strategy}_{judge_model.replace('/', '_')}.jsonl", ragas_rows)

        topic_match = ragas_means.get("topic_match", 0.0)
        coherence = ragas_means.get("single_topic_coherence", 0.0)
        grounded = ragas_means.get("grounded_in_span", 0.0)
        composite = (0.60 * det_mean_seg) + (0.25 * (topic_match / 5.0)) + (0.10 * coherence) + (0.05 * grounded)

        leaderboard_rows.append(
            {
                "strategy": strategy,
                "judge_model": judge_model,
                "segmenter_model": args.segmenter_model,
                "boundary_f1_seg_tol1_mean": det_mean_seg,
                "boundary_f1_sec_tol10_mean": det_mean_sec,
                "episode_count_error_abs_mean": det_mean_count_error,
                "topic_match_mean": topic_match,
                "single_topic_coherence_mean": coherence,
                "grounded_in_span_mean": grounded,
                "composite_score": composite,
            }
        )
        print(
            f"Eval {strategy} | judge={judge_model} | "
            f"F1seg={det_mean_seg:.3f} topic={topic_match:.3f} composite={composite:.3f}"
        )

    leaderboard_rows = sorted(leaderboard_rows, key=lambda r: r["composite_score"], reverse=True)
    write_csv(args.report_csv, leaderboard_rows)
    write_json(args.report_json, leaderboard_rows)
    print(f"Leaderboard CSV -> {args.report_csv}")
    print(f"Leaderboard JSON -> {args.report_json}")


def cmd_run_all(args: argparse.Namespace) -> None:
    normalize_args = argparse.Namespace(
        input_dir=args.input_dir,
        output=args.transcripts_out,
    )
    cmd_normalize(normalize_args)

    label_args = argparse.Namespace(
        transcripts=args.transcripts_out,
        output=args.gold_out,
        gold_model=args.gold_model,
    )
    cmd_label_gold(label_args)

    run_id = datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S")
    run_dir = args.runs_dir / run_id
    predict_args = argparse.Namespace(
        transcripts=args.transcripts_out,
        run_dir=run_dir,
        strategies=args.strategies,
        segmenter_model=args.segmenter_model,
        b2_segments_per_episode=args.b2_segments_per_episode,
        s3_chunk_size=args.s3_chunk_size,
    )
    cmd_predict(predict_args)

    eval_args = argparse.Namespace(
        transcripts=args.transcripts_out,
        gold=args.gold_out,
        run_dir=run_dir,
        judge_model=args.judge_model,
        segmenter_model=args.segmenter_model,
        ragas_max_samples=args.ragas_max_samples,
        ragas_show_progress=args.ragas_show_progress,
        ragas_max_workers=args.ragas_max_workers,
        ragas_batch_size=args.ragas_batch_size,
        report_csv=args.reports_dir / f"{run_id}_leaderboard.csv",
        report_json=args.reports_dir / f"{run_id}_leaderboard.json",
    )
    cmd_evaluate(eval_args)


def build_parser() -> argparse.ArgumentParser:
    load_dotenv_if_available()

    parser = argparse.ArgumentParser(description="Minimal episode segmentation experiment pipeline.")
    sub = parser.add_subparsers(dest="command", required=True)

    normalize_parser = sub.add_parser("normalize", help="Normalize Whisper transcript JSONs into JSONL dataset.")
    normalize_parser.add_argument(
        "--input-dir", type=Path, default=Path(os.getenv("EPISODE_INPUT_DIR", DEFAULT_TRANSCRIPTS_DIR))
    )
    normalize_parser.add_argument(
        "--output",
        type=Path,
        default=Path(os.getenv("EPISODE_NORMALIZED_DATASET", DEFAULT_DATASETS_DIR / "transcripts_normalized.jsonl")),
    )
    normalize_parser.set_defaults(func=cmd_normalize)

    gold_parser = sub.add_parser("label-gold", help="Generate pseudo-gold labels via LiteLLM.")
    gold_parser.add_argument(
        "--transcripts",
        type=Path,
        default=Path(os.getenv("EPISODE_NORMALIZED_DATASET", DEFAULT_DATASETS_DIR / "transcripts_normalized.jsonl")),
    )
    gold_parser.add_argument(
        "--output",
        type=Path,
        default=Path(os.getenv("EPISODE_GOLD_DATASET", DEFAULT_DATASETS_DIR / "gold_episodes_llm.jsonl")),
    )
    gold_parser.add_argument(
        "--gold-model",
        default=os.getenv("GOLD_LABEL_MODEL", os.getenv("SEGMENTER_MODEL", "gemini/gemini-2.5-flash")),
    )
    gold_parser.set_defaults(func=cmd_label_gold)

    predict_parser = sub.add_parser("predict", help="Run segmentation strategies and write predictions.")
    predict_parser.add_argument(
        "--transcripts",
        type=Path,
        default=Path(os.getenv("EPISODE_NORMALIZED_DATASET", DEFAULT_DATASETS_DIR / "transcripts_normalized.jsonl")),
    )
    predict_parser.add_argument(
        "--run-dir",
        type=Path,
        default=Path(os.getenv("EPISODE_RUN_DIR", DEFAULT_RUNS_DIR / "manual_run")),
    )
    predict_parser.add_argument("--strategies", default=os.getenv("EPISODE_STRATEGIES", "B1,B2,S1,S2,S3"))
    predict_parser.add_argument(
        "--segmenter-model",
        default=os.getenv("SEGMENTER_MODEL", "gemini/gemini-2.5-flash"),
    )
    predict_parser.add_argument(
        "--b2-segments-per-episode",
        type=int,
        default=int(os.getenv("B2_SEGMENTS_PER_EPISODE", "30")),
    )
    predict_parser.add_argument(
        "--s3-chunk-size",
        type=int,
        default=int(os.getenv("S3_CHUNK_SIZE", "40")),
    )
    predict_parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Resume from existing predictions_<strategy>.jsonl and append remaining journals.",
    )
    predict_parser.set_defaults(func=cmd_predict)

    eval_parser = sub.add_parser("evaluate", help="Evaluate predictions with deterministic + Ragas metrics.")
    eval_parser.add_argument(
        "--transcripts",
        type=Path,
        default=Path(os.getenv("EPISODE_NORMALIZED_DATASET", DEFAULT_DATASETS_DIR / "transcripts_normalized.jsonl")),
    )
    eval_parser.add_argument(
        "--gold",
        type=Path,
        default=Path(os.getenv("EPISODE_GOLD_DATASET", DEFAULT_DATASETS_DIR / "gold_episodes_llm.jsonl")),
    )
    eval_parser.add_argument(
        "--run-dir",
        type=Path,
        default=Path(os.getenv("EPISODE_RUN_DIR", DEFAULT_RUNS_DIR / "manual_run")),
    )
    eval_parser.add_argument("--segmenter-model", default=os.getenv("SEGMENTER_MODEL", "gemini/gemini-2.5-flash"))
    eval_parser.add_argument("--judge-model", default=os.getenv("JUDGE_MODEL", "gemini/gemini-2.5-flash"))
    eval_parser.add_argument(
        "--ragas-max-samples",
        type=int,
        default=int(os.getenv("RAGAS_MAX_SAMPLES", "60")),
        help="Max Ragas samples per strategy (<=0 means all).",
    )
    eval_parser.add_argument(
        "--ragas-show-progress",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Show Ragas progress bars.",
    )
    eval_parser.add_argument(
        "--ragas-max-workers",
        type=int,
        default=int(os.getenv("RAGAS_MAX_WORKERS", "16")),
        help="Max parallel workers for Ragas evaluation calls.",
    )
    eval_parser.add_argument(
        "--ragas-batch-size",
        type=int,
        default=int(os.getenv("RAGAS_BATCH_SIZE", "0")),
        help="Batch size passed to ragas evaluate() (0 means unset).",
    )
    eval_parser.add_argument(
        "--report-csv",
        type=Path,
        default=Path(os.getenv("EPISODE_REPORT_CSV", DEFAULT_REPORTS_DIR / "leaderboard.csv")),
    )
    eval_parser.add_argument(
        "--report-json",
        type=Path,
        default=Path(os.getenv("EPISODE_REPORT_JSON", DEFAULT_REPORTS_DIR / "leaderboard.json")),
    )
    eval_parser.set_defaults(func=cmd_evaluate)

    run_all_parser = sub.add_parser("run-all", help="Run normalize -> label-gold -> predict -> evaluate")
    run_all_parser.add_argument(
        "--input-dir", type=Path, default=Path(os.getenv("EPISODE_INPUT_DIR", DEFAULT_TRANSCRIPTS_DIR))
    )
    run_all_parser.add_argument(
        "--transcripts-out",
        type=Path,
        default=Path(os.getenv("EPISODE_NORMALIZED_DATASET", DEFAULT_DATASETS_DIR / "transcripts_normalized.jsonl")),
    )
    run_all_parser.add_argument(
        "--gold-out",
        type=Path,
        default=Path(os.getenv("EPISODE_GOLD_DATASET", DEFAULT_DATASETS_DIR / "gold_episodes_llm.jsonl")),
    )
    run_all_parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path(os.getenv("EPISODE_RUNS_DIR", DEFAULT_RUNS_DIR)),
    )
    run_all_parser.add_argument(
        "--reports-dir",
        type=Path,
        default=Path(os.getenv("EPISODE_REPORTS_DIR", DEFAULT_REPORTS_DIR)),
    )
    run_all_parser.add_argument("--strategies", default=os.getenv("EPISODE_STRATEGIES", "B1,B2,S1,S2,S3"))
    run_all_parser.add_argument(
        "--segmenter-model",
        default=os.getenv("SEGMENTER_MODEL", "gemini/gemini-2.5-flash"),
    )
    run_all_parser.add_argument("--judge-model", default=os.getenv("JUDGE_MODEL", "gemini/gemini-2.5-flash"))
    run_all_parser.add_argument(
        "--ragas-max-samples",
        type=int,
        default=int(os.getenv("RAGAS_MAX_SAMPLES", "60")),
    )
    run_all_parser.add_argument(
        "--ragas-show-progress",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    run_all_parser.add_argument(
        "--ragas-max-workers",
        type=int,
        default=int(os.getenv("RAGAS_MAX_WORKERS", "16")),
    )
    run_all_parser.add_argument(
        "--ragas-batch-size",
        type=int,
        default=int(os.getenv("RAGAS_BATCH_SIZE", "0")),
    )
    run_all_parser.add_argument(
        "--gold-model",
        default=os.getenv("GOLD_LABEL_MODEL", os.getenv("SEGMENTER_MODEL", "gemini/gemini-2.5-flash")),
    )
    run_all_parser.add_argument(
        "--b2-segments-per-episode",
        type=int,
        default=int(os.getenv("B2_SEGMENTS_PER_EPISODE", "30")),
    )
    run_all_parser.add_argument(
        "--s3-chunk-size",
        type=int,
        default=int(os.getenv("S3_CHUNK_SIZE", "40")),
    )
    run_all_parser.set_defaults(func=cmd_run_all)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
