"""Rich console wrapper with custom theme, utilities and progress bars.

Bundles a preconfigured auto-highlighting ``console``, the 150+ style
``RICH_THEME``, dynamic-color progress bars, and formatting helpers.

Usage:
    >>> from rich_console import console
    >>> console.print("Processing 100 files")  # Auto-highlights numbers

    >>> from rich_console import ProgressBarManager
    >>> with ProgressBarManager("Downloading", total=100) as pb:
    ...     pb.advance(50)

    >>> from rich_console import format_bytes, format_duration
    >>> print(format_bytes(1024**3))  # "1.07 GB"
    >>> print(format_duration(3665))  # "1h 1m 5.00s"
"""

from __future__ import annotations

from typing import Final

from .console import console
from .progress import (
    MultiProgressManager,
    ProgressBarBuilder,
    ProgressBarManager,
)
from .theme import RICH_THEME, Colors
from .utilities import (
    StatusType,
    format_bytes,
    format_duration,
    format_percentage,
    get_progress_color,
    get_status_icon,
)

__all__ = [
    "RICH_THEME",
    "Colors",
    "MultiProgressManager",
    "ProgressBarBuilder",
    "ProgressBarManager",
    "StatusType",
    "console",
    "format_bytes",
    "format_duration",
    "format_percentage",
    "get_progress_color",
    "get_status_icon",
]

__version__: Final[str] = "1.0.0"
"""Semantic version of the rich_console package."""
