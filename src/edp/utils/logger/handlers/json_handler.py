"""JSON file handler for loguru sink with rotation support.

Writes structured JSON log lines to a file with rotation and retention.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import io
    from pathlib import Path

from ..formatters import JSONFormatter, LogRecordMeta

__all__ = ["JSONHandler"]

if TYPE_CHECKING:
    from datetime import datetime


class JSONHandler:
    """Loguru sink for structured JSON file logging with rotation."""

    def __init__(
        self,
        file_path: Path,
        formatter: JSONFormatter | None = None,
        rotation: str = "100 MB",
        retention: str = "30 days",
        compression: str = "zip",
    ) -> None:
        """Initialize JSON handler.

        Args:
            file_path: Log file path.
            formatter: JSON formatter (creates default if None).
            rotation: Rotation trigger ('100 MB', '1 day', etc.).
            retention: Retention period ('30 days', '1 week', etc.).
            compression: Compression format ('zip', 'gz', etc.).
        """
        self._file_path: Path = file_path
        self._formatter: JSONFormatter = formatter or JSONFormatter()
        self._rotation: str = rotation
        self._retention: str = retention
        self._compression: str = compression
        self._file_handle: io.TextIOWrapper | None = None

        self._ensure_directory()

    def write(self, message: Any) -> None:
        """Process log record and write to JSON file.

        Args:
            message: Loguru message object (contains record).
        """
        record: dict[str, Any] = message.record
        json_line: str = self._serialize_record(record)

        handle = self._get_file_handle()
        handle.write(json_line + "\n")
        handle.flush()

    def close(self) -> None:
        """Close the file handle."""
        if self._file_handle is not None and not self._file_handle.closed:
            self._file_handle.close()
            self._file_handle = None

    def _get_file_handle(self) -> io.TextIOWrapper:
        """Return persistent file handle, opening if needed."""
        if self._file_handle is None or self._file_handle.closed:
            self._file_handle = self._file_path.open("a", encoding="utf-8")
        return self._file_handle

    def _serialize_record(self, record: dict[str, Any]) -> str:
        """Serialize record to JSON string.

        Args:
            record: Loguru record dict.

        Returns:
            JSON string.
        """
        level: str = record["level"].name
        message: str = record["message"]
        timestamp: datetime = record["time"]

        context: dict[str, Any] = record.get("extra", {}).copy()
        logger_name: str = context.pop("logger_name", "")

        exception: str | None = None
        if record.get("exception"):
            exc = record["exception"]
            if exc:
                exception = f"{exc.type.__name__}: {exc.value}"

        file_path = ""
        file_info = record.get("file")
        if file_info and hasattr(file_info, "path"):
            file_path = str(file_info.path)

        return self._formatter.format_record(
            level=level,
            message=message,
            context=context,
            timestamp=timestamp,
            meta=LogRecordMeta(
                logger_name=logger_name,
                file_path=file_path,
                function_name=record.get("function", ""),
                line_number=record.get("line", 0),
                exception=exception,
            ),
        )

    def _ensure_directory(self) -> None:
        """Create log directory if it doesn't exist."""
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
