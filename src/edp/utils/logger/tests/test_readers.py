from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

import pytest

from ..readers import LogAggregator, LogReader

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def log_file(tmp_path: Path) -> Path:
    logs = [
        {"level": "INFO", "message": "app started", "logger": "app", "timestamp": "2024-06-15T10:00:00"},
        {"level": "DEBUG", "message": "loading config", "logger": "config", "timestamp": "2024-06-15T10:01:00"},
        {"level": "ERROR", "message": "db connection failed", "logger": "db", "timestamp": "2024-06-15T10:02:00"},
        {"level": "WARNING", "message": "slow query detected", "logger": "db", "timestamp": "2024-06-15T10:03:00"},
        {"level": "INFO", "message": "request handled", "logger": "api", "timestamp": "2024-06-15T10:04:00"},
        {"level": "ERROR", "message": "timeout error", "logger": "api", "timestamp": "2024-06-15T10:05:00"},
    ]
    f = tmp_path / "test.log.jsonl"
    f.write_text("\n".join(json.dumps(log) for log in logs), encoding="utf-8")
    return f


@pytest.fixture
def loguru_file(tmp_path: Path) -> Path:
    records = [
        {
            "text": "msg",
            "record": {
                "time": {"repr": "2024-06-15T10:00:00"},
                "level": {"name": "INFO"},
                "message": "started",
                "extra": {"logger_name": "core", "request_id": 42},
                "file": {"name": "main.py"},
                "function": "run",
                "line": 10,
            },
        },
    ]
    f = tmp_path / "loguru.log.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    return f


@pytest.fixture
def duration_logs() -> list[dict[str, object]]:
    return [
        {
            "level": "INFO",
            "message": "op1 done",
            "operation": "encode",
            "duration_ms": 100.0,
            "timestamp": "2024-06-15T10:00:00",
        },
        {
            "level": "INFO",
            "message": "op2 done",
            "operation": "encode",
            "duration_ms": 200.0,
            "timestamp": "2024-06-15T11:00:00",
        },
        {
            "level": "INFO",
            "message": "op3 done",
            "operation": "parse",
            "duration_ms": 50.0,
            "timestamp": "2024-06-15T10:00:00",
        },
        {
            "level": "ERROR",
            "message": "op4 fail",
            "operation": "parse",
            "duration_ms": 300.0,
            "timestamp": "2024-06-16T10:00:00",
        },
    ]


class TestLogReaderLoad:
    def test_load_simple_jsonl(self, log_file: Path) -> None:
        reader = LogReader(log_file)
        logs = reader.load().to_list()
        assert len(logs) == 6

    def test_load_loguru_format(self, loguru_file: Path) -> None:
        reader = LogReader(loguru_file)
        logs = reader.load().to_list()
        assert len(logs) == 1
        assert logs[0]["level"] == "INFO"
        assert logs[0]["message"] == "started"
        assert logs[0]["request_id"] == 42

    def test_load_nonexistent_file(self, tmp_path: Path) -> None:
        reader = LogReader(tmp_path / "nope.log")
        logs = reader.load().to_list()
        assert logs == []

    def test_load_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.log"
        f.write_text("", encoding="utf-8")
        logs = LogReader(f).load().to_list()
        assert logs == []

    def test_load_skips_invalid_json(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.log"
        f.write_text('{"level":"INFO","message":"ok"}\nNOT_JSON\n', encoding="utf-8")
        logs = LogReader(f).load().to_list()
        assert len(logs) == 1


class TestLogReaderFilters:
    def test_filter_by_level(self, log_file: Path) -> None:
        errors = LogReader(log_file).load().filter_by_level("ERROR").to_list()
        assert len(errors) == 2

    def test_filter_by_levels(self, log_file: Path) -> None:
        results = LogReader(log_file).load().filter_by_levels(["ERROR", "WARNING"]).to_list()
        assert len(results) == 3

    def test_filter_by_logger_partial(self, log_file: Path) -> None:
        results = LogReader(log_file).load().filter_by_logger("db").to_list()
        assert len(results) == 2

    def test_filter_by_logger_exact(self, log_file: Path) -> None:
        results = LogReader(log_file).load().filter_by_logger("db", partial=False).to_list()
        assert len(results) == 2

    def test_filter_by_message(self, log_file: Path) -> None:
        results = LogReader(log_file).load().filter_by_message("timeout").to_list()
        assert len(results) == 1

    def test_filter_by_message_case_sensitive(self, log_file: Path) -> None:
        results = LogReader(log_file).load().filter_by_message("ERROR", case_sensitive=True).to_list()
        assert len(results) == 0

    def test_filter_by_context_key_exists(self, loguru_file: Path) -> None:
        results = LogReader(loguru_file).load().filter_by_context("request_id").to_list()
        assert len(results) == 1

    def test_filter_by_context_key_value(self, loguru_file: Path) -> None:
        results = LogReader(loguru_file).load().filter_by_context("request_id", 42).to_list()
        assert len(results) == 1

    def test_filter_by_context_key_missing(self, loguru_file: Path) -> None:
        results = LogReader(loguru_file).load().filter_by_context("nope").to_list()
        assert len(results) == 0

    def test_chained_filters(self, log_file: Path) -> None:
        results = LogReader(log_file).load().filter_by_level("ERROR").filter_by_logger("api").to_list()
        assert len(results) == 1
        assert results[0]["message"] == "timeout error"


class TestLogReaderTerminals:
    def test_count(self, log_file: Path) -> None:
        assert LogReader(log_file).load().count() == 6

    def test_first(self, log_file: Path) -> None:
        first = LogReader(log_file).load().first(2)
        assert len(first) == 2
        assert first[0]["message"] == "app started"

    def test_last(self, log_file: Path) -> None:
        last = LogReader(log_file).load().last(1)
        assert len(last) == 1
        assert last[0]["message"] == "timeout error"

    def test_last_zero(self, log_file: Path) -> None:
        assert LogReader(log_file).load().last(0) == []

    def test_reset(self, log_file: Path) -> None:
        reader = LogReader(log_file).load()
        reader.filter_by_level("ERROR")
        assert reader.count() == 2
        reader.reset()
        assert reader.count() == 6


class TestLogReaderFilterByTime:
    def test_filter_by_time_range(self, log_file: Path) -> None:
        results = (
            LogReader(log_file)
            .load()
            .filter_by_time(
                start=datetime(2024, 6, 15, 10, 1),
                end=datetime(2024, 6, 15, 10, 3),
            )
            .to_list()
        )
        assert len(results) == 3

    def test_filter_no_start_end_returns_all(self, log_file: Path) -> None:
        results = LogReader(log_file).load().filter_by_time().to_list()
        assert len(results) == 6


class TestLogAggregator:
    def test_count_by_level(self, log_file: Path) -> None:
        logs = LogReader(log_file).load().to_list()
        agg = LogAggregator(logs)
        counts = agg.count_by_level()
        assert counts["ERROR"] == 2
        assert counts["INFO"] == 2

    def test_count_by_logger(self, log_file: Path) -> None:
        logs = LogReader(log_file).load().to_list()
        agg = LogAggregator(logs)
        counts = agg.count_by_logger()
        assert counts["db"] == 2
        assert counts["api"] == 2

    def test_count_by_hour(self, log_file: Path) -> None:
        logs = LogReader(log_file).load().to_list()
        agg = LogAggregator(logs)
        counts = agg.count_by_hour()
        assert "2024-06-15 10:00" in counts
        assert counts["2024-06-15 10:00"] == 6

    def test_count_by_day(self, log_file: Path) -> None:
        logs = LogReader(log_file).load().to_list()
        agg = LogAggregator(logs)
        counts = agg.count_by_day()
        assert counts["2024-06-15"] == 6

    def test_avg_duration(self, duration_logs: list[dict[str, object]]) -> None:
        agg = LogAggregator(duration_logs)
        avg = agg.avg_duration()
        assert avg == pytest.approx(162.5)

    def test_avg_duration_by_operation(self, duration_logs: list[dict[str, object]]) -> None:
        agg = LogAggregator(duration_logs)
        assert agg.avg_duration("encode") == pytest.approx(150.0)
        assert agg.avg_duration("parse") == pytest.approx(175.0)

    def test_avg_duration_no_data(self) -> None:
        agg = LogAggregator([])
        assert agg.avg_duration() == 0.0

    def test_max_duration(self, duration_logs: list[dict[str, object]]) -> None:
        agg = LogAggregator(duration_logs)
        assert agg.max_duration() == 300.0
        assert agg.max_duration("encode") == 200.0

    def test_min_duration(self, duration_logs: list[dict[str, object]]) -> None:
        agg = LogAggregator(duration_logs)
        assert agg.min_duration() == 50.0
        assert agg.min_duration("encode") == 100.0

    def test_operations_summary(self, duration_logs: list[dict[str, object]]) -> None:
        agg = LogAggregator(duration_logs)
        summary = agg.operations_summary()
        assert "encode" in summary
        assert summary["encode"]["count"] == 2
        assert summary["encode"]["avg_ms"] == pytest.approx(150.0)

    def test_error_summary(self, log_file: Path) -> None:
        logs = LogReader(log_file).load().to_list()
        agg = LogAggregator(logs)
        err = agg.error_summary()
        assert err["total_errors"] == 2
        assert err["unique_messages"] == 2

    def test_timeline_hour(self, duration_logs: list[dict[str, object]]) -> None:
        agg = LogAggregator(duration_logs)
        timeline = agg.timeline("hour")
        assert len(timeline) >= 1
        assert "time" in timeline[0]

    def test_timeline_day(self, duration_logs: list[dict[str, object]]) -> None:
        agg = LogAggregator(duration_logs)
        timeline = agg.timeline("day")
        assert len(timeline) >= 1

    def test_empty_logs(self) -> None:
        agg = LogAggregator([])
        assert agg.count_by_level() == {}
        assert agg.count_by_logger() == {}
        assert agg.count_by_hour() == {}
        assert agg.count_by_day() == {}
        assert agg.operations_summary() == {}
        assert agg.timeline() == []
