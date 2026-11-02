"""Rich console handler for loguru sink.

Use ``rich_console`` theme styles for consistent log formatting:
- Icons from ``get_status_icon()``.
- Styles from ``RICH_THEME`` (``log.time``, ``logging.level.*``).
- Smart auto-highlighting via ``console.print(highlight=True)``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from rich.cells import cell_len

if TYPE_CHECKING:
    from datetime import datetime

from ...rich_console import console
from ...rich_console.utilities import StatusType, get_status_icon
from ..config import ConsoleConfig

__all__ = ["RichHandler"]


class RichHandler:
    """Loguru sink using Rich console."""

    def __init__(self, config: ConsoleConfig | None = None) -> None:
        """Initialize handler.

        Args:
            config: Console display configuration.
        """
        self._config: ConsoleConfig = config or ConsoleConfig()

    def write(self, message: Any) -> None:
        """Write log record to Rich console.

        Args:
            message: Loguru message object with ``.record`` dict.
        """
        record: dict[str, Any] = message.record
        formatted: str = self._build_message(record)
        console.print(formatted, highlight=True)

    def _build_message(self, record: dict[str, Any]) -> str:
        """Build formatted log message with Rich markup.

        Returns:
            Formatted string with Rich tags for time/level/logger, plain text for message.
        """
        parts: list[str] = []

        if self._config.show_time:
            parts.append(self._format_time(record["time"]))

        if self._config.show_level:
            parts.append(self._format_level(record["level"].name))

        extra: dict[str, Any] = record.get("extra", {})
        logger_name: str = extra.get("logger_name", "")
        if self._config.show_logger_name and logger_name:
            styled_name = f"[{self._config.logger_name_style}]{logger_name}[/{self._config.logger_name_style}]"
            parts.append(styled_name)

        if self._config.show_location:
            file_info = record.get("file")
            file_name = file_info.name if file_info else "unknown"
            line_num = record.get("line", "?")
            location = f"[{self._config.location_style}]{file_name}:{line_num}[/{self._config.location_style}]"
            parts.append(location)

        sep = f"[{self._config.separator_style}]{self._config.separator}[/{self._config.separator_style}]"

        parts.append(record["message"])

        if self._config.show_context:
            context_parts: list[str] = [f"{k}={v}" for k, v in extra.items() if k != "logger_name"]
            if context_parts:
                parts.append(" ".join(context_parts))

        return sep.join(parts)

    def _format_time(self, timestamp: datetime) -> str:
        """Format timestamp with style from config.

        Args:
            timestamp: Log timestamp.

        Returns:
            Formatted time with Rich markup.
        """
        if self._config.time_format == "HH:MM:SS.ms":
            time_str = timestamp.strftime("%H:%M:%S.%f")[:-3]
        elif self._config.time_format == "HH:MM:SS":
            time_str = timestamp.strftime("%H:%M:%S")
        elif self._config.time_format == "ISO8601":
            time_str = timestamp.isoformat()
        else:
            time_str = str(int(timestamp.timestamp()))

        if self._config.show_date and self._config.time_format != "ISO8601":
            date_str = timestamp.strftime("%Y-%m-%d")
            time_str = f"{date_str} {time_str}"

        if self._config.time_width:
            time_str = f"{time_str:<{self._config.time_width}}"

        return f"[{self._config.time_style}]{time_str}[/{self._config.time_style}]"

    def _format_level(self, level: str) -> str:
        """Format level with icon and color from RICH_THEME.

        Args:
            level: Log level name.

        Returns:
            Formatted level with icon and Rich markup.
        """
        style = f"logging.level.{level.lower()}" if self._config.level_style == "auto" else self._config.level_style

        level_text = level
        if self._config.show_icons:
            status = cast("StatusType", level.lower())
            icon = get_status_icon(status, with_style=False)
            level_text = f"{icon} {level}"

        if self._config.level_width:
            current_width = cell_len(level_text)
            if current_width < self._config.level_width:
                level_text = level_text + " " * (self._config.level_width - current_width)

        return f"[{style}]{level_text}[/{style}]"
