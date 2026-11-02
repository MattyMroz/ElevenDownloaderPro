from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from ..log_reader import LogReader

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def log_file(tmp_path: Path) -> Path:
    logs = [
        {"level": "INFO", "message": "boot", "logger": "core", "timestamp": "2024-06-15T10:00:00"},
        {"level": "DEBUG", "message": "detail", "logger": "core", "timestamp": "2024-06-15T10:01:00"},
        {"level": "ERROR", "message": "crash", "logger": "db", "timestamp": "2024-06-15T10:02:00"},
        {"level": "WARNING", "message": "slow", "logger": "api", "timestamp": "2024-06-15T10:03:00"},
        {"level": "INFO", "message": "ok stuff", "logger": "api", "timestamp": "2024-06-15T10:04:00"},
    ]
    f = tmp_path / "simple.log.jsonl"
    f.write_text("\n".join(json.dumps(log) for log in logs), encoding="utf-8")
    return f


class TestSimpleLogReader:
    def test_read_all(self, log_file: Path) -> None:
        reader = LogReader(log_file)
        logs = reader.read_all()
        assert len(logs) == 5

    def test_read_nonexistent(self, tmp_path: Path) -> None:
        reader = LogReader(tmp_path / "nope.log")
        assert reader.read_all() == []

    def test_filter_by_level(self, log_file: Path) -> None:
        reader = LogReader(log_file)
        errors = reader.filter_by_level("ERROR")
        assert len(errors) == 1
        assert errors[0]["message"] == "crash"

    def test_filter_by_levels(self, log_file: Path) -> None:
        reader = LogReader(log_file)
        results = reader.filter_by_levels(["ERROR", "WARNING"])
        assert len(results) == 2

    def test_filter_by_logger(self, log_file: Path) -> None:
        reader = LogReader(log_file)
        results = reader.filter_by_logger("api")
        assert len(results) == 2

    def test_filter_by_message(self, log_file: Path) -> None:
        reader = LogReader(log_file)
        results = reader.filter_by_message("slow")
        assert len(results) == 1

    def test_filter_by_message_case_sensitive(self, log_file: Path) -> None:
        reader = LogReader(log_file)
        results = reader.filter_by_message("CRASH", case_sensitive=True)
        assert len(results) == 0

    def test_get_field(self, log_file: Path) -> None:
        reader = LogReader(log_file)
        levels = reader.get_field("level")
        assert len(levels) == 5
        assert "INFO" in levels

    def test_get_recent(self, log_file: Path) -> None:
        reader = LogReader(log_file)
        recent = reader.get_recent(2)
        assert len(recent) == 2
        assert recent[0]["message"] == "ok stuff"

    def test_get_stats(self, log_file: Path) -> None:
        reader = LogReader(log_file)
        stats = reader.get_stats()
        assert stats["total"] == 5
        assert stats["by_level"]["INFO"] == 2
        assert stats["by_logger"]["core"] == 2

    def test_filter_by_time_no_range_returns_all(self, log_file: Path) -> None:
        reader = LogReader(log_file)
        reader.read_all()
        results = reader.filter_by_time()
        assert len(results) == 5

    def test_skips_invalid_json(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.log"
        f.write_text('{"level":"OK"}\nBAD_LINE\n', encoding="utf-8")
        reader = LogReader(f)
        assert len(reader.read_all()) == 1
