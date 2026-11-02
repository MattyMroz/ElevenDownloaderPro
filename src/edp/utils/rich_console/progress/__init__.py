"""Progress bar system with dynamic color transitions.

Modular single-bar (``ProgressBarManager``) and multi-row
(``MultiProgressManager``) context managers with per-component flags,
multiple bar styles, and download/speed columns.

Usage:
    >>> from rich_console.progress import ProgressBarManager
    >>> with ProgressBarManager("Processing", total=100) as pb:
    ...     pb.advance(50)

    >>> # Download mode
    >>> with ProgressBarManager("file.zip", total=100_000_000,
    ...     show_download=True, show_speed=True) as pb:
    ...     pb.advance(10_000_000)
"""

from __future__ import annotations

from .manager import ProgressBarBuilder, ProgressBarManager
from .multi import MultiProgressManager

__all__ = ["MultiProgressManager", "ProgressBarBuilder", "ProgressBarManager"]
