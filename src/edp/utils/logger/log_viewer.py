"""Display logs with Rich formatting using existing theme and console styles.

Example:
    >>> from logger.log_reader import LogReader
    >>> from logger.log_viewer import LogViewer
    >>> reader = LogReader("logs/app.log")
    >>> viewer = LogViewer()
    >>> viewer.display(reader.read_all())
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..rich_console import console
from ..rich_console.console import auto_highlight_text
from .handlers.console import _LEVEL_BADGE, _LEVEL_COLOR, _LEVEL_ICON, _show_icons

__all__ = ["LogViewer"]


class LogViewer:
    """Display logs with Rich formatting using existing styles."""

    def display(self, logs: list[dict[str, Any]], show_context: bool = True) -> None:
        """Display logs with Rich formatting.

        Args:
            logs: List of log dictionaries.
            show_context: Whether to show context metadata.
        """
        if not logs:
            console.print("[gray]No logs to display[/gray]")
            return

        for log in logs:
            self._display_log(log, show_context=show_context)

    def display_table(self, logs: list[dict[str, Any]]) -> None:
        """Display logs in table format.

        Args:
            logs: List of log dictionaries.
        """
        if not logs:
            console.print("[gray]No logs to display[/gray]")
            return

        table = Table(show_header=True, header_style="ruby_red_bold")
        table.add_column("Time", no_wrap=True)
        table.add_column("Level", no_wrap=True)
        table.add_column("Logger", no_wrap=True)
        table.add_column("Message")

        for log in logs:
            level = log.get("level", "INFO")
            color = _LEVEL_COLOR.get(level, "dodger_blue2")
            badge = _LEVEL_BADGE.get(level, "dodger_blue2 bold")
            timestamp = self._format_timestamp(log.get("timestamp", ""))
            logger_name = log.get("logger", "")
            message = log.get("message", "")

            msg = auto_highlight_text(message)
            msg.style = f"bold italic {color}"

            table.add_row(
                Text(timestamp, style=f"{color} italic"),
                Text(f"{level:<8}", style=badge),
                Text(logger_name, style=f"{color} italic"),
                msg,
            )

        console.print(table)

    def display_with_stats(self, logs: list[dict[str, Any]]) -> None:
        """Display logs with statistics panel.

        Args:
            logs: List of log dictionaries.
        """
        stats = self._calculate_stats(logs)
        self._display_stats(stats)

        console.print()

        self.display(logs, show_context=False)

    def display_stats(self, stats: dict[str, Any]) -> None:
        """Display statistics only.

        Args:
            stats: Statistics dictionary.
        """
        self._display_stats(stats)

    def _display_log(self, log: dict[str, Any], show_context: bool = True) -> None:
        """Display single log entry with per-field styling.

        Layout matches ``console_sink``: ``time | 🔍 LEVEL | logger | message``

        Args:
            log: Log dictionary.
            show_context: Whether to show context metadata.
        """
        level = log.get("level", "INFO")
        color = _LEVEL_COLOR.get(level, "dodger_blue2")
        badge = _LEVEL_BADGE.get(level, "dodger_blue2 bold")
        icon = _LEVEL_ICON.get(level, "❓")
        timestamp = self._format_timestamp(log.get("timestamp", ""))
        logger_name = log.get("logger", "")
        message = log.get("message", "")

        sep = " | "

        t = Text()
        t.append(timestamp, style=f"{color} italic")
        t.append(sep, style="white")
        if _show_icons:
            t.append(f"{icon} ", style=badge)
        t.append(f"{level:<8}", style=badge)
        t.append(sep, style="white")
        if logger_name:
            t.append(logger_name, style=f"{color} italic")
            t.append(sep, style="white")

        msg = auto_highlight_text(message)
        msg.style = f"bold italic {color}"
        t.append_text(msg)

        if show_context and "context" in log:
            ctx = " ".join(f"{k}={v}" for k, v in log["context"].items())
            t.append(f" [{ctx}]", style=f"{color} dim")

        console.print(t)

    def _format_timestamp(self, timestamp: str) -> str:
        """Format timestamp for display.

        Args:
            timestamp: ISO timestamp string.

        Returns:
            Formatted time string.
        """
        if not timestamp:
            return ""

        try:
            dt = datetime.fromisoformat(timestamp)
            return dt.strftime("%H:%M:%S.%f")[:-3]
        except ValueError, TypeError:
            return timestamp

    def _calculate_stats(self, logs: list[dict[str, Any]]) -> dict[str, Any]:
        """Calculate statistics from logs.

        Args:
            logs: List of log dictionaries.

        Returns:
            Statistics dictionary.
        """
        level_counts: dict[str, int] = {}
        for log in logs:
            level = log.get("level", "UNKNOWN")
            level_counts[level] = level_counts.get(level, 0) + 1

        return {
            "total": len(logs),
            "by_level": level_counts,
        }

    def _display_stats(self, stats: dict[str, Any]) -> None:
        """Display statistics panel.

        Args:
            stats: Statistics dictionary.
        """
        content = []

        content.append(f"[white_bold]Total logs:[/white_bold] {stats['total']}")

        if "by_level" in stats:
            content.append("\n[white_bold]By level:[/white_bold]")
            for level, count in stats["by_level"].items():
                color = _LEVEL_COLOR.get(level, "dodger_blue2")
                icon = _LEVEL_ICON.get(level, "❓") if _show_icons else ""
                prefix = f"{icon} " if icon else ""
                content.append(f"  [{color} bold]{prefix}{level:<8} {count:>4}[/{color} bold]")

        panel = Panel(
            "\n".join(content),
            title="[ruby_red_bold]Log Statistics[/ruby_red_bold]",
            border_style="ruby_red",
        )

        console.print(panel)
