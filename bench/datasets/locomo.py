"""LoCoMo dataset loader.

LoCoMo (https://github.com/snap-research/locomo) is the de-facto conversational
long-term-memory benchmark: 10 multi-session dialogues between two speakers, each
with a category-tagged QA set. We parse ``locomo10.json`` into typed objects and
turn each conversation into a list of :class:`~bench.adapters.base.Episode` at a
configurable granularity.

The raw schema (one array element per conversation)::

    {
      "conversation": {
        "speaker_a": "Caroline",
        "speaker_b": "Melanie",
        "session_1_date_time": "1:56 pm on 8 May, 2023",
        "session_1": [ {"speaker": "...", "dia_id": "D1:1", "text": "..."}, ... ],
        "session_2_date_time": ...,
        "session_2": [ ... ],
        ...
      },
      "qa": [
        {"question": "...", "answer": "...", "evidence": ["D1:3"], "category": 2},
        {"question": "...", "answer": "No", "adversarial_answer": "Yes",
         "evidence": ["D5:8"], "category": 5},
        ...
      ]
    }

The file is not redistributed here — download it once with
``python -m bench.run download`` (or manually) into ``bench/data/locomo10.json``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

# LoCoMo category integers. This mapping follows the convention used by the Mem0
# LoCoMo evaluation (the most-cited harness) so our per-category numbers line up
# with published results. Adversarial (5) is scored separately as abstention.
CATEGORY_NAMES: dict[int, str] = {
    1: "multi_hop",
    2: "temporal",
    3: "open_domain",
    4: "single_hop",
    5: "adversarial",
}

Granularity = Literal["session", "turn", "conversation"]

# Date strings look like "1:56 pm on 8 May, 2023". Python's strptime matches
# month names and am/pm case-insensitively, so a single format suffices; we keep
# a couple of fallbacks for robustness.
_DATE_FORMATS = (
    "%I:%M %p on %d %B, %Y",
    "%I:%M %p on %d %B %Y",
    "%H:%M on %d %B, %Y",
)

# Import lazily to avoid a hard dependency for callers that pass datetimes in.
from bench.adapters.base import Episode  # noqa: E402


def _parse_date(raw: str) -> datetime:
    s = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Unrecognised LoCoMo date string: {raw!r}")


@dataclass(frozen=True)
class Turn:
    speaker: str
    dia_id: str
    text: str


@dataclass(frozen=True)
class SessionBlock:
    index: int
    date: datetime
    turns: list[Turn]

    def to_text(self) -> str:
        lines = [_turn_line(t) for t in self.turns]
        return "\n".join(lines)


@dataclass(frozen=True)
class QAItem:
    question: str
    answer: str
    category: int
    evidence: list[str]

    @property
    def category_name(self) -> str:
        return CATEGORY_NAMES.get(self.category, f"category_{self.category}")

    @property
    def is_adversarial(self) -> bool:
        return self.category == 5


@dataclass(frozen=True)
class Conversation:
    sample_id: str
    speaker_a: str
    speaker_b: str
    sessions: list[SessionBlock]
    qa: list[QAItem]

    @property
    def context(self) -> str:
        return (
            f"A multi-session chat conversation between {self.speaker_a} "
            f"and {self.speaker_b}."
        )

    @property
    def query_time(self) -> datetime:
        """When the questions are posed: just after the last session."""
        last = max((s.date for s in self.sessions), default=datetime.now(timezone.utc))
        return last + timedelta(days=1)

    def to_episodes(self, granularity: Granularity = "session") -> list[Episode]:
        """Render the dialogue into ingestion episodes.

        - ``session`` (default): one episode per session, session date as
          timestamp. Preserves temporal structure with coherent context.
        - ``turn``: one episode per speaker turn (shares its session's date).
        - ``conversation``: a single episode for the whole dialogue, with each
          session prefixed by a dated header so structure is not fully lost.
        """
        if granularity == "session":
            return [
                Episode(text=s.to_text(), timestamp=s.date, context=self.context)
                for s in self.sessions
            ]
        if granularity == "turn":
            return [
                Episode(text=_turn_line(t), timestamp=s.date, context=self.context)
                for s in self.sessions
                for t in s.turns
            ]
        if granularity == "conversation":
            blocks = [
                f"# Session {s.index} — {s.date:%d %B %Y}\n{s.to_text()}"
                for s in self.sessions
            ]
            ts = self.sessions[0].date if self.sessions else datetime.now(timezone.utc)
            return [
                Episode(text="\n\n".join(blocks), timestamp=ts, context=self.context)
            ]
        raise ValueError(f"Unknown granularity: {granularity!r}")


def _turn_line(t: Turn) -> str:
    return f"{t.speaker}: {t.text}"


def _load_sessions(conv: dict) -> list[SessionBlock]:
    blocks: list[SessionBlock] = []
    index = 1
    while f"session_{index}" in conv:
        date_key = f"session_{index}_date_time"
        if date_key not in conv:
            raise ValueError(f"session_{index} present but {date_key} missing")
        turns = [
            Turn(
                speaker=str(t.get("speaker", "")),
                dia_id=str(t.get("dia_id", "")),
                text=_with_image(t),
            )
            for t in conv[f"session_{index}"]
        ]
        blocks.append(
            SessionBlock(index=index, date=_parse_date(conv[date_key]), turns=turns)
        )
        index += 1
    return blocks


def _with_image(turn: dict) -> str:
    """Fold image captions into the text so visual context is not dropped."""
    text = str(turn.get("text", "")).strip()
    caption = turn.get("blip_caption")
    if caption:
        return f"{text} [shared an image: {caption}]".strip()
    return text


def _load_qa(item: dict) -> QAItem | None:
    if "question" not in item or "category" not in item:
        return None
    category = int(item["category"])
    # Category 5 sometimes stores the correct yes/no rebuttal in "answer" (the
    # question posed a binary false premise); "adversarial_answer" is always
    # the trap the question implies and must never be graded as gold — most
    # category-5 items in this dataset carry only "adversarial_answer" (the
    # premise substitutes the wrong entity/attribute with no single correct
    # string), so gold falls back to a premise-is-false marker instead.
    if "answer" in item:
        answer = item["answer"]
    elif category == 5:
        answer = "The premise is false / not supported by the record."
    else:
        answer = item.get("adversarial_answer", "")
    return QAItem(
        question=str(item["question"]).strip(),
        answer=str(answer).strip(),
        category=category,
        evidence=[str(e) for e in item.get("evidence", [])],
    )


def load_locomo(path: str | Path) -> list[Conversation]:
    """Load and parse ``locomo10.json`` into typed conversations."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"LoCoMo data not found at {p}. Download it with "
            f"`python -m bench.run download` or place locomo10.json there."
        )
    raw = json.loads(p.read_text())
    conversations: list[Conversation] = []
    for i, sample in enumerate(raw):
        conv = sample["conversation"]
        qa = [q for q in (_load_qa(it) for it in sample.get("qa", [])) if q]
        conversations.append(
            Conversation(
                sample_id=str(sample.get("sample_id", i)),
                speaker_a=str(conv.get("speaker_a", "Speaker A")),
                speaker_b=str(conv.get("speaker_b", "Speaker B")),
                sessions=_load_sessions(conv),
                qa=qa,
            )
        )
    return conversations
