from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone, tzinfo
from typing import Self

import pytest

from .. import _time_helpers
from .._time_helpers import (
    _in_range,
    _parse_timestamp,
    filter_logs_by_time,
    resolve_time_window,
)


class TestResolveTimeWindow:
    def test_relative_hour_spans_elapsed_time_during_warsaw_autumn_transition(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class TransitionClock(datetime):
            @classmethod
            def now(cls, tz: tzinfo | None = None) -> Self:
                local: Self = cls(2026, 10, 25, 3, 30)
                return local if tz is None else local.astimezone(tz)

            def astimezone(self, tz: tzinfo | None = None) -> Self:
                if self.tzinfo is not None:
                    return super().astimezone(tz)
                offset: timezone = timezone(timedelta(hours=1 if self.hour >= 3 else 2))
                return self.replace(tzinfo=offset).astimezone(tz)

        monkeypatch.setattr(_time_helpers, "datetime", TransitionClock)
        start, end = resolve_time_window(hours=1)
        assert start is not None
        assert end is not None
        assert end.astimezone(UTC) - start.astimezone(UTC) == timedelta(hours=1)
        assert start.tzinfo is UTC
        assert end.tzinfo is UTC
        logs: list[dict[str, str]] = [
            {"timestamp": "2026-10-25T01:15:00+00:00", "message": "seventy-five-minutes-old"},
            {"timestamp": "2026-10-25T01:45:00+00:00", "message": "forty-five-minutes-old"},
        ]
        assert filter_logs_by_time(logs, start, end) == [logs[1]]

    def test_passthrough_when_no_shortcuts(self) -> None:
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 2)
        s, e = resolve_time_window(start=start, end=end)
        assert s == start
        assert e == end

    def test_none_passthrough(self) -> None:
        s, e = resolve_time_window()
        assert s is None
        assert e is None

    def test_minutes_shortcut(self) -> None:
        before = datetime.now(UTC)
        s, e = resolve_time_window(minutes=10)
        after = datetime.now(UTC)
        assert s is not None
        assert e is not None
        assert before - timedelta(minutes=10, seconds=1) <= s
        assert e <= after

    def test_hours_shortcut(self) -> None:
        before = datetime.now(UTC)
        s, e = resolve_time_window(hours=2)
        after = datetime.now(UTC)
        assert s is not None
        assert e is not None
        assert before - timedelta(hours=2, seconds=1) <= s
        assert e <= after

    def test_days_shortcut(self) -> None:
        before = datetime.now(UTC)
        s, e = resolve_time_window(days=7)
        after = datetime.now(UTC)
        assert s is not None
        assert e is not None
        assert before - timedelta(days=7, seconds=1) <= s
        assert e <= after

    def test_minutes_beats_hours(self) -> None:
        s, _e = resolve_time_window(minutes=5, hours=2)
        assert s is not None
        assert (datetime.now(UTC) - s) < timedelta(minutes=6)

    def test_hours_beats_days(self) -> None:
        s, _e = resolve_time_window(hours=1, days=30)
        assert s is not None
        assert (datetime.now(UTC) - s) < timedelta(hours=2)


class TestParseTimestamp:
    def test_iso_format(self) -> None:
        log = {"timestamp": "2024-06-15T12:00:00"}
        result = _parse_timestamp(log)
        assert result == datetime(2024, 6, 15, 12, 0, 0)

    def test_missing_timestamp(self) -> None:
        assert _parse_timestamp({}) is None

    def test_none_timestamp(self) -> None:
        assert _parse_timestamp({"timestamp": None}) is None

    def test_invalid_timestamp(self) -> None:
        assert _parse_timestamp({"timestamp": "not-a-date"}) is None

    def test_non_string_timestamp(self) -> None:
        assert _parse_timestamp({"timestamp": 12345}) is None


class TestInRange:
    def test_aware_record_with_naive_local_bounds(self) -> None:
        local: datetime = datetime(2024, 6, 15, 12)
        log: dict[str, str] = {"timestamp": local.astimezone(UTC).isoformat()}
        assert _in_range(log, local - timedelta(minutes=1), local + timedelta(minutes=1))

    def test_naive_record_with_aware_bounds(self) -> None:
        local: datetime = datetime(2024, 6, 15, 12)
        log: dict[str, str] = {"timestamp": local.isoformat()}
        instant: datetime = local.astimezone(UTC)
        assert _in_range(log, instant, instant)

    def test_offsets_are_compared_as_instants(self) -> None:
        start: datetime = datetime(2024, 6, 15, 12, tzinfo=UTC)
        offset: timezone = timezone(timedelta(hours=2))
        matching: dict[str, str] = {"timestamp": start.astimezone(offset).isoformat()}
        earlier: dict[str, str] = {"timestamp": start.replace(tzinfo=offset).isoformat()}
        assert _in_range(matching, start, start)
        assert not _in_range(earlier, start, start + timedelta(hours=1))

    def test_within_range(self) -> None:
        log = {"timestamp": "2024-06-15T12:00:00"}
        start = datetime(2024, 6, 15, 11, 0, 0)
        end = datetime(2024, 6, 15, 13, 0, 0)
        assert _in_range(log, start, end) is True

    def test_before_range(self) -> None:
        log = {"timestamp": "2024-06-15T10:00:00"}
        start = datetime(2024, 6, 15, 11, 0, 0)
        end = datetime(2024, 6, 15, 13, 0, 0)
        assert _in_range(log, start, end) is False

    def test_after_range(self) -> None:
        log = {"timestamp": "2024-06-15T14:00:00"}
        start = datetime(2024, 6, 15, 11, 0, 0)
        end = datetime(2024, 6, 15, 13, 0, 0)
        assert _in_range(log, start, end) is False

    def test_start_only(self) -> None:
        log = {"timestamp": "2024-06-15T12:00:00"}
        assert _in_range(log, datetime(2024, 6, 15, 11, 0, 0), None) is True
        assert _in_range(log, datetime(2024, 6, 15, 13, 0, 0), None) is False

    def test_end_only(self) -> None:
        log = {"timestamp": "2024-06-15T12:00:00"}
        assert _in_range(log, None, datetime(2024, 6, 15, 13, 0, 0)) is True
        assert _in_range(log, None, datetime(2024, 6, 15, 11, 0, 0)) is False

    def test_no_timestamp_returns_false(self) -> None:
        assert _in_range({}, datetime(2024, 1, 1), datetime(2024, 1, 2)) is False


class TestFilterLogsByTime:
    @pytest.fixture
    def logs(self) -> list[dict[str, str]]:
        return [
            {"timestamp": "2024-06-15T10:00:00", "message": "early"},
            {"timestamp": "2024-06-15T12:00:00", "message": "noon"},
            {"timestamp": "2024-06-15T14:00:00", "message": "late"},
        ]

    def test_no_filter_returns_all(self, logs: list[dict[str, str]]) -> None:
        assert filter_logs_by_time(logs, None, None) == logs

    def test_start_filter(self, logs: list[dict[str, str]]) -> None:
        result = filter_logs_by_time(logs, datetime(2024, 6, 15, 11, 0, 0), None)
        assert len(result) == 2
        assert result[0]["message"] == "noon"

    def test_end_filter(self, logs: list[dict[str, str]]) -> None:
        result = filter_logs_by_time(logs, None, datetime(2024, 6, 15, 13, 0, 0))
        assert len(result) == 2
        assert result[-1]["message"] == "noon"

    def test_both_filters(self, logs: list[dict[str, str]]) -> None:
        result = filter_logs_by_time(
            logs,
            datetime(2024, 6, 15, 11, 0, 0),
            datetime(2024, 6, 15, 13, 0, 0),
        )
        assert len(result) == 1
        assert result[0]["message"] == "noon"

    def test_empty_list(self) -> None:
        assert filter_logs_by_time([], datetime(2024, 1, 1), datetime(2024, 1, 2)) == []
