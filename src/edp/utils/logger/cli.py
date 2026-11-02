"""CLI for viewing structured JSON log files.

Provide filtering by level, time window, logger name, and text search.
Support table and statistics display modes.

Usage (adjust ``<pkg>`` to your install path):

    python -m <pkg>.logger.cli <log_file> [options]
    python -m <pkg>.logger.cli logs/app.log --recent 10
    python -m <pkg>.logger.cli logs/app.log --level ERROR --table
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Final

from ..rich_console import console
from .log_reader import LogReader
from .log_viewer import LogViewer

__all__ = ["main"]


def main() -> None:
    """Main CLI entry point."""
    args = sys.argv[1:]

    if not args or "--help" in args or "-h" in args:
        print_help()
        return

    log_file = args[0]

    if not Path(log_file).exists():
        console.print(f"[red]Error: File not found: {log_file}[/red]")
        return

    options = parse_args(args[1:])

    reader = LogReader(log_file)
    viewer = LogViewer()

    logs = apply_filters(reader, options)

    if options.get("stats"):
        viewer.display_with_stats(logs)
    elif options.get("table"):
        viewer.display_table(logs)
    else:
        viewer.display(logs)


_VALUE_ARGS: Final[dict[str, tuple[str, type]]] = {
    "--recent": ("recent", int),
    "-n": ("recent", int),
    "--level": ("level", str),
    "-l": ("level", str),
    "--minutes": ("minutes", int),
    "-m": ("minutes", int),
    "--hours": ("hours", int),
    "-H": ("hours", int),
    "--logger": ("logger", str),
    "-L": ("logger", str),
    "--search": ("search", str),
    "-s": ("search", str),
}
"""Flags that consume a following value, mapped to (option_key, parser)."""

_FLAG_ARGS: Final[dict[str, str]] = {
    "--table": "table",
    "--stats": "stats",
}
"""Boolean flags mapped to their option key."""


def _parse_int_arg(name: str, value: str) -> int | None:
    """Parse an integer argument, printing a warning on failure.

    Args:
        name: Argument name for the error message.
        value: Raw string value to parse.

    Returns:
        Parsed integer or None if invalid.
    """
    try:
        return int(value)
    except ValueError:
        console.print(f"[yellow]Warning: invalid value for {name}: {value!r}[/yellow]")
        return None


def parse_args(args: list[str]) -> dict[str, Any]:
    """Parse command-line arguments.

    Args:
        args: Argument list.

    Returns:
        Options dictionary.
    """
    options: dict[str, Any] = {}
    i = 0

    while i < len(args):
        arg = args[i]

        if arg in _VALUE_ARGS:
            key, typ = _VALUE_ARGS[arg]
            if i + 1 < len(args):
                raw = args[i + 1]
                if typ is int:
                    val = _parse_int_arg(arg, raw)
                    if val is not None:
                        options[key] = val
                else:
                    options[key] = raw
                i += 2
            else:
                i += 1
        elif arg in _FLAG_ARGS:
            options[_FLAG_ARGS[arg]] = True
            i += 1
        else:
            i += 1

    return options


def apply_filters(reader: LogReader, options: dict[str, Any]) -> list[dict[str, Any]]:
    """Apply filters based on options.

    Args:
        reader: Log reader instance.
        options: Options dictionary.

    Returns:
        Filtered logs.
    """
    logs = reader.read_all()

    if "minutes" in options:
        logs = reader.filter_by_time(minutes=options["minutes"])
    elif "hours" in options:
        logs = reader.filter_by_time(hours=options["hours"])

    if "level" in options:
        logs = [log for log in logs if log.get("level") == options["level"].upper()]

    if "logger" in options:
        logs = [log for log in logs if options["logger"].lower() in log.get("logger", "").lower()]

    if "search" in options:
        search = options["search"].lower()
        logs = [log for log in logs if search in log.get("message", "").lower()]

    if "recent" in options:
        logs = logs[-options["recent"] :][::-1]

    return logs


def print_help() -> None:
    """Print help message."""
    console.print("""[ruby_red_bold]Log Viewer CLI[/ruby_red_bold]

[white_bold]Usage:[/white_bold]
  python -m <pkg>.logger.cli <log_file> [options]

[white_bold]Options:[/white_bold]
  --recent, -n <count>     Show N most recent logs
  --level, -l <level>      Filter by level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  --minutes, -m <minutes>  Show logs from last N minutes
  --hours, -H <hours>      Show logs from last N hours
  --logger, -L <name>      Filter by logger name
  --search, -s <text>      Search in message content
  --table                  Display as table
  --stats                  Show statistics
  --help, -h               Show this help

[white_bold]Examples:[/white_bold]
  python -m <pkg>.logger.cli logs/app.log --recent 10
  python -m <pkg>.logger.cli logs/app.log --level ERROR
  python -m <pkg>.logger.cli logs/app.log --minutes 30 --table
  python -m <pkg>.logger.cli logs/app.log --stats
""")


if __name__ == "__main__":
    main()
