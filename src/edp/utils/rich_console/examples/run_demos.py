"""Run visual demo scripts for the Rich Console System.

Usage (adjust ``<pkg>`` to your install path):

    python -m <pkg>.rich_console.examples --all
    python -m <pkg>.rich_console.examples --theme
    python -m <pkg>.rich_console.examples --colors
    python -m <pkg>.rich_console.examples --utilities
    python -m <pkg>.rich_console.examples --progress
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Final

from ..console import console

__all__ = ["main"]

DemoRunner = Callable[[], None]
"""A demo entry point invoked with no arguments."""


def _run_theme_demo() -> None:
    """Run the full theme demonstration."""
    from .demo_theme import run_all_demos

    run_all_demos()


def _run_colors_demo() -> None:
    """Run the auto-highlighting color demonstration."""
    from .demo_colors import demo_colors

    demo_colors()


def _run_utilities_demo() -> None:
    """Run the utilities demonstration."""
    from .demo_utilities import run_all_demos

    run_all_demos()


def _run_progress_demo() -> None:
    """Run the progress bar demonstration."""
    from .demo_progress import run_all_demos

    run_all_demos()


DEMO_RUNNERS: Final[dict[str, tuple[DemoRunner, ...]]] = {
    "--all": (
        _run_theme_demo,
        _run_colors_demo,
        _run_utilities_demo,
        _run_progress_demo,
    ),
    "--theme": (_run_theme_demo,),
    "--colors": (_run_colors_demo,),
    "--utilities": (_run_utilities_demo,),
    "--progress": (_run_progress_demo,),
}
"""CLI flag mapped to the demo runners it triggers."""

USAGE: Final[str] = (
    f"Usage: python -m {__package__ or 'rich_console.examples'} [--all|--theme|--colors|--utilities|--progress]"
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

    for runner in runners:
        runner()


if __name__ == "__main__":
    main()
