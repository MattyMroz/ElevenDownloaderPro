from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

from .. import cli as _cli_mod
from ..cli import apply_filters, main, parse_args
from ..log_reader import LogReader

_CLI_CONSOLE = f"{_cli_mod.__name__}.console"
_CLI_VIEWER = f"{_cli_mod.__name__}.LogViewer"

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def log_file(tmp_path: Path) -> Path:
    p = tmp_path / "test.log.jsonl"
    entries: list[dict[str, Any]] = [
        {"level": "INFO", "message": "boot", "logger": "core", "timestamp": "2024-06-15T10:00:00"},
        {"level": "ERROR", "message": "db crash", "logger": "db", "timestamp": "2024-06-15T10:01:00"},
        {"level": "WARNING", "message": "slow query", "logger": "api", "timestamp": "2024-06-15T10:02:00"},
        {"level": "DEBUG", "message": "trace", "logger": "core", "timestamp": "2024-06-15T10:03:00"},
        {"level": "INFO", "message": "ready", "logger": "api", "timestamp": "2024-06-15T10:04:00"},
    ]
    p.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
    return p


class TestParseArgs:
    def test_empty(self) -> None:
        assert parse_args([]) == {}

    def test_recent(self) -> None:
        opts = parse_args(["--recent", "5"])
        assert opts["recent"] == 5

    def test_recent_short(self) -> None:
        opts = parse_args(["-n", "3"])
        assert opts["recent"] == 3

    def test_level(self) -> None:
        opts = parse_args(["--level", "ERROR"])
        assert opts["level"] == "ERROR"

    def test_level_short(self) -> None:
        opts = parse_args(["-l", "WARNING"])
        assert opts["level"] == "WARNING"

    def test_minutes(self) -> None:
        opts = parse_args(["--minutes", "30"])
        assert opts["minutes"] == 30

    def test_hours(self) -> None:
        opts = parse_args(["--hours", "2"])
        assert opts["hours"] == 2

    def test_logger(self) -> None:
        opts = parse_args(["--logger", "db"])
        assert opts["logger"] == "db"

    def test_search(self) -> None:
        opts = parse_args(["--search", "crash"])
        assert opts["search"] == "crash"

    def test_table_flag(self) -> None:
        opts = parse_args(["--table"])
        assert opts["table"] is True

    def test_stats_flag(self) -> None:
        opts = parse_args(["--stats"])
        assert opts["stats"] is True

    def test_combined(self) -> None:
        opts = parse_args(["--level", "ERROR", "--recent", "10", "--table"])
        assert opts == {"level": "ERROR", "recent": 10, "table": True}

    def test_unknown_ignored(self) -> None:
        opts = parse_args(["--unknown", "val"])
        assert "unknown" not in opts

    def test_missing_value_skipped(self) -> None:
        opts = parse_args(["--recent"])
        assert "recent" not in opts


class TestApplyFilters:
    def test_no_filters(self, log_file: Path) -> None:
        reader = LogReader(log_file)
        logs = apply_filters(reader, {})
        assert len(logs) == 5

    def test_level_filter(self, log_file: Path) -> None:
        reader = LogReader(log_file)
        logs = apply_filters(reader, {"level": "ERROR"})
        assert len(logs) == 1
        assert logs[0]["message"] == "db crash"

    def test_logger_filter(self, log_file: Path) -> None:
        reader = LogReader(log_file)
        logs = apply_filters(reader, {"logger": "core"})
        assert len(logs) == 2

    def test_search_filter(self, log_file: Path) -> None:
        reader = LogReader(log_file)
        logs = apply_filters(reader, {"search": "crash"})
        assert len(logs) == 1

    def test_recent_filter(self, log_file: Path) -> None:
        reader = LogReader(log_file)
        logs = apply_filters(reader, {"recent": 2})
        assert len(logs) == 2
        assert logs[0]["message"] == "ready"

    def test_combined_filters(self, log_file: Path) -> None:
        reader = LogReader(log_file)
        logs = apply_filters(reader, {"level": "INFO", "recent": 1})
        assert len(logs) == 1
        assert logs[0]["message"] == "ready"


class TestMain:
    @patch(_CLI_CONSOLE)
    def test_no_args_prints_help(self, mock_console: Any) -> None:
        with patch("sys.argv", ["cli"]):
            main()
        mock_console.print.assert_called()

    @patch(_CLI_CONSOLE)
    def test_help_flag(self, mock_console: Any) -> None:
        with patch("sys.argv", ["cli", "--help"]):
            main()
        mock_console.print.assert_called()

    @patch(_CLI_CONSOLE)
    def test_file_not_found(self, mock_console: Any) -> None:
        with patch("sys.argv", ["cli", "/nonexistent/file.log"]):
            main()
        call_str = str(mock_console.print.call_args)
        assert "not found" in call_str.lower() or "Error" in call_str

    @patch(_CLI_VIEWER)
    @patch(_CLI_CONSOLE)
    def test_display_default(self, _console: Any, mock_viewer_cls: Any, log_file: Path) -> None:
        mock_viewer = mock_viewer_cls.return_value
        with patch("sys.argv", ["cli", str(log_file)]):
            main()
        mock_viewer.display.assert_called_once()

    @patch(_CLI_VIEWER)
    @patch(_CLI_CONSOLE)
    def test_display_table(self, _console: Any, mock_viewer_cls: Any, log_file: Path) -> None:
        mock_viewer = mock_viewer_cls.return_value
        with patch("sys.argv", ["cli", str(log_file), "--table"]):
            main()
        mock_viewer.display_table.assert_called_once()

    @patch(_CLI_VIEWER)
    @patch(_CLI_CONSOLE)
    def test_display_stats(self, _console: Any, mock_viewer_cls: Any, log_file: Path) -> None:
        mock_viewer = mock_viewer_cls.return_value
        with patch("sys.argv", ["cli", str(log_file), "--stats"]):
            main()
        mock_viewer.display_with_stats.assert_called_once()
