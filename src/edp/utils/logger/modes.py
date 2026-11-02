"""Predefined logger mode configurations for DEV, PRODUCTION and SILENT."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

from .config import (
    ConsoleConfig,
    FileConfig,
    LoggerConfig,
    LoggerMode,
)

__all__ = ["get_mode_config"]

# ── Mode Presets ──────────────────────────────────────────────────────────────

_MODE_DEFAULTS: Final[dict[LoggerMode, dict[str, Any]]] = {
    LoggerMode.DEV: {
        "name": "dev",
        "level": "DEBUG",
        "console_level": "DEBUG",
        "file_level": "DEBUG",
        "console_enabled": True,
        "console": ConsoleConfig(
            show_time=True,
            show_level=True,
            show_logger_name=True,
            show_context=True,
            show_location=True,
        ),
        "file": FileConfig(
            enable=True,
            path=Path("logs/dev.log.jsonl"),
            rotation="50 MB",
            retention="7 days",
            include_process=True,
            include_thread=True,
            include_location=True,
            indent=2,
        ),
    },
    LoggerMode.PRODUCTION: {
        "name": "app",
        "level": "INFO",
        "console_level": "INFO",
        "file_level": "INFO",
        "console_enabled": True,
        "console": ConsoleConfig(
            show_time=True,
            show_level=True,
            show_logger_name=True,
            show_context=False,
            show_location=False,
        ),
        "file": FileConfig(
            enable=True,
            path=Path("logs/app.log.jsonl"),
            rotation="100 MB",
            retention="30 days",
            include_process=False,
            include_thread=False,
            include_location=False,
            indent=None,
        ),
    },
    LoggerMode.SILENT: {
        "name": "silent",
        "level": "ERROR",
        "console_level": None,
        "file_level": "ERROR",
        "console_enabled": False,
        "console": ConsoleConfig(
            show_time=False,
        ),
        "file": FileConfig(
            enable=True,
            path=Path("logs/errors.log.jsonl"),
            rotation="200 MB",
            retention="90 days",
            include_process=True,
            include_thread=True,
            include_location=True,
            include_exception=True,
            indent=2,
        ),
    },
}
"""Per-mode default config kwargs passed to ``LoggerConfig``."""


def get_mode_config(mode: LoggerMode, **overrides: Any) -> LoggerConfig:
    """Return logger config for the specified mode.

    Args:
        mode: Logger operating mode to apply.
        **overrides: Override any config field (e.g., level="DEBUG").

    Returns:
        LoggerConfig with mode-specific settings.

    Raises:
        ValueError: If mode is not a recognized LoggerMode value.

    Example:
        >>> from logger import get_mode_config, LoggerMode
        >>> config = get_mode_config(LoggerMode.DEV)
        >>> config = get_mode_config(LoggerMode.PRODUCTION, level="DEBUG")
    """
    defaults = _MODE_DEFAULTS.get(mode)
    if defaults is None:
        msg = f"Unknown mode: {mode}"
        raise ValueError(msg)

    config = LoggerConfig(**defaults)

    if overrides:
        if "file_path" in overrides:
            file_path = overrides.pop("file_path")
            overrides["file"] = FileConfig(**{**config.file.model_dump(), "path": file_path})

        config_dict = config.model_dump()
        config_dict.update(overrides)
        config = LoggerConfig(**config_dict)

    return config
