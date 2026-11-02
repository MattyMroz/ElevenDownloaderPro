"""Logger configuration models for console and file output.

Every component is configurable: time, level, icon, logger name, message, context.

Example:
    >>> from logger import LoggerConfig, ConsoleConfig, FileConfig
    >>>
    >>> # Minimal: only message
    >>> config = LoggerConfig(
    ...     console=ConsoleConfig(
    ...         show_time=False,
    ...         show_level=False,
    ...         show_logger_name=False
    ...     )
    ... )
    >>>
    >>> # Custom styles
    >>> config = LoggerConfig(
    ...     console=ConsoleConfig(
    ...         logger_name_style="purple_bold",
    ...         time_style="yellow"
    ...     )
    ... )
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

__all__ = [
    "ConsoleConfig",
    "FileConfig",
    "LogLevel",
    "LoggerConfig",
    "LoggerMode",
    "PresetConfig",
    "PresetName",
    "TimeFormat",
    "TimestampFormat",
    "get_level_priority",
]

# ── Type Aliases ──────────────────────────────────────────────────────────────

LogLevel = Literal["DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"]
"""Accepted log level names, from least to most severe."""

TimeFormat = Literal["HH:MM:SS.ms", "HH:MM:SS", "ISO8601", "timestamp"]
"""Accepted console timestamp display formats."""

TimestampFormat = Literal["iso8601", "timestamp"]
"""Accepted JSON timestamp formats."""


# ── Logger Modes ──────────────────────────────────────────────────────────────


class LoggerMode(StrEnum):
    """Logger operating modes for different environments.

    Attributes:
        DEV: Development mode (DEBUG+, full context, file:line).
        PRODUCTION: Production mode (INFO+, minimal context).
        SILENT: Silent mode (ERROR only, no console, file only).
    """

    DEV = "DEV"
    PRODUCTION = "PRODUCTION"
    SILENT = "SILENT"


# ── Console Configuration ─────────────────────────────────────────────────────


class ConsoleConfig(BaseModel):
    """Console output configuration controlling which components are displayed.

    Example:
        >>> ConsoleConfig(
        ...     show_time=False,
        ...     show_icon=False,
        ...     show_logger_name=False
        ... )
        >>>
        >>> ConsoleConfig(
        ...     logger_name_style="ruby_red_bold",
        ...     time_style="yellow"
        ... )
    """

    # ── Time ──────────────────────────────────────────────────────────────────
    show_time: bool = Field(
        default=True,
        description="Show timestamp",
    )
    show_date: bool = Field(
        default=False,
        description="Include date in timestamp (YYYY-MM-DD)",
    )
    time_format: TimeFormat = Field(
        default="HH:MM:SS.ms",
        description="Time display format",
    )
    time_width: int | None = Field(
        default=None,
        description="Time field width (None = auto, recommended: 12 for HH:MM:SS.ms)",
    )
    time_style: str = Field(
        default="log.time",
        description="Rich style for time (from RICH_THEME)",
    )

    # ── Level ─────────────────────────────────────────────────────────────────
    show_level: bool = Field(
        default=True,
        description="Show log level with icon (e.g., 'ℹ️  INFO')",
    )
    show_icons: bool = Field(
        default=True,
        description="Show emoji icons in level display",
    )
    level_width: int | None = Field(
        default=11,
        description="Level field width including icon (None = auto, uses cell_len for emoji)",
    )
    level_style: str = Field(
        default="auto",
        description="Rich style for level ('auto' = per-level colors from RICH_THEME)",
    )

    # ── Logger Name ───────────────────────────────────────────────────────────
    show_logger_name: bool = Field(
        default=True,
        description="Show logger name/section",
    )
    logger_name_width: int | None = Field(
        default=None,
        description="Logger name field width (None = dynamic)",
    )
    logger_name_style: str = Field(
        default="ruby_red_bold",
        description="Rich style for logger name (from RICH_THEME)",
    )

    # ── Message ───────────────────────────────────────────────────────────────
    message_style: str = Field(
        default="normal",
        description="Rich style for message text",
    )

    # ── Context ───────────────────────────────────────────────────────────────
    show_context: bool = Field(
        default=True,
        description="Show context metadata (key=value pairs)",
    )
    context_style: str = Field(
        default="gray",
        description="Rich style for context",
    )

    # ── Location ──────────────────────────────────────────────────────────────
    show_location: bool = Field(
        default=False,
        description="Show file:line location",
    )
    location_style: str = Field(
        default="gray",
        description="Rich style for location",
    )

    # ── Separator ─────────────────────────────────────────────────────────────
    separator: str = Field(
        default=" | ",
        description="Separator between components",
    )
    separator_style: str = Field(
        default="white",
        description="Rich style for separator",
    )

    model_config = {"frozen": False, "extra": "forbid"}


# ── File Configuration ────────────────────────────────────────────────────────


class FileConfig(BaseModel):
    """File logging configuration with JSON output and rotation.

    Example:
        >>> FileConfig(
        ...     path=Path("logs/app.log"),
        ...     rotation="100 MB"
        ... )
        >>>
        >>> FileConfig(
        ...     include_location=False,
        ...     include_process=False
        ... )
    """

    # ── Basic ─────────────────────────────────────────────────────────────────
    enable: bool = Field(
        default=True,
        description="Enable file logging",
    )
    path: Path = Field(
        default=Path("logs/app.log"),
        description="Log file path",
    )

    # ── Rotation & Retention ──────────────────────────────────────────────────
    rotation: str | int = Field(
        default="100 MB",
        description="Rotation trigger (size: '100 MB', time: '1 day', '00:00')",
    )
    retention: str | int = Field(
        default="30 days",
        description="Retention period ('30 days') or count (10 files)",
    )
    compression: str = Field(
        default="zip",
        description="Compression format (zip, gz, bz2)",
    )

    # ── JSON Structure ────────────────────────────────────────────────────────
    include_timestamp: bool = Field(
        default=True,
        description="Include timestamp in JSON",
    )
    include_level: bool = Field(
        default=True,
        description="Include level in JSON",
    )
    include_logger: bool = Field(
        default=True,
        description="Include logger name in JSON",
    )
    include_message: bool = Field(
        default=True,
        description="Include message in JSON",
    )
    include_context: bool = Field(
        default=True,
        description="Include context metadata in JSON",
    )
    include_location: bool = Field(
        default=True,
        description="Include file/function/line in JSON",
    )
    include_process: bool = Field(
        default=False,
        description="Include process info in JSON",
    )
    include_thread: bool = Field(
        default=False,
        description="Include thread info in JSON",
    )
    include_exception: bool = Field(
        default=True,
        description="Include exception traceback in JSON",
    )

    # ── Format ────────────────────────────────────────────────────────────────
    timestamp_format: TimestampFormat = Field(
        default="iso8601",
        description="Timestamp format in JSON",
    )
    indent: int | None = Field(
        default=None,
        description="JSON indentation (None = compact, 2 = pretty)",
    )

    model_config = {"frozen": False, "extra": "forbid"}


# ── Main Logger Configuration ─────────────────────────────────────────────────


class LoggerConfig(BaseModel):
    """Main logger configuration combining console and file settings.

    Example:
        >>> LoggerConfig(name="app", level="INFO")
        >>>
        >>> LoggerConfig(
        ...     console=ConsoleConfig(show_time=False),
        ...     file=FileConfig(rotation="50 MB")
        ... )
    """

    # ── Basic ─────────────────────────────────────────────────────────────────
    name: str = Field(
        default="app",
        description="Logger name (generic, portable)",
    )
    level: LogLevel = Field(
        default="INFO",
        description="Minimum log level",
    )

    # ── Level Overrides ───────────────────────────────────────────────────────
    console_level: LogLevel | None = Field(
        default=None,
        description="Override console log level (None = use main level)",
    )
    file_level: LogLevel | None = Field(
        default=None,
        description="Override file log level (None = use main level)",
    )

    # ── Sink Enable/Disable ───────────────────────────────────────────────────
    console_enabled: bool = Field(
        default=True,
        description="Enable console output",
    )

    # ── Sinks ─────────────────────────────────────────────────────────────────
    console: ConsoleConfig = Field(
        default_factory=ConsoleConfig,
        description="Console output configuration",
    )
    file: FileConfig = Field(
        default_factory=FileConfig,
        description="File logging configuration",
    )

    def save_to_json(self, path: Path | str) -> None:
        """Save config to JSON file.

        Args:
            path: Path to JSON file.

        Raises:
            OSError: If the file cannot be written.
        """
        path = Path(path) if isinstance(path, str) else path
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.model_dump(), f, indent=2, default=str)

    @classmethod
    def load_from_json(cls, path: Path | str) -> LoggerConfig:
        """Load config from JSON file.

        Args:
            path: Path to JSON file.

        Returns:
            LoggerConfig instance.

        Raises:
            FileNotFoundError: If the file does not exist.
            JSONDecodeError: If the file contains invalid JSON.
            ValidationError: If the data does not match the schema.
        """
        path = Path(path) if isinstance(path, str) else path
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)

    model_config = {"frozen": False, "extra": "forbid"}


# ── Preset Configuration ──────────────────────────────────────────────────────

PresetName = Literal[
    "ultra_verbose",
    "verbose",
    "standard",
    "minimal",
    "silent",
    "api_logging",
    "ml_logging",
]
"""Names of built-in logger configuration presets."""


class PresetConfig(BaseModel):
    """Preset configuration template.

    Example:
        >>> PresetConfig(
        ...     name="standard",
        ...     description="Production logging",
        ...     config=LoggerConfig(level="INFO")
        ... )
    """

    name: PresetName = Field(
        description="Preset name",
    )
    description: str = Field(
        description="Preset description",
    )
    config: LoggerConfig = Field(
        description="Logger configuration",
    )

    model_config = {"frozen": True, "extra": "forbid"}


# ── Utility Functions ─────────────────────────────────────────────────────────


def get_level_priority(level: LogLevel) -> int:
    """Return numeric priority for a log level.

    Args:
        level: Log level name.

    Returns:
        Priority value (higher = more severe).

    Example:
        >>> get_level_priority("ERROR")
        40
        >>> get_level_priority("DEBUG")
        10
    """
    priorities: dict[LogLevel, int] = {
        "DEBUG": 10,
        "INFO": 20,
        "SUCCESS": 25,
        "WARNING": 30,
        "ERROR": 40,
        "CRITICAL": 50,
    }
    return priorities.get(level, 0)
