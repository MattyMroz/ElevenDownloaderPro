"""Run visual demo scripts for the Logger System.

Usage (adjust ``<pkg>`` to your install path):

    python -m <pkg>.logger.examples --all
    python -m <pkg>.logger.examples --modes
    python -m <pkg>.logger.examples --decorators
    python -m <pkg>.logger.examples --readers
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Final

from ...rich_console import console

__all__ = ["main"]

DemoRunner = Callable[[], None]
"""A demo entry point invoked with no arguments."""


def _run_modes_demo() -> None:
    """Run the logger modes demonstration."""
    from .demo_modes import run_all_demos

    run_all_demos()


def _run_decorators_demo() -> None:
    """Run the decorators demonstration."""
    from .demo_decorators import run_all_demos

    run_all_demos()


def _run_readers_demo() -> None:
    """Run the readers and viewer demonstration."""
    from .demo_readers import run_all_demos

    run_all_demos()


def _run_realistic_demo() -> None:
    """Run the realistic app simulation."""
    from .demo_realistic import run_all_demos

    run_all_demos()


DEMO_RUNNERS: Final[dict[str, tuple[DemoRunner, ...]]] = {
    "--all": (
        _run_modes_demo,
        _run_decorators_demo,
        _run_readers_demo,
        _run_realistic_demo,
    ),
    "--modes": (_run_modes_demo,),
    "--decorators": (_run_decorators_demo,),
    "--readers": (_run_readers_demo,),
    "--realistic": (_run_realistic_demo,),
}
"""CLI flag mapped to the demo runners it triggers."""

USAGE: Final[str] = (
    f"Usage: python -m {__package__ or 'logger.examples'} [--all|--modes|--decorators|--readers|--realistic]"
)
"""One-line CLI usage string shown on bad or missing arguments."""


def _print_usage() -> None:
    """Display supported CLI arguments."""
    console.print(USAGE, style="warning")


def _resolve_runners(arguments: list[str]) -> tuple[list[DemoRunner], list[str]]:
    """Resolve CLI arguments to demo callables and invalid flags."""
    runners: list[DemoRunner] = []
    invalid_arguments: list[str] = []

    for argument in arguments:
        if argument in DEMO_RUNNERS:
            runners.extend(DEMO_RUNNERS[argument])
        else:
            invalid_arguments.append(argument)

    return runners, invalid_arguments


def main() -> None:
    """Parse CLI args and run selected demo modules."""
    if len(sys.argv) == 1:
        _print_usage()
        raise SystemExit(0)

    runners, invalid_arguments = _resolve_runners(sys.argv[1:])

    if invalid_arguments:
        console.print(f"Unknown argument(s): {', '.join(invalid_arguments)}", style="error")
        _print_usage()
        raise SystemExit(1)

    if not runners:
        _print_usage()
        raise SystemExit(0)

    for runner in runners:
        runner()
        console.print()
