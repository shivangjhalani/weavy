from __future__ import annotations

from datetime import datetime, timezone

try:
    import humanize
except Exception:  # pragma: no cover - fallback when dependency is unavailable
    humanize = None


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _relative_phrase(dt: datetime, now: datetime) -> str:
    if humanize is not None:
        return str(humanize.naturaltime(dt - now))

    delta = now - dt
    seconds = int(abs(delta.total_seconds()))
    if seconds < 10:
        phrase = "just now"
    elif seconds < 60:
        phrase = f"{seconds} seconds"
    elif seconds < 3600:
        minutes = seconds // 60
        phrase = f"{minutes} minute{'s' if minutes != 1 else ''}"
    elif seconds < 86400:
        hours = seconds // 3600
        phrase = f"{hours} hour{'s' if hours != 1 else ''}"
    elif seconds < 604800:
        days = seconds // 86400
        phrase = f"{days} day{'s' if days != 1 else ''}"
    elif seconds < 2629800:
        weeks = seconds // 604800
        phrase = f"{weeks} week{'s' if weeks != 1 else ''}"
    elif seconds < 31557600:
        months = seconds // 2629800
        phrase = f"{months} month{'s' if months != 1 else ''}"
    else:
        years = seconds // 31557600
        phrase = f"{years} year{'s' if years != 1 else ''}"

    if phrase == "just now":
        return phrase
    return f"{phrase} ago" if delta.total_seconds() >= 0 else f"in {phrase}"


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
