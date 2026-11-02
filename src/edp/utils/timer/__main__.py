"""Run timer visual demo: ``python -m <pkg>.timer``."""

from __future__ import annotations

import time

from ..rich_console import console
from . import ExecutionTimer, timed


def main() -> None:
    """Demonstrate all timer display modes and the ``@timed`` decorator."""
    console.rule("[ruby_red_bold]Timer Module Demo[/ruby_red_bold]")

    console.print("\n[white_bold]1. ExecutionTimer — MINIMAL mode:[/white_bold]")
    with ExecutionTimer("Task", display_mode="minimal"):
        time.sleep(0.05)

    console.print("\n[white_bold]2. ExecutionTimer — STANDARD mode (default):[/white_bold]")
    with ExecutionTimer("Task", display_mode="standard"):
        time.sleep(0.05)

    console.print("\n[white_bold]3. ExecutionTimer — VERBOSE mode:[/white_bold]")
    with ExecutionTimer("Task", display_mode="verbose"):
        time.sleep(0.05)

    console.print("\n[white_bold]4. ExecutionTimer — NONE mode (silent):[/white_bold]")
    with ExecutionTimer("Task", display_mode="none") as t:
        time.sleep(0.05)
    console.print(f"  Raw duration: {t.get_duration_ns():,} ns")

    console.print("\n[white_bold]5. @timed decorator:[/white_bold]")

    @timed(display_mode="standard")
    def example_function() -> int:
        time.sleep(0.05)
        return 42

    result = example_function()
    console.print(f"  Return value: {result}")

    console.rule("[ruby_red_bold]Done[/ruby_red_bold]")


if __name__ == "__main__":
    main()
