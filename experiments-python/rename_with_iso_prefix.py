#!/usr/bin/env python3
"""Rename files in private/raw with random ISO 8601 UTC prefix (Jan 5 2025 - Feb 5 2026)."""

import random
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
RAW_DIR = PROJECT_ROOT / "private" / "raw"

START = datetime(2025, 1, 5, 0, 0, 0, tzinfo=timezone.utc)
END = datetime(2026, 2, 5, 23, 59, 59, tzinfo=timezone.utc)


def random_iso8601_utc() -> str:
    """Random datetime in [START, END], formatted as ISO 8601 UTC (lexicographically sortable)."""
    start_ts = START.timestamp()
    end_ts = END.timestamp()
    ts = random.uniform(start_ts, end_ts)
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    files = [f for f in RAW_DIR.iterdir() if f.is_file()]
    used_prefixes: set[str] = set()

    for f in sorted(files):
        while True:
            prefix = random_iso8601_utc()
            if prefix not in used_prefixes:
                used_prefixes.add(prefix)
                break

        new_name = f"{prefix}_{f.name}"
        new_path = f.parent / new_name
        f.rename(new_path)
        print(f"{f.name} -> {new_name}")


if __name__ == "__main__":
    main()
