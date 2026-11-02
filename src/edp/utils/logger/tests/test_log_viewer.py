from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from .. import log_viewer as _log_viewer_mod
from ..log_viewer import LogViewer

_LV_CONSOLE = f"{_log_viewer_mod.__name__}.console"

SAMPLE_LOGS: list[dict[str, Any]] = [
    {"level": "INFO", "message": "started", "logger": "core", "timestamp": "2024-06-15T10:00:00"},
    {"level": "ERROR", "message": "crash", "logger": "db", "timestamp": "2024-06-15T10:01:00"},
    {"level": "WARNING", "message": "slow", "logger": "api", "timestamp": "2024-06-15T10:02:00"},
]


class TestLogViewerDisplay:
    @patch(_LV_CONSOLE)
    def test_display_empty(self, mock_console: MagicMock) -> None:
        viewer = LogViewer()
        viewer.display([])
        mock_console.print.assert_called_once()
        assert "No logs" in mock_console.print.call_args[0][0]

    @patch(_LV_CONSOLE)
    def test_display_logs(self, mock_console: MagicMock) -> None:
        viewer = LogViewer()
        viewer.display(SAMPLE_LOGS)
        assert mock_console.print.call_count == 3

    @patch(_LV_CONSOLE)
    def test_display_with_context(self, mock_console: MagicMock) -> None:
        logs = [{"level": "INFO", "message": "test", "context": {"key": "val"}, "timestamp": ""}]
        viewer = LogViewer()
        viewer.display(logs, show_context=True)
        output = mock_console.print.call_args[0][0]
        assert "key=val" in output


class TestLogViewerTable:
    @patch(_LV_CONSOLE)
    def test_display_table_empty(self, mock_console: MagicMock) -> None:
        viewer = LogViewer()
        viewer.display_table([])
        assert "No logs" in mock_console.print.call_args[0][0]

    @patch(_LV_CONSOLE)
    def test_display_table(self, mock_console: MagicMock) -> None:
        viewer = LogViewer()
        viewer.display_table(SAMPLE_LOGS)
        mock_console.print.assert_called_once()


class TestLogViewerStats:
    @patch(_LV_CONSOLE)
    def test_display_with_stats(self, mock_console: MagicMock) -> None:
        viewer = LogViewer()
        viewer.display_with_stats(SAMPLE_LOGS)
        assert mock_console.print.call_count >= 4

    @patch(_LV_CONSOLE)
    def test_display_stats_only(self, mock_console: MagicMock) -> None:
        viewer = LogViewer()
        stats = {"total": 5, "by_level": {"INFO": 3, "ERROR": 2}}
        viewer.display_stats(stats)
        mock_console.print.assert_called_once()

    def test_calculate_stats(self) -> None:
        viewer = LogViewer()
        stats = viewer._calculate_stats(SAMPLE_LOGS)
        assert stats["total"] == 3
        assert stats["by_level"]["INFO"] == 1
        assert stats["by_level"]["ERROR"] == 1

    def test_calculate_stats_empty(self) -> None:
        viewer = LogViewer()
        stats = viewer._calculate_stats([])
        assert stats["total"] == 0


class TestLogViewerFormatting:
    def test_format_timestamp_valid(self) -> None:
        viewer = LogViewer()
        result = viewer._format_timestamp("2024-06-15T10:30:45.123456")
        assert "10:30:45" in result

    def test_format_timestamp_empty(self) -> None:
        viewer = LogViewer()
        assert viewer._format_timestamp("") == ""

    def test_format_timestamp_invalid(self) -> None:
        viewer = LogViewer()
        assert viewer._format_timestamp("not_a_date") == "not_a_date"
