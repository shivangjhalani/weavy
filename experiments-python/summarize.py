#!/usr/bin/env python3
"""Summarize transcript JSON files using LiteLLM structured output."""

import argparse
import glob
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from litellm import completion
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PRIVATE_SUMMARIES = PROJECT_ROOT / "private" / "summaries"

load_dotenv(PROJECT_ROOT / ".env")

FILENAME_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)")


class LLMJournalSummary(BaseModel):
    title: str = Field(description="Short descriptive title for this journal entry")
    mood: List[str] = Field(
        description="1-3 emotional states during this journal (e.g., 'frustrated', 'hopeful', 'anxious', 'energized', 'reflective', 'confused')",
    )
    topics: List[str] = Field(
        description="Main themes discussed"
    )
    memorable_quotes: List[str] = Field(
        description="Most memorable direct quotes from transcript (max 150 chars)"
    )
    key_learnings: List[str] = Field(
        description="Most important core insights (one line each, max 100 chars)"
    )
    active_questions: List[str] = Field(
        description="Most important unresolved questions or tensions (one line each, max 100 chars)"
    )


class JournalSummary(BaseModel):
    # Locally controlled metadata first.
    date: datetime
    duration_minutes: int
    # LLM-generated summary fields.
    title: str
    mood: List[str]
    topics: List[str]
    memorable_quotes: List[str]
    key_learnings: List[str]
    active_questions: List[str]

    transcript: str = Field(description="Full transcript text")


# SUMMARY_PROMPT = """\
# Analyze this {duration_minutes}-minute personal journal transcript.

# Extract:
# - 3-5 KEY LEARNINGS: Core insights to remember (one line each, max 100 chars each)
# - 2-3 MEMORABLE QUOTES: Direct quotes that capture essence (max 150 chars each)
# - 3-5 ACTIVE QUESTIONS: Unresolved tensions or questions (one line each, max 100 chars)
# - TOPICS: Specific concepts, people, companies, or situations discussed (NOT generic themes like "self-improvement")
#   Examples of bad topics: "personal growth", "self-improvement", "Personal reflection"
# - TITLE: A short descriptive title (max 60 chars)

# Make learnings and questions CONCISE.
# Quotes should be verbatim (cleaned of typos and structure) from the transcript and meaningful.

# Transcript:
# {text}
# """

SUMMARY_PROMPT = """\
Analyze this {duration_minutes}-minute personal journal transcript.

Extract the following, but ONLY if they meet the quality threshold:

TITLE: A short descriptive title (max 60 chars)

MOOD (1-3 tags):
- Capture the dominant emotional states during journaling
- Use specific emotions: frustrated, anxious, hopeful, energized, reflective, confused, determined, overwhelmed, excited, doubtful etc.
- NOT generic states like "good" or "bad"
- Choose 1-3 that best characterize the session

TOPICS (3-6 items):
- Concrete entities: people, companies, specific concepts
- Broad themes useful for filtering (e.g., "career", "communication", "relationships")
- NOT abstract states

MEMORABLE QUOTES (0-3 items):
- Extract ONLY quotes that uniquely capture your voice or a key insight
- Must be meaningful enough to remind you of the context
- Max 150 chars each
- Skip if no quotes meet this bar

KEY LEARNINGS (1-5 items):
- Extract ONLY genuine insights worth remembering
- Each must be a concrete realization, not generic advice
- One line each, max 100 chars
- If the journal is sparse/surface-level, extract fewer (even 0-1)
- Quality over quantity

ACTIVE QUESTIONS (1-5 items):
- Extract ONLY genuine unresolved tensions or questions
- Must be specific, not generic wondering
- One line each, max 100 chars
- Fewer is better than low-quality items

CRITICAL: If the journal is sparse or conversational without deep insights, extract fewer items. An empty quotes array is better than forced padding.

Transcript:
{text}
"""


def parse_date_from_filename(filename: str) -> datetime:
    """Extract the ISO-8601 datetime prefix from a transcript filename."""
    m = FILENAME_DATE_RE.match(filename)
    if not m:
        raise ValueError(f"Cannot parse date from filename: {filename}")
    return datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))


def load_transcript(path: Path) -> dict:
    """Load and validate transcript JSON."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if "text" not in data:
        raise ValueError(f"Transcript missing 'text' field: {path}")
    return data


def resolve_transcript_paths(inputs: List[str]) -> List[Path]:
    """Resolve CLI inputs into transcript file paths.

    Supports:
    - direct file paths
    - wildcard patterns (e.g. private/transcripts/*.json)
    """
    resolved: List[Path] = []
    for raw in inputs:
        # Expand wildcard patterns even if shell does not.
        if any(ch in raw for ch in ["*", "?", "["]):
            matches = glob.glob(
                str((PROJECT_ROOT / raw).resolve()) if not Path(raw).is_absolute() else raw
            )
            resolved.extend(Path(m).resolve() for m in matches)
            continue

        p = Path(raw)
        if not p.is_absolute():
            p = (PROJECT_ROOT / p).resolve()
        resolved.append(p)

    # Deduplicate while preserving order.
    deduped: List[Path] = []
    seen = set()
    for p in resolved:
        if p not in seen:
            deduped.append(p)
            seen.add(p)
    return deduped


def summarize(transcript: dict, date: datetime) -> JournalSummary:
    """Generate a structured summary via LiteLLM."""
    model = os.getenv("GEMINI_MODEL", "gemini/gemini-2.5-flash")

    duration_minutes = round(transcript.get("duration", 0) / 60)
    text = transcript["text"].strip()

    prompt = SUMMARY_PROMPT.format(duration_minutes=duration_minutes, text=text)

    response = completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format=LLMJournalSummary,
    )

    llm_summary = LLMJournalSummary.model_validate_json(response.choices[0].message.content)
    return JournalSummary(
        date=date,
        duration_minutes=duration_minutes,
        title=llm_summary.title,
        mood=llm_summary.mood,
        topics=llm_summary.topics,
        memorable_quotes=llm_summary.memorable_quotes,
        key_learnings=llm_summary.key_learnings,
        active_questions=llm_summary.active_questions,
        transcript=text,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize one or more transcript JSON files using Gemini structured output."
    )
    parser.add_argument(
        "transcripts",
        nargs="+",
        help="Transcript path(s) or glob(s), e.g. file1.json file2.json or private/transcripts/*.json",
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=None,
        help="Output path for single-input mode only (default: private/summaries/<stem>_summary.json)",
    )
    parser.add_argument(
        "--no-skip",
        action="store_true",
        help="Overwrite existing summaries instead of skipping",
    )
    args = parser.parse_args()

    transcript_paths = resolve_transcript_paths(args.transcripts)
    if not transcript_paths:
        parser.error("No transcript files matched the provided inputs.")

    if args.output and len(transcript_paths) > 1:
        parser.error("--output can only be used when summarizing a single transcript.")

    if not os.getenv("GEMINI_API_KEY"):
        parser.error("GEMINI_API_KEY not set. Add it to .env (copy from .example.env).")

    PRIVATE_SUMMARIES.mkdir(parents=True, exist_ok=True)
    had_errors = False

    for transcript_path in transcript_paths:
        if not transcript_path.exists():
            print(f"Skipping missing file: {transcript_path}")
            had_errors = True
            continue
        if not transcript_path.is_file():
            print(f"Skipping non-file path: {transcript_path}")
            had_errors = True
            continue

        if args.output:
            out_path = (
                args.output if args.output.is_absolute() else (PROJECT_ROOT / args.output).resolve()
            )
        else:
            out_path = PRIVATE_SUMMARIES / f"{transcript_path.stem}_summary.json"

        if out_path.exists() and not args.no_skip:
            print(f"Skip {transcript_path.name} (summary exists)")
            continue

        try:
            date = parse_date_from_filename(transcript_path.name)
            transcript = load_transcript(transcript_path)

            print(f"Summarizing: {transcript_path.name}")
            summary = summarize(transcript, date)

            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
            print(f"Summary saved to {out_path}")
        except Exception as e:
            print(f"Failed to summarize {transcript_path}: {e}")
            had_errors = True

    if had_errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
