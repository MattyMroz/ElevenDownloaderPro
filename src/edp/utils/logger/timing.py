"""Timer integration for performance tracking with automatic logging.

Bridge between ``utils.timer.Timer`` and *loguru* — provide ``log_duration``
context manager that automatically logs elapsed time.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

    from loguru import Logger

from loguru import logger

from ..timer import Timer

__all__ = ["log_duration"]


# ── log_duration ──────────────────────────────────────────────────────────────


@contextmanager
def log_duration(
    operation_name: str,
    level: str = "INFO",
    logger_instance: Logger | None = None,
) -> Generator[Timer]:
    """Time an operation and log the duration on exit.

    Args:
        operation_name: Name of the operation being timed.
        level: Log level for the timing message.
        logger_instance: Custom logger instance (default: global logger).

    Yields:
        Timer instance for manual access to duration.

    Example:
        >>> with log_duration("image_processing"):  # doctest: +SKIP
        ...     process_image(img)
    """
    log = logger_instance or logger
    timer = Timer(operation_name, auto_start=True)

    try:
        yield timer
    finally:
        duration_ns = timer.stop()
        duration_ms = round(duration_ns / 1_000_000, 3)
        duration_s = round(duration_ns / 1_000_000_000, 3)

        log.bind(
            operation=operation_name,
            duration_ns=duration_ns,
            duration_ms=duration_ms,
            duration_s=duration_s,
            start_time=timer.start_date.isoformat() if timer.start_date else None,
            end_time=timer.end_date.isoformat() if timer.end_date else None,
        ).log(level, "{op} completed in {ms}ms", op=operation_name, ms=duration_ms)
