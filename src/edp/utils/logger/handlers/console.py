"""Console sink function for loguru with Rich formatting and stats tracking."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from rich.text import Text

from ...rich_console import console
from ...rich_console.console import auto_highlight_text
from ..stats import increment_stat

__all__ = ["console_sink", "set_show_icons"]

if TYPE_CHECKING:
    from datetime import datetime

# ── Configuration ─────────────────────────────────────────────────────────────
_show_icons: bool = True


def set_show_icons(enabled: bool) -> None:
    """Enable or disable emoji icons in console log output.

    Args:
        enabled: True to show icons, False to hide them.
    """
    global _show_icons  # noqa: PLW0603
    _show_icons = enabled


# ── Per-field styling ─────────────────────────────────────────────────────────
_SEP: Final[str] = " | "
"""Separator drawn between log line fields."""

_LEVEL_BADGE: Final[dict[str, str]] = {
    "TRACE": "rgb(58,58,58) bold",
    "DEBUG": "rgb(255,135,70) bold",
    "INFO": "dodger_blue2 bold",
    "SUCCESS": "green bold",
    "WARNING": "bright_yellow bold",
    "ERROR": "bright_red bold",
    "CRITICAL": "rgb(0,0,0) on bright_red bold",
}
"""Column-2 badge style per level (icon + level name, full intensity, bold)."""

_LEVEL_COLOR: Final[dict[str, str]] = {
    "TRACE": "rgb(58,58,58)",
    "DEBUG": "rgb(255,135,70)",
    "INFO": "dodger_blue2",
    "SUCCESS": "green",
    "WARNING": "bright_yellow",
    "ERROR": "bright_red",
    "CRITICAL": "bright_red",
}
"""Base color per level for columns 1 & 3 (same hue as badge, italic)."""

_LEVEL_ICON: Final[dict[str, str]] = {
    "TRACE": "🔬",
    "DEBUG": "🔍",
    "INFO": "ℹ️ ",
    "SUCCESS": "✅",
    "WARNING": "⚠️ ",
    "ERROR": "❌",
    "CRITICAL": "💀",
}
"""Emoji icon per level (matching rich_console.utilities)."""


def console_sink(message: Any) -> None:
    """Format and print a log record to console with Rich styling.

    Args:
        message: Loguru message object with ``.record`` dict.
    """
    record: dict[str, Any] = message.record
    level: str = record["level"].name
    extra: dict[str, Any] = record.get("extra", {})
    logger_name: str = extra.get("logger_name", "app")

    increment_stat(level, logger_name)

    text: Text = _build_message(record)
    console.print(text)


def _build_message(record: dict[str, Any]) -> Text:
    """Build log line as Rich Text with per-field styling.

    Layout: ``time | 🔍 LEVEL | logger | message``

    Colors follow the level theme:

    - Column 1 (timestamp): level color, italic.
    - Column 2 (icon + badge): level color, bold (CRITICAL: black on red).
    - Column 3 (logger name): level color, italic, dynamic width.
    - Column 4 (message): bold white italic with ``auto_highlight_text`` styling.
    - Separators: ``|`` white.
    - Context binds: omitted on console (kept in file sink only).

    Args:
        record: Loguru record dict.

    Returns:
        Rich Text object ready for ``console.print()``.
    """
    timestamp: datetime = record["time"]
    time_str: str = timestamp.strftime("%H:%M:%S.%f")[:-3]

    level: str = record["level"].name
    extra: dict[str, Any] = record.get("extra", {})
    logger_name: str = extra.get("logger_name", "app")
    message_text: str = record["message"]

    color: str = _LEVEL_COLOR.get(level, "dodger_blue2")
    badge: str = _LEVEL_BADGE.get(level, "dodger_blue2 bold")
    icon: str = _LEVEL_ICON.get(level, "❓")

    t = Text()
    t.append(time_str, style=f"{color} italic")
    t.append(_SEP, style="white")
    if _show_icons:
        t.append(f"{icon} ", style=badge)
    t.append(f"{level:<8}", style=badge)
    t.append(_SEP, style="white")
    t.append(logger_name, style=f"{color} italic")
    t.append(_SEP, style="white")

    msg: Text = auto_highlight_text(message_text)
    msg.style = f"bold italic {color}"
    t.append_text(msg)

    return t
