"""Logger exception hierarchy.

All logger-specific exceptions inherit from ``LoggerError``.
"""

from __future__ import annotations

__all__ = [
    "ConfigError",
    "HandlerError",
    "LoggerError",
    "ParserError",
]


class LoggerError(Exception):
    """Base exception for the logger module."""


class ConfigError(LoggerError):
    """Raised when logger configuration is invalid."""


class ParserError(LoggerError):
    """Raised when a log file cannot be parsed."""


class HandlerError(LoggerError):
    """Raised when a log handler encounters an error."""
