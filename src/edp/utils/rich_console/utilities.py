"""Stateless helper functions for Rich console: icons, sizes, colors, durations, percentages.

Usage:
    >>> from rich_console import get_status_icon, format_bytes, format_duration
    >>> icon = get_status_icon("success")  # '[success]✅[/success]'
    >>> size = format_bytes(1024**3)  # "1.07 GB"
    >>> time = format_duration(3665)  # "1h 1m 5.00s"
"""

from __future__ import annotations

from typing import Final, Literal

__all__ = [
    "StatusType",
    "format_bytes",
    "format_duration",
    "format_percentage",
    "get_progress_color",
    "get_status_icon",
]

# ── Constants ─────────────────────────────────────────────────────────────────

_MAX_PERCENTAGE: Final[float] = 100
"""Upper bound of a valid percentage value."""

_SECONDS_PER_MINUTE: Final[int] = 60
"""Seconds in one minute, used to split a duration into minutes and seconds."""

_MINUTES_PER_HOUR: Final[int] = 60
"""Minutes in one hour, used to split a duration into hours and minutes."""

# ── Status Icons ──────────────────────────────────────────────────────────────

StatusType = Literal[
    "success",
    "error",
    "warning",
    "info",
    "debug",
    "critical",
    "pending",
    "running",
    "stopped",
]
"""Supported status icon names for ``get_status_icon``."""


def get_status_icon(status: StatusType, with_style: bool = True) -> str:
    """Return icon for a status with optional Rich styling.

    Args:
        status: Status type.
        with_style: If True, wrap icon in Rich markup tags.

    Returns:
        Icon string, optionally wrapped in Rich style tags.

    Example:
        >>> get_status_icon("success")
        '[success]✅[/success]'
        >>> get_status_icon("error", with_style=False)
        '❌'
    """
    icons: dict[StatusType, tuple[str, str]] = {
        "success": ("✅", "success"),
        "error": ("❌", "error"),
        "warning": ("⚠️ ", "warning"),
        "info": ("ℹ️ ", "info"),
        "debug": ("🔍", "debug"),
        "critical": ("💀", "critical"),
        "pending": ("⏳", "yellow"),
        "running": ("⚙️ ", "blue"),
        "stopped": ("⏹️ ", "gray"),
    }

    icon: str
    style: str
    icon, style = icons.get(status, ("❓", "gray"))

    return f"[{style}]{icon}[/{style}]" if with_style else icon


# ── Byte Size Formatting ──────────────────────────────────────────────────────


def format_bytes(
    size_bytes: int | float,
    precision: int = 2,
    binary: bool = False,
) -> str:
    """Format byte count to human-readable size string.

    Args:
        size_bytes: Size in bytes.
        precision: Decimal places.
        binary: If True, use 1024 base (KiB); otherwise 1000 (KB).

    Returns:
        Formatted size string.

    Raises:
        ValueError: If size_bytes is negative.

    Example:
        >>> format_bytes(1000)
        '1.00 KB'
        >>> format_bytes(1024, binary=True)
        '1.00 KiB'
    """
    if size_bytes < 0:
        msg = "Size cannot be negative"
        raise ValueError(msg)

    if size_bytes == 0:
        return "0 B"

    base: int = 1024 if binary else 1000
    units: list[str] = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"] if binary else ["B", "KB", "MB", "GB", "TB", "PB"]

    unit_index: int = 0
    size: float = float(size_bytes)

    while size >= base and unit_index < len(units) - 1:
        size /= base
        unit_index += 1

    return f"{size:.{precision}f} {units[unit_index]}"


# ── Progress Color ────────────────────────────────────────────────────────────


def get_progress_color(
    percentage: float,
    good_threshold: float = 80.0,
    warning_threshold: float = 50.0,
) -> str:
    """Return color name based on percentage thresholds.

    Args:
        percentage: Progress percentage (0–100).
        good_threshold: Percentage at or above which to return green.
        warning_threshold: Percentage at or above which to return yellow.

    Returns:
        Color name: ``"green"``, ``"yellow"``, or ``"red"``.

    Raises:
        ValueError: If percentage is outside 0–100.

    Example:
        >>> get_progress_color(90)
        'green'
        >>> get_progress_color(60)
        'yellow'
    """
    if not 0 <= percentage <= _MAX_PERCENTAGE:
        msg = "Percentage must be between 0 and 100"
        raise ValueError(msg)

    if percentage >= good_threshold:
        return "green"
    if percentage >= warning_threshold:
        return "yellow"
    return "red"


# ── Duration Formatting ───────────────────────────────────────────────────────


def format_duration(seconds: float, precision: int = 2) -> str:
    """Format seconds to human-readable duration string.

    Args:
        seconds: Duration in seconds.
        precision: Decimal places for the seconds component.

    Returns:
        Formatted duration string.

    Raises:
        ValueError: If seconds is negative.

    Example:
        >>> format_duration(45.5)
        '45.50s'
        >>> format_duration(3665)
        '1h 1m 5.00s'
    """
    if seconds < 0:
        msg = "Duration cannot be negative"
        raise ValueError(msg)

    if seconds < _SECONDS_PER_MINUTE:
        return f"{seconds:.{precision}f}s"

    minutes: int = int(seconds // _SECONDS_PER_MINUTE)
    remaining_seconds: float = seconds % _SECONDS_PER_MINUTE

    if minutes < _MINUTES_PER_HOUR:
        return f"{minutes}m {remaining_seconds:.{precision}f}s"

    hours: int = minutes // _MINUTES_PER_HOUR
    remaining_minutes: int = minutes % _MINUTES_PER_HOUR

    return f"{hours}h {remaining_minutes}m {remaining_seconds:.{precision}f}s"


# ── Percentage Formatting ─────────────────────────────────────────────────────


def format_percentage(
    value: float,
    total: float,
    precision: int = 1,
    with_symbol: bool = True,
) -> str:
    """Format value/total ratio as a percentage string.

    Args:
        value: Current value.
        total: Total value. Must not be negative.
        precision: Decimal places.
        with_symbol: If True, append ``'%'`` symbol.

    Returns:
        Formatted percentage string.

    Raises:
        ValueError: If total is negative.

    Example:
        >>> format_percentage(75, 100)
        '75.0%'
        >>> format_percentage(1, 3, precision=2)
        '33.33%'
    """
    if total < 0:
        msg = "Total cannot be negative"
        raise ValueError(msg)

    if total == 0:
        zero: str = f"{0:.{precision}f}"
        return f"{zero}%" if with_symbol else zero

    percentage: float = (value / total) * 100
    formatted: str = f"{percentage:.{precision}f}"

    return f"{formatted}%" if with_symbol else formatted
