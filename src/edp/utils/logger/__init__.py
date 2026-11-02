"""Preconfigured loguru logger with DEV/PRODUCTION/SILENT modes and JSONL output.

Bundles non-blocking sinks, a ``log_duration`` timer, a chain-able ``LogReader``,
and statistics tracking.

Example:
    >>> from logger import setup_mode, LoggerMode
    >>> from loguru import logger
    >>>
    >>> setup_mode(LoggerMode.DEV)
    >>> logger.bind(logger_name="app").info("Application started")

    >>> from logger import log_duration
    >>> with log_duration("image_processing"):
    ...     process_image(img)

    >>> from logger import get_logger_stats
    >>> stats = get_logger_stats()
    >>> print(f"Total logged: {stats.total_logged}")
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from loguru import Logger

# ── Core ──────────────────────────────────────────────────────────────────────
from .config import LoggerConfig, LoggerMode
from .core import (
    InterceptHandler,
    setup_mode,
    setup_mode_from_env,
    shutdown_logger,
)
from .decorators import (
    timed,
    timed_debug,
    timed_if,
    timed_in_dev,
    timed_when_debug,
)
from .errors import ConfigError, HandlerError, LoggerError, ParserError
from .log_viewer import LogViewer
from .modes import get_mode_config
from .readers import LogAggregator, LogReader
from .stats import LoggerStats, get_logger_stats, reset_stats
from .timing import log_duration


def get_logger(name: str | None = None) -> Logger:
    """Get a configured logger instance with bound context.

    Args:
        name: Logger name (typically ``__name__``).

    Returns:
        Logger instance with bound ``logger_name``.

    Example:
        >>> from logger import get_logger
        >>> log = get_logger(__name__)
        >>> log.info("Ready")
    """
    if name:
        return logger.bind(logger_name=name)
    return logger


__all__ = [
    "ConfigError",
    "HandlerError",
    "InterceptHandler",
    "LogAggregator",
    "LogReader",
    "LogViewer",
    "LoggerConfig",
    "LoggerError",
    "LoggerMode",
    "LoggerStats",
    "ParserError",
    "get_logger",
    "get_logger_stats",
    "get_mode_config",
    "log_duration",
    "logger",
    "reset_stats",
    "setup_mode",
    "setup_mode_from_env",
    "shutdown_logger",
    "timed",
    "timed_debug",
    "timed_if",
    "timed_in_dev",
    "timed_when_debug",
]
