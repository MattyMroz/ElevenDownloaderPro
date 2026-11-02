"""Monotonic-clock timing helpers shared across the app."""

from __future__ import annotations

import time
from typing import Final

__all__ = ["MS_PER_SEC", "elapsed_ms_since"]

MS_PER_SEC: Final[int] = 1_000
"""Milliseconds per second, for monotonic-clock elapsed conversions."""


def elapsed_ms_since(monotonic_start: float) -> int:
    """Return integer milliseconds elapsed since ``monotonic_start``.

    Args:
        monotonic_start: A ``time.monotonic()`` reading taken at the start.

    Returns:
        Whole milliseconds elapsed (truncated toward zero).
    """
    return int((time.monotonic() - monotonic_start) * MS_PER_SEC)
