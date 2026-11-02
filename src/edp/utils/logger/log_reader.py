"""Simple log reader for CLI and quick queries.

For the chain-able fluent API, use ``readers.LogReader`` instead.

Example:
    >>> from logger.log_reader import LogReader
    >>> reader = LogReader("logs/app.log")
    >>> logs = reader.read_all()
    >>> errors = reader.filter_by_level("ERROR")
    >>> recent = reader.filter_by_time(minutes=30)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ._time_helpers import filter_logs_by_time, resolve_time_window

if TYPE_CHECKING:
    from datetime import datetime

__all__ = ["LogReader"]


class LogReader:
    """Simple JSON log reader with filtering capabilities.

    Attributes:
        log_file: Path to the JSON log file.
    """

    def __init__(self, log_file: str | Path) -> None:
        """Initialize log reader.

        Args:
            log_file: Path to JSON log file.
        """
        self.log_file = Path(log_file)
        self._logs: list[dict[str, Any]] = []

    def read_all(self) -> list[dict[str, Any]]:
        """Read all logs from file.

        Returns:
            List of log dictionaries.
        """
        self._logs = []

        if not self.log_file.exists():
            return self._logs

        with self.log_file.open(encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue

                try:
                    log: object = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(log, dict):
                    record: object = log.get("record")
                    self._logs.append(_flatten_loguru_record(record) if isinstance(record, dict) else log)

        return self._logs

    def filter_by_level(self, level: str) -> list[dict[str, Any]]:
        """Filter logs by level.

        Args:
            level: Log level.

        Returns:
            Filtered logs.
        """
        if not self._logs:
            self.read_all()

        return [log for log in self._logs if log.get("level") == level.upper()]

    def filter_by_levels(self, levels: list[str]) -> list[dict[str, Any]]:
        """Filter logs by multiple levels.

        Args:
            levels: List of log levels.

        Returns:
            Filtered logs.
        """
        if not self._logs:
            self.read_all()

        upper_levels = [level.upper() for level in levels]
        return [log for log in self._logs if log.get("level") in upper_levels]

    def filter_by_time(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        minutes: int | None = None,
        hours: int | None = None,
    ) -> list[dict[str, Any]]:
        """Filter logs by time range.

        Args:
            start: Start datetime (inclusive).
            end: End datetime (inclusive).
            minutes: Last N minutes (relative).
            hours: Last N hours (relative).

        Returns:
            Filtered logs.
        """
        if not self._logs:
            self.read_all()

        start, end = resolve_time_window(start, end, minutes, hours)
        return filter_logs_by_time(self._logs, start, end)

    def filter_by_logger(self, logger_name: str) -> list[dict[str, Any]]:
        """Filter logs by logger name.

        Args:
            logger_name: Logger name (can be partial match).

        Returns:
            Filtered logs.
        """
        if not self._logs:
            self.read_all()

        return [log for log in self._logs if logger_name.lower() in log.get("logger", "").lower()]

    def filter_by_message(self, search: str, case_sensitive: bool = False) -> list[dict[str, Any]]:
        """Filter logs by message content.

        Args:
            search: Search string.
            case_sensitive: Case-sensitive search.

        Returns:
            Filtered logs.
        """
        if not self._logs:
            self.read_all()

        if case_sensitive:
            return [log for log in self._logs if search in log.get("message", "")]
        search_lower = search.lower()
        return [log for log in self._logs if search_lower in log.get("message", "").lower()]

    def get_field(self, field: str) -> list[Any]:
        """Extract specific field from all logs.

        Args:
            field: Field name (e.g., 'message', 'level', 'logger').

        Returns:
            List of field values.
        """
        if not self._logs:
            self.read_all()

        return [log.get(field) for log in self._logs if field in log]

    def get_recent(self, count: int = 10) -> list[dict[str, Any]]:
        """Get N most recent logs.

        Args:
            count: Number of logs to return.

        Returns:
            Recent logs (newest first).
        """
        if not self._logs:
            self.read_all()

        return self._logs[-count:][::-1]

    def get_stats(self) -> dict[str, Any]:
        """Get log statistics.

        Returns:
            Statistics dictionary.
        """
        if not self._logs:
            self.read_all()

        level_counts: dict[str, int] = {}
        for log in self._logs:
            level = log.get("level", "UNKNOWN")
            level_counts[level] = level_counts.get(level, 0) + 1

        logger_counts: dict[str, int] = {}
        for log in self._logs:
            logger = log.get("logger", "unknown")
            logger_counts[logger] = logger_counts.get(logger, 0) + 1

        return {
            "total": len(self._logs),
            "by_level": level_counts,
            "by_logger": logger_counts,
        }


def _flatten_loguru_record(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize Loguru serialization to the flat fields used by both readers."""
    time_obj: object = record.get("time", {})
    level_obj: object = record.get("level", {})
    extra: object = record.get("extra", {})
    file_obj: object = record.get("file", {})
    flat_log: dict[str, Any] = {
        "timestamp": time_obj.get("repr", "") if isinstance(time_obj, dict) else str(time_obj),
        "level": level_obj.get("name", "") if isinstance(level_obj, dict) else str(level_obj),
        "logger": extra.get("logger_name", record.get("name", "")) if isinstance(extra, dict) else "",
        "message": record.get("message", ""),
        "file": file_obj.get("name", "") if isinstance(file_obj, dict) else "",
        "function": record.get("function", ""),
        "line": record.get("line", 0),
    }
    if isinstance(extra, dict):
        flat_log.update({key: value for key, value in extra.items() if key not in flat_log and key != "logger_name"})
    return flat_log
