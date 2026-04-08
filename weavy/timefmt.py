from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

import humanize
from pydantic import PlainSerializer


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _relative_phrase(dt: datetime, now: datetime) -> str:
    return str(humanize.naturaltime(dt - now))


def format_agent_timestamp(
    dt: datetime,
    *,
    now: datetime | None = None,
    include_relative: bool = True,
) -> str:
    dt = _ensure_aware(dt)
    now = _ensure_aware(now or datetime.now(tz=timezone.utc))
    absolute = dt.strftime("%A %d %b %Y, %I:%M %p %Z")
    if not include_relative:
        return absolute
    return f"{_relative_phrase(dt, now)}, {absolute}"


AgentTimestamp = Annotated[
    datetime,
    PlainSerializer(format_agent_timestamp, when_used="json"),
]


def format_agent_date_range(
    start: datetime,
    end: datetime,
    *,
    now: datetime | None = None,
) -> list[str]:
    return [
        format_agent_timestamp(start, now=now),
        format_agent_timestamp(end, now=now),
    ]
