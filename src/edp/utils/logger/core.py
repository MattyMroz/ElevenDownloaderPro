"""Core logger setup with queue-based non-blocking logging.

Provide the main ``setup_mode`` function, stdlib bridge via
``InterceptHandler``, and environment-based configuration.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from loguru import logger

from .config import LoggerMode
from .modes import get_mode_config
from .scrubber import scrub_patcher

if TYPE_CHECKING:
    from types import FrameType

    from loguru import Record

__all__ = [
    "InterceptHandler",
    "setup_mode",
    "setup_mode_from_env",
    "shutdown_logger",
]

_VENDOR_LOGGERS: Final[tuple[str, ...]] = (
    "torch",
    "torchvision",
    "httpx",
    "httpcore",
    "transformers",
    "urllib3",
    "PIL",
    "matplotlib",
    "ultralytics",
    "onnxruntime",
    "filelock",
    "fsspec",
    "huggingface_hub",
)
"""Noisy vendor loggers pinned to WARNING to keep logs readable."""


class InterceptHandler(logging.Handler):
    """Bridge stdlib logging → loguru.

    Routes all stdlib log records to loguru so there's a single
    logging backend regardless of which library emits the message.
    """

    def emit(self, record: logging.LogRecord) -> None:
        """Forward a stdlib LogRecord to loguru.

        Args:
            record: The stdlib log record to forward.
        """
        level: str | int
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame: FrameType | None = logging.currentframe()
        depth = 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_mode(mode: LoggerMode, **overrides: Any) -> None:
    """Set up logger with a predefined mode.

    Adds enqueued console/file sinks and installs the stdlib → loguru bridge.

    Args:
        mode: Logger operating mode to apply.
        **overrides: Optional config overrides (e.g., level="DEBUG").

    Example:
        >>> from logger import setup_mode, LoggerMode
        >>> setup_mode(LoggerMode.DEV)
        >>> setup_mode(LoggerMode.PRODUCTION, level="DEBUG")
    """
    logger.remove()

    config = get_mode_config(mode, **overrides)

    diagnose = False

    if config.console_enabled:
        from .handlers.console import console_sink

        logger.add(
            sink=console_sink,
            level=config.console_level or config.level,
            enqueue=True,
            diagnose=diagnose,
            format="{message}",
        )

    if config.file.enable:
        config.file.path.parent.mkdir(parents=True, exist_ok=True)

        logger.add(
            sink=str(config.file.path),
            level=config.file_level or config.level,
            enqueue=True,
            diagnose=diagnose,
            rotation=config.file.rotation,
            retention=config.file.retention,
            compression=config.file.compression,
            serialize=True,
            format=_file_format,
        )

        if mode is not LoggerMode.SILENT:
            errors_path = config.file.path.parent / "errors.log.jsonl"
            logger.add(
                sink=str(errors_path),
                level="ERROR",
                enqueue=True,
                diagnose=diagnose,
                backtrace=True,
                rotation="50 MB",
                retention="90 days",
                serialize=True,
                format=_file_format,
            )

    logger.configure(patcher=scrub_patcher)

    _install_intercept()


def _file_format(record: Record) -> str:
    """Format file exceptions with source names and no paths, code or locals."""
    if record["exception"] is None:
        return "{message}\n"
    return "{message}\n{extra[_safe_traceback]}\n"


def _install_intercept() -> None:
    """Install InterceptHandler on the root stdlib logger and tame vendor noise."""
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    for name in _VENDOR_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers = [InterceptHandler()]
        lg.propagate = False

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers = []
    access_logger.propagate = False
    access_logger.disabled = True


def setup_mode_from_env(**overrides: Any) -> None:
    """Set up logger from environment variables.

    Reads configuration from environment variables:
    - LOGGER_MODE: DEV | PRODUCTION | SILENT (default: PRODUCTION)
    - LOGGER_LEVEL: DEBUG | INFO | WARNING | ERROR | CRITICAL
    - LOGGER_FILE_PATH: Custom log file path
    - LOGGER_DISABLE_CONSOLE: true/false (disable console output)
    - LOGGER_DISABLE_FILE: true/false (disable file output)

    Args:
        **overrides: Additional overrides (take priority over env vars).

    Example:
        >>> from logger import setup_mode_from_env
        >>> setup_mode_from_env()
    """
    mode_str = os.getenv("LOGGER_MODE", "PRODUCTION").upper()
    try:
        mode = LoggerMode(mode_str)
    except ValueError:
        logger.warning("Invalid LOGGER_MODE: {mode_str}, using PRODUCTION", mode_str=mode_str)
        mode = LoggerMode.PRODUCTION

    env_overrides: dict[str, Any] = {}

    if level := os.getenv("LOGGER_LEVEL"):
        env_overrides["level"] = level.upper()

    if file_path := os.getenv("LOGGER_FILE_PATH"):
        env_overrides["file_path"] = Path(file_path)

    if os.getenv("LOGGER_DISABLE_CONSOLE", "").lower() == "true":
        env_overrides["console_enabled"] = False

    if os.getenv("LOGGER_DISABLE_FILE", "").lower() == "true":
        env_overrides["file"] = {"enable": False}

    final_overrides = {**env_overrides, **overrides}

    setup_mode(mode, **final_overrides)


def shutdown_logger() -> None:
    """Gracefully shut down logger.

    Wait for the queue to flush before removing handlers.
    Call before application exit.

    Example:
        >>> from logger import shutdown_logger
        >>> shutdown_logger()
    """
    logger.remove()
