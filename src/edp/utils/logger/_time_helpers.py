"""Shared time-range helpers for log readers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

__all__ = ["filter_logs_by_time", "resolve_time_window"]


def resolve_time_window(
    start: datetime | None = None,
    end: datetime | None = None,
    minutes: int | None = None,
    hours: int | None = None,
    days: int | None = None,
) -> tuple[datetime | None, datetime | None]:
    """Convert relative time shortcuts to absolute start/end.

    Priority: ``minutes`` > ``hours`` > ``days`` (first non-None wins).

    Args:
        start: Absolute start datetime.
        end: Absolute end datetime.
        minutes: Last N minutes shortcut.
        hours: Last N hours shortcut.
        days: Last N days shortcut.

    Returns:
        Tuple of (start, end) datetimes.
    """
    if minutes or hours or days:
        now: datetime = datetime.now(UTC)
        if minutes:
            start = now - timedelta(minutes=minutes)
        elif hours:
            start = now - timedelta(hours=hours)
        elif days:
            start = now - timedelta(days=days)
        end = now
    return start, end


def filter_logs_by_time(
    logs: list[dict[str, Any]],
    start: datetime | None,
    end: datetime | None,
) -> list[dict[str, Any]]:
    """Filter log entries by timestamp range; naive times mean local time.

    Args:
        logs: Log entries to filter.
        start: Start datetime (inclusive).
        end: End datetime (inclusive).

    Returns:
        Filtered log entries.
    """
    if not start and not end:
        return logs

    return [log for log in logs if _in_range(log, start, end)]


def _parse_timestamp(log: dict[str, Any]) -> datetime | None:
    """Parse timestamp from a log entry.

    Args:
        log: Log dictionary.

    Returns:
        Parsed datetime or None.
    """
    timestamp_str = log.get("timestamp")
    if not timestamp_str:
        return None
    try:
        return datetime.fromisoformat(timestamp_str)
    except ValueError, TypeError:
        return None


def _in_range(
    log: dict[str, Any],
    start: datetime | None,
    end: datetime | None,
) -> bool:
    """Check whether a single log entry falls within the time range.

    Args:
        log: Log dictionary.
        start: Range start (inclusive).
        end: Range end (inclusive).

    Returns:
        True if the entry is within range.
    """
    ts: datetime | None = _parse_timestamp(log)
    if ts is None:
        return False
    ts = ts.astimezone(UTC)
    if start and ts < start.astimezone(UTC):
        return False
    return not (end and ts > end.astimezone(UTC))
