"""Demo logger decorators — timed, timed_if, timed_debug, timed_in_dev.

Demonstrate automatic function timing decorators
and conditional timing based on environment.

Usage (via module entry point):

    python -m <pkg>.logger.examples --decorators
"""

from __future__ import annotations

import time

from ...rich_console import console
from .. import LoggerMode, setup_mode, timed, timed_debug, timed_if, timed_in_dev

__all__ = ["run_all_demos"]


@timed()
def slow_operation() -> str:
    """Simulate a slow operation."""
    time.sleep(0.05)
    return "done"


@timed("custom_name", level="DEBUG")
def named_operation() -> None:
    """Operation with custom timing name."""
    time.sleep(0.02)


@timed_if(lambda: True)
def conditional_always() -> None:
    """Timed only when condition is True."""
    time.sleep(0.01)


@timed_if(lambda: False)
def conditional_never() -> None:
    """Condition is False — no timing logged."""
    time.sleep(0.01)


@timed_debug()
def debug_only_timing() -> None:
    """Timed only when DEBUG env var is set."""
    time.sleep(0.01)


@timed_in_dev()
def dev_only_timing() -> None:
    """Timed only in DEV mode (LOGGER_MODE=DEV)."""
    time.sleep(0.01)


def run_all_demos() -> None:
    """Run all decorator demos."""
    console.rule("[ruby_red_bold]Decorators Demo[/ruby_red_bold]", style="ruby_red")
    console.print()

    setup_mode(LoggerMode.DEV, name="demo")

    console.print("[white_bold]@timed() — auto-logs function execution time:[/white_bold]")
    result = slow_operation()
    console.print(f"  Return value: {result}")
    console.print()

    console.print("[white_bold]@timed('custom_name', level='DEBUG') — custom name + level:[/white_bold]")
    named_operation()
    console.print()

    console.print("[white_bold]@timed_if(lambda: True) — conditional timing (True):[/white_bold]")
    conditional_always()
    console.print()

    console.print("[white_bold]@timed_if(lambda: False) — conditional timing (False = no log):[/white_bold]")
    conditional_never()
    console.print("  [gray](no timing logged — condition is False)[/gray]")
    console.print()

    console.print("[white_bold]@timed_debug() — only when DEBUG=true:[/white_bold]")
    debug_only_timing()
    console.print("  [gray](depends on DEBUG env var)[/gray]")
    console.print()

    console.print("[white_bold]@timed_in_dev() — only in DEV mode:[/white_bold]")
    dev_only_timing()
    console.print()
