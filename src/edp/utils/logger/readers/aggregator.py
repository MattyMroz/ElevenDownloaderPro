"""Log aggregation utilities for analysis."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

__all__ = ["LogAggregator"]


class LogAggregator:
    """Aggregation utilities for log analysis.

    Example:
        >>> from logger.readers import LogReader, LogAggregator
        >>> reader = LogReader("logs/app.log.jsonl")
        >>> logs = reader.load().to_list()
        >>> agg = LogAggregator(logs)
        >>> print(agg.count_by_level())
        >>> print(agg.avg_duration())
    """

    def __init__(self, logs: list[dict[str, Any]]) -> None:
        """Initialize aggregator.

        Args:
            logs: List of log dictionaries.
        """
        self._logs = logs

    def count_by_level(self) -> dict[str, int]:
        """Count logs by level.

        Returns:
            Dictionary mapping level to count.
        """
        return dict(Counter(log.get("level", "UNKNOWN") for log in self._logs))

    def count_by_logger(self) -> dict[str, int]:
        """Count logs by logger name.

        Returns:
            Dictionary mapping logger to count.
        """
        return dict(Counter(log.get("logger", "unknown") for log in self._logs))

    def count_by_hour(self) -> dict[str, int]:
        """Count logs grouped by hour.

        Returns:
            Dictionary mapping hour (YYYY-MM-DD HH:00) to count.
        """
        hours = []
        for log in self._logs:
            timestamp_str = log.get("timestamp")
            if not timestamp_str:
                continue
            try:
                ts = datetime.fromisoformat(timestamp_str)
                hours.append(ts.strftime("%Y-%m-%d %H:00"))
            except ValueError, TypeError:
                continue
        return dict(Counter(hours))

    def count_by_day(self) -> dict[str, int]:
        """Count logs grouped by day.

        Returns:
            Dictionary mapping day (YYYY-MM-DD) to count.
        """
        days = []
        for log in self._logs:
            timestamp_str = log.get("timestamp")
            if not timestamp_str:
                continue
            try:
                ts = datetime.fromisoformat(timestamp_str)
                days.append(ts.strftime("%Y-%m-%d"))
            except ValueError, TypeError:
                continue
        return dict(Counter(days))

    def avg_duration(self, operation: str | None = None) -> float:
        """Compute average duration_ms for operations.

        Args:
            operation: Filter by operation name.

        Returns:
            Average duration in milliseconds.
        """
        durations = []
        for log in self._logs:
            if "duration_ms" not in log:
                continue
            if operation and log.get("operation") != operation:
                continue
            durations.append(log["duration_ms"])

        return sum(durations) / len(durations) if durations else 0.0

    def max_duration(self, operation: str | None = None) -> float:
        """Compute maximum duration_ms for operations.

        Args:
            operation: Filter by operation name.

        Returns:
            Maximum duration in milliseconds.
        """
        durations = []
        for log in self._logs:
            if "duration_ms" not in log:
                continue
            if operation and log.get("operation") != operation:
                continue
            durations.append(log["duration_ms"])

        return max(durations) if durations else 0.0

    def min_duration(self, operation: str | None = None) -> float:
        """Compute minimum duration_ms for operations.

        Args:
            operation: Filter by operation name.

        Returns:
            Minimum duration in milliseconds.
        """
        durations = []
        for log in self._logs:
            if "duration_ms" not in log:
                continue
            if operation and log.get("operation") != operation:
                continue
            durations.append(log["duration_ms"])

        return min(durations) if durations else 0.0

    def operations_summary(self) -> dict[str, dict[str, Any]]:
        """Compute summary statistics for all operations.

        Returns:
            Dictionary mapping operation name to statistics.
        """
        ops = defaultdict(list)
        for log in self._logs:
            if "duration_ms" not in log or "operation" not in log:
                continue
            ops[log["operation"]].append(log["duration_ms"])

        summary = {}
        for op_name, durations in ops.items():
            summary[op_name] = {
                "count": len(durations),
                "avg_ms": round(sum(durations) / len(durations), 3),
                "min_ms": round(min(durations), 3),
                "max_ms": round(max(durations), 3),
                "total_ms": round(sum(durations), 3),
            }

        return summary

    def error_summary(self) -> dict[str, Any]:
        """Compute summary of errors by logger.

        Returns:
            Dictionary with error statistics.
        """
        errors = [log for log in self._logs if log.get("level") == "ERROR"]

        return {
            "total_errors": len(errors),
            "by_logger": dict(Counter(log.get("logger", "unknown") for log in errors)),
            "unique_messages": len({log.get("message", "") for log in errors}),
        }

    def timeline(self, interval: str = "hour") -> list[dict[str, Any]]:
        """Generate timeline data for visualization.

        Args:
            interval: Time interval ('hour' or 'day').

        Returns:
            List of timeline points with counts by level.
        """
        timeline_data: defaultdict[str, defaultdict[str, int]] = defaultdict(lambda: defaultdict(int))

        for log in self._logs:
            timestamp_str = log.get("timestamp")
            if not timestamp_str:
                continue

            try:
                ts = datetime.fromisoformat(timestamp_str)
                bucket = ts.strftime("%Y-%m-%d %H:00") if interval == "hour" else ts.strftime("%Y-%m-%d")
                level = log.get("level", "UNKNOWN")
                timeline_data[bucket][level] += 1
            except ValueError, TypeError:
                continue

        result = []
        for bucket, levels in sorted(timeline_data.items()):
            point: dict[str, Any] = {"time": bucket}
            point.update(levels)
            result.append(point)

        return result
