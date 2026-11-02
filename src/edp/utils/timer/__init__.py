"""Nanosecond-precision execution timer with Rich console display.

Provide ``Timer`` (low-level), ``ExecutionTimer`` (context manager with
visual output), and ``format_duration`` for standalone formatting.

Usage:

    # Context manager — visual output
    >>> with ExecutionTimer("Task"):  # doctest: +SKIP
    ...     do_work()

    # Decorator
    >>> @timed()  # doctest: +SKIP
    ... def process():
    ...     pass

    # Low-level
    >>> t = Timer("task", auto_start=True)
    >>> _ = t.stop()
"""

from __future__ import annotations

from datetime import datetime
from functools import wraps
from time import perf_counter_ns
from typing import TYPE_CHECKING, Any, Literal

from ..rich_console import console

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "DisplayMode",
    "ExecutionTimer",
    "Timer",
    "format_duration",
    "timed",
]

DisplayMode = Literal["none", "minimal", "standard", "verbose"]
"""Accepted display modes for timer output."""


# ── Timer ─────────────────────────────────────────────────────────────────────


class Timer:
    """Nanosecond-precision timer with datetime tracking.

    Usage:
        >>> t = Timer("task", auto_start=True)
        >>> _ = t.stop()
        >>> t.duration_ns >= 0
        True
    """

    def __init__(self, name: str = "Timer", auto_start: bool = False) -> None:
        """Initialize timer.

        Args:
            name: Timer name for identification.
            auto_start: Start timer immediately.
        """
        self._name: str = name
        self._start_time_ns: int | None = None
        self._end_time_ns: int | None = None
        self._start_date: datetime | None = None
        self._end_date: datetime | None = None
        self._is_running: bool = False

        if auto_start:
            self.start()

    def start(self) -> None:
        """Start timer measurement."""
        self._start_time_ns = perf_counter_ns()
        self._start_date = datetime.now()
        self._is_running = True
        self._end_time_ns = None
        self._end_date = None

    def stop(self) -> int:
        """Stop timer and return elapsed nanoseconds.

        Returns:
            Elapsed time in nanoseconds.
        """
        if not self._is_running:
            return 0

        self._end_time_ns = perf_counter_ns()
        self._end_date = datetime.now()
        self._is_running = False
        return self.duration_ns

    def reset(self) -> None:
        """Reset timer to initial state."""
        self._start_time_ns = None
        self._end_time_ns = None
        self._start_date = None
        self._end_date = None
        self._is_running = False

    @property
    def duration_ns(self) -> int:
        """Return duration in nanoseconds (0 if not started)."""
        if self._start_time_ns is None:
            return 0
        end_ns: int = self._end_time_ns if self._end_time_ns else perf_counter_ns()
        return end_ns - self._start_time_ns

    @property
    def duration_ms(self) -> float:
        """Return duration in milliseconds."""
        return self.duration_ns / 1_000_000

    @property
    def duration_s(self) -> float:
        """Return duration in seconds."""
        return self.duration_ns / 1_000_000_000

    @property
    def name(self) -> str:
        """Return timer name."""
        return self._name

    @property
    def is_running(self) -> bool:
        """Return whether timer is currently running."""
        return self._is_running

    @property
    def start_date(self) -> datetime | None:
        """Return start datetime."""
        return self._start_date

    @property
    def end_date(self) -> datetime | None:
        """Return end datetime."""
        return self._end_date


# ── ExecutionTimer ────────────────────────────────────────────────────────────


class ExecutionTimer:
    """Context manager for timing code blocks with Rich display.

    Usage:
        >>> with ExecutionTimer("Process"):  # doctest: +SKIP
        ...     do_work()

        >>> with ExecutionTimer("Task", display_mode="none") as t:  # doctest: +SKIP
        ...     do_work()
        ...     print(f"Took {t.get_duration_ns()} ns")
    """

    def __init__(
        self,
        name: str = "Execution",
        display_mode: DisplayMode = "standard",
    ) -> None:
        """Initialize execution timer.

        Args:
            name: Timer name.
            display_mode: Display mode (none/minimal/standard/verbose).
        """
        self._timer: Timer = Timer(name, auto_start=False)
        self._display_mode: DisplayMode = display_mode

    def __enter__(self) -> ExecutionTimer:
        """Start timer on context entry."""
        self._timer.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Stop timer and display result."""
        self._timer.stop()
        if self._display_mode != "none":
            format_duration(
                self._timer.duration_ns,
                self._timer.start_date,
                self._timer.end_date,
                mode=self._display_mode,
            )

    def get_duration_ns(self) -> int:
        """Return raw duration in nanoseconds."""
        return self._timer.duration_ns

    @property
    def timer(self) -> Timer:
        """Return underlying timer instance."""
        return self._timer


# ── Decorator ─────────────────────────────────────────────────────────────────


def timed(display_mode: DisplayMode = "standard") -> Callable[..., Any]:
    """Decorate a function to time its execution with Rich display.

    Args:
        display_mode: Display mode (none/minimal/standard/verbose).

    Returns:
        Decorated function.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            t = Timer(func.__name__, auto_start=True)
            try:
                result: Any = func(*args, **kwargs)
            except Exception:
                if t.is_running:
                    t.stop()
                raise
            else:
                t.stop()
                if display_mode != "none":
                    format_duration(
                        t.duration_ns,
                        t.start_date,
                        t.end_date,
                        mode=display_mode,
                    )
                return result

        return wrapper

    return decorator


# ── Formatting ────────────────────────────────────────────────────────────────


def format_duration(
    duration_ns: int,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    *,
    mode: DisplayMode = "standard",
) -> str | None:
    """Format and print duration with Rich console.

    Args:
        duration_ns: Duration in nanoseconds.
        start_date: Start datetime.
        end_date: End datetime.
        mode: Display mode.

    Returns:
        Formatted time string, or ``None`` if mode is ``"none"``.
    """
    if mode == "none":
        return None

    secs, remainder = divmod(duration_ns, 1_000_000_000)
    ms, remainder = divmod(remainder, 1_000_000)
    us, ns = divmod(remainder, 1_000)
    hrs, remainder = divmod(secs, 3600)
    mins, secs = divmod(remainder, 60)

    time_str = f"{hrs:02d}:{mins:02d}:{secs:02d}:{ms:03d}:{us:03d}:{ns:03d}"

    if mode == "minimal":
        return _print_minimal(time_str)
    if mode == "verbose":
        return _print_verbose(time_str, start_date, end_date, duration_ns)
    return _print_standard(time_str, start_date, end_date)


# ── Private helpers ───────────────────────────────────────────────────────────


def _fmt_dt(dt: datetime) -> str:
    """Format datetime for Rich markup display."""
    return f"[yellow]{dt.year}-{dt.month:02d}-{dt.day:02d} [white_bold]{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}"


def _print_minimal(time_str: str) -> str:
    """Print minimal timer output."""
    console.print(
        f"\n[white_bold]╚═══ EXECUTION TIME ═══╝\n"
        f"[yellow_bold]HH:MM:SS:ms :µs :ns\n"
        f"[white_bold]{time_str}\n"
        f"[red_bold]^^^^^^^^^^^^",
    )
    return time_str


def _print_standard(
    time_str: str,
    start_date: datetime | None,
    end_date: datetime | None,
) -> str:
    """Print standard timer output with START/END dates."""
    start = _fmt_dt(start_date) if start_date else "N/A"
    end = _fmt_dt(end_date) if end_date else "N/A"

    console.print(
        f"\n[white_bold]╚═══════════ EXECUTION TIME ═══════════╝\n"
        f"[yellow_bold]        YYYY-MM-DD HH:MM:SS:ms :µs :ns\n"
        f"[red_bold][[white_bold]START[red_bold]] {start}\n"
        f"[red_bold][[white_bold]END[red_bold]]   {end}\n"
        f"[red_bold][[white_bold]TIME[red_bold]]  "
        f"[yellow_bold]YYYY-MM-DD [white_bold]{time_str}\n"
        f"[red_bold]                   ^^^^^^^^^^^^",
    )
    return time_str


def _print_verbose(
    time_str: str,
    start_date: datetime | None,
    end_date: datetime | None,
    duration_ns: int,
) -> str:
    """Print verbose timer output with unit conversions."""
    start = _fmt_dt(start_date) if start_date else "N/A"
    end = _fmt_dt(end_date) if end_date else "N/A"

    h = duration_ns / 3_600_000_000_000
    m = duration_ns / 60_000_000_000
    s = duration_ns / 1_000_000_000

    console.print(
        f"\n[white_bold]╚═══════════ EXECUTION TIME ═══════════╝\n"
        f"[yellow_bold]        YYYY-MM-DD HH:MM:SS:ms :µs :ns\n"
        f"[red_bold][[white_bold]START[red_bold]] {start}\n"
        f"[red_bold][[white_bold]END[red_bold]]   {end}\n"
        f"[red_bold][[white_bold]TIME[red_bold]]  "
        f"[yellow_bold]YYYY-MM-DD [white_bold]{time_str}\n"
        f"[red_bold]                   ^^^^^^^^^^^^\n"
        f"[red_bold][[white_bold]TIME[red_bold]]  [white_bold]{h:.9f} hours\n"
        f"[red_bold][[white_bold]TIME[red_bold]]  [white_bold]{m:.9f} minutes\n"
        f"[red_bold][[white_bold]TIME[red_bold]]  [white_bold]{s:.9f} seconds",
    )
    return time_str
