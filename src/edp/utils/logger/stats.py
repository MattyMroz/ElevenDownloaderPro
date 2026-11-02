"""Thread-safe logger statistics tracking for health monitoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Any

__all__ = ["LoggerStats", "get_logger_stats", "increment_stat", "reset_stats"]


@dataclass
class LoggerStats:
    """Thread-safe logger health statistics.

    Attributes:
        total_logged: Total number of logged messages.
        by_level: Message count per log level.
        by_logger: Message count per logger name.
        last_log_time: Timestamp of the most recent log entry.
        started_at: Timestamp when tracking started.

    Example:
        >>> stats = get_logger_stats()
        >>> print(f"Total logged: {stats.total_logged}")
        >>> print(f"By level: {stats.by_level}")
    """

    total_logged: int = 0
    by_level: dict[str, int] = field(default_factory=dict)
    by_logger: dict[str, int] = field(default_factory=dict)
    last_log_time: datetime | None = None
    started_at: datetime = field(default_factory=datetime.now)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def increment(self, level: str, logger_name: str | None = None) -> None:
        """Increment statistics (thread-safe).

        Args:
            level: Log level name.
            logger_name: Optional logger name.
        """
        with self._lock:
            self.total_logged += 1
            self.by_level[level] = self.by_level.get(level, 0) + 1
            if logger_name:
                self.by_logger[logger_name] = self.by_logger.get(logger_name, 0) + 1
            self.last_log_time = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Export statistics as dictionary.

        Returns:
            Dictionary with all statistics.
        """
        with self._lock:
            return {
                "total_logged": self.total_logged,
                "by_level": dict(self.by_level),
                "by_logger": dict(self.by_logger),
                "last_log_time": self.last_log_time.isoformat() if self.last_log_time else None,
                "started_at": self.started_at.isoformat(),
                "uptime_seconds": (datetime.now() - self.started_at).total_seconds(),
            }

    def reset(self) -> None:
        """Reset all statistics (thread-safe)."""
        with self._lock:
            self.total_logged = 0
            self.by_level.clear()
            self.by_logger.clear()
            self.last_log_time = None
            self.started_at = datetime.now()


_stats = LoggerStats()


def get_logger_stats() -> LoggerStats:
    """Return current logger statistics.

    Returns:
        LoggerStats instance with current statistics.

    Example:
        >>> stats = get_logger_stats()
        >>> print(stats.total_logged)
    """
    return _stats


def increment_stat(level: str, logger_name: str | None = None) -> None:
    """Increment statistics (called by sinks).

    Args:
        level: Log level name.
        logger_name: Optional logger name.
    """
    _stats.increment(level, logger_name)


def reset_stats() -> None:
    """Reset logger statistics.

    Useful for testing or resetting monitoring state.
    """
    _stats.reset()
