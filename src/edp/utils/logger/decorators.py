"""Timing decorators for automatic function execution logging.

Example:
    >>> from logger.decorators import timed, timed_if
    >>> @timed()
    ... def slow_function():
    ...     time.sleep(1)
    >>>
    >>> @timed_if(lambda: os.getenv("DEBUG") == "true")
    ... def debug_only():
    ...     pass
"""

from __future__ import annotations

import os
from collections.abc import Callable
from functools import wraps
from typing import Any, Literal, TypeVar

from .timing import log_duration

__all__ = ["timed", "timed_debug", "timed_if", "timed_in_dev", "timed_when_debug"]

F = TypeVar("F", bound=Callable[..., Any])
"""Callable type preserved by the timing decorators (signature stays intact)."""


def timed(
    operation_name: str | None = None,
    level: Literal["DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR"] = "INFO",
) -> Callable[[F], F]:
    """Decorate a function to automatically log its execution time.

    Args:
        operation_name: Custom operation name (defaults to function name).
        level: Log level for timing message.

    Returns:
        Decorated function.

    Example:
        >>> @timed()
        ... def process_image(img):
        ...     return transform(img)
        >>>
        >>> @timed("heavy_computation", level="DEBUG")
        ... def compute(data):
        ...     return result
    """

    def decorator(func: F) -> F:
        name = operation_name or func.__name__

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with log_duration(name, level=level):
                return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def timed_if(
    condition: Callable[[], bool] | bool,
    operation_name: str | None = None,
    level: Literal["DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR"] = "INFO",
) -> Callable[[F], F]:
    """Decorate a function to conditionally log its execution time.

    Args:
        condition: Boolean or callable returning bool (checked at runtime).
        operation_name: Custom operation name (defaults to function name).
        level: Log level for timing message.

    Returns:
        Decorated function.

    Example:
        >>> @timed_if(os.getenv("DEBUG", "false") == "true")
        ... def debug_function():
        ...     pass
        >>>
        >>> @timed_if(lambda: os.getenv("ENABLE_TIMING") == "true")
        ... def maybe_timed():
        ...     pass
    """

    def decorator(func: F) -> F:
        name = operation_name or func.__name__

        def should_time() -> bool:
            if callable(condition):
                return condition()
            return condition

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if should_time():
                with log_duration(name, level=level):
                    return func(*args, **kwargs)
            else:
                return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


# ── Convenience Decorators ────────────────────────────────────────────────────


def timed_debug(operation_name: str | None = None) -> Callable[[F], F]:
    """Time function execution at DEBUG level.

    Example:
        >>> @timed_debug()
        ... def debug_operation():
        ...     pass
    """
    return timed(operation_name, level="DEBUG")


def timed_in_dev(operation_name: str | None = None) -> Callable[[F], F]:
    """Time function only in development mode (LOGGER_MODE=DEV).

    Example:
        >>> @timed_in_dev()
        ... def dev_only_timing():
        ...     pass
    """
    is_dev = os.getenv("LOGGER_MODE", "PRODUCTION") == "DEV"
    return timed_if(is_dev, operation_name)


def timed_when_debug(operation_name: str | None = None) -> Callable[[F], F]:
    """Time function only when DEBUG=true.

    Example:
        >>> @timed_when_debug()
        ... def debug_timed():
        ...     pass
    """
    return timed_if(
        lambda: os.getenv("DEBUG", "false").lower() == "true",
        operation_name,
    )
