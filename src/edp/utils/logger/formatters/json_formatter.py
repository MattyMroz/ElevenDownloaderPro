"""Structured JSON formatter for file logging.

Serializes log records to JSON format for machine-readable structured logging.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

__all__ = ["JSONFormatter", "LogRecordMeta"]

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True, slots=True)
class LogRecordMeta:
    """Optional metadata for a log record.

    Groups source-location and auxiliary fields that would otherwise
    inflate the ``format_record`` parameter list.

    Attributes:
        logger_name: Logger name.
        file_path: Source file path.
        function_name: Function name.
        line_number: Line number.
        exception: Exception traceback string.
    """

    logger_name: str = ""
    file_path: str = ""
    function_name: str = ""
    line_number: int = 0
    exception: str | None = None


_EMPTY_META: Final[LogRecordMeta] = LogRecordMeta()
"""Default empty metadata singleton (frozen, safe to share)."""


class JSONFormatter:
    """Structured JSON formatter for file logging."""

    def __init__(self, indent: int | None = None, ensure_ascii: bool = False) -> None:
        """Initialize JSON formatter.

        Args:
            indent: JSON indentation (None = compact).
            ensure_ascii: Whether to escape non-ASCII characters.
        """
        self._indent: int | None = indent
        self._ensure_ascii: bool = ensure_ascii

    def format_record(
        self,
        level: str,
        message: str,
        context: dict[str, Any],
        timestamp: datetime,
        meta: LogRecordMeta = _EMPTY_META,
    ) -> str:
        """Convert log record to JSON string.

        Args:
            level: Log level.
            message: Log message.
            context: Context metadata.
            timestamp: Log timestamp.
            meta: Optional record metadata (logger, location, exception).

        Returns:
            JSON string.
        """
        record: dict[str, Any] = {
            "timestamp": timestamp.isoformat(),
            "level": level,
            "message": message,
        }

        if meta.logger_name:
            record["logger"] = meta.logger_name

        if context:
            record["context"] = context

        if meta.file_path or meta.function_name or meta.line_number:
            record["location"] = {
                "file": meta.file_path,
                "function": meta.function_name,
                "line": meta.line_number,
            }

        if meta.exception:
            record["exception"] = meta.exception

        return json.dumps(
            record,
            indent=self._indent,
            ensure_ascii=self._ensure_ascii,
            default=str,
        )
