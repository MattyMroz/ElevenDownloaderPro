"""Chain-able log reader with fluent API."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from .._time_helpers import filter_logs_by_time, resolve_time_window
from ..log_reader import LogReader as SimpleLogReader

if TYPE_CHECKING:
    from datetime import datetime

__all__ = ["LogReader"]


class LogReader:
    r"""Chain-able log reader with fluent API.

    Provide method chaining similar to pandas for filtering and querying logs.

    Example:
        >>> reader = LogReader("logs/app.log.jsonl")
        >>> errors = (
        ...     reader.load()
        ...     .filter_by_level("ERROR")
        ...     .filter_by_time(hours=1)
        ...     .to_list()
        ... )
        >>> warnings = reader.reset().filter_by_level("WARNING").count()
    """

    def __init__(self, log_file: Path | str) -> None:
        """Initialize reader.

        Args:
            log_file: Path to JSONL log file.
        """
        self._file = Path(log_file)
        self._all_logs: list[dict[str, Any]] = []
        self._current: list[dict[str, Any]] = []

    def load(self) -> LogReader:
        """Load logs from file.

        Returns:
            Self for chaining.
        """
        self._all_logs = SimpleLogReader(self._file).read_all()
        self._current = self._all_logs
        return self

    def filter_by_level(self, level: str) -> LogReader:
        """Filter by log level (chain-able).

        Args:
            level: Log level.

        Returns:
            Self for chaining.
        """
        self._current = [log for log in self._current if log.get("level", "").upper() == level.upper()]
        return self

    def filter_by_levels(self, levels: list[str]) -> LogReader:
        """Filter by multiple levels (chain-able).

        Args:
            levels: List of log levels.

        Returns:
            Self for chaining.
        """
        upper_levels = [level.upper() for level in levels]
        self._current = [log for log in self._current if log.get("level", "").upper() in upper_levels]
        return self

    def filter_by_time(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        minutes: int | None = None,
        hours: int | None = None,
        days: int | None = None,
    ) -> LogReader:
        """Filter by time range (chain-able).

        Args:
            start: Start datetime (optional).
            end: End datetime (optional).
            minutes: Last N minutes (shortcut).
            hours: Last N hours (shortcut).
            days: Last N days (shortcut).

        Returns:
            Self for chaining.

        Example:
            >>> reader.filter_by_time(hours=1)  # Last hour
            >>> reader.filter_by_time(start=datetime(...), end=datetime(...))
        """
        start, end = resolve_time_window(start, end, minutes, hours, days)
        self._current = filter_logs_by_time(self._current, start, end)
        return self

    def filter_by_logger(self, logger_name: str, partial: bool = True) -> LogReader:
        """Filter by logger name (chain-able).

        Args:
            logger_name: Logger name to filter.
            partial: Allow partial matches.

        Returns:
            Self for chaining.
        """
        if partial:
            self._current = [log for log in self._current if logger_name.lower() in log.get("logger", "").lower()]
        else:
            self._current = [log for log in self._current if log.get("logger", "") == logger_name]
        return self

    def filter_by_message(self, search: str, case_sensitive: bool = False) -> LogReader:
        """Filter by message content (chain-able).

        Args:
            search: Search string.
            case_sensitive: Case sensitive search.

        Returns:
            Self for chaining.
        """
        if case_sensitive:
            self._current = [log for log in self._current if search in log.get("message", "")]
        else:
            search_lower = search.lower()
            self._current = [log for log in self._current if search_lower in log.get("message", "").lower()]
        return self

    def filter_by_context(self, key: str, value: Any | None = None) -> LogReader:
        """Filter by context field (chain-able).

        Args:
            key: Context key to check.
            value: Expected value (None checks key existence only).

        Returns:
            Self for chaining.
        """
        if value is None:
            self._current = [log for log in self._current if key in log]
        else:
            self._current = [log for log in self._current if log.get(key) == value]
        return self

    def to_list(self) -> list[dict[str, Any]]:
        """Return current filtered logs as list (terminal).

        Returns:
            List of log dictionaries.
        """
        return self._current

    def count(self) -> int:
        """Count filtered logs (terminal).

        Returns:
            Number of logs.
        """
        return len(self._current)

    def first(self, n: int = 1) -> list[dict[str, Any]]:
        """Get first N logs (terminal).

        Args:
            n: Number of logs to return.

        Returns:
            First N logs.
        """
        return self._current[:n]

    def last(self, n: int = 1) -> list[dict[str, Any]]:
        """Get last N logs (terminal).

        Args:
            n: Number of logs to return.

        Returns:
            Last N logs.
        """
        return self._current[-n:] if n > 0 else []

    def reset(self) -> LogReader:
        """Reset filters (back to all logs).

        Returns:
            Self for chaining.
        """
        self._current = self._all_logs
        return self

    def to_dataframe(self) -> Any:
        """Export to pandas DataFrame (optional).

        Returns:
            pandas DataFrame with log entries.

        Raises:
            ImportError: If pandas is not installed.
        """
        try:
            import pandas as pd  # type: ignore[import-untyped]

            return pd.DataFrame(self._current)
        except ImportError as e:
            msg = "pandas not installed. Install with: uv add pandas"
            raise ImportError(msg) from e
