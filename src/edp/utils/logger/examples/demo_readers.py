"""Demo LogReader, LogAggregator, LogViewer — reading and analyzing logs.

Demonstrate the chain-able LogReader API, aggregation, and Rich display.
Create a temporary log file for demonstration.

Usage (via module entry point):

    python -m <pkg>.logger.examples --readers
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path

from ...rich_console import console
from .. import LogAggregator, LogReader, LogViewer

__all__ = ["run_all_demos"]


def _create_sample_logs(path: Path) -> None:
    """Write sample JSONL entries for demo."""
    entries = [
        {"level": "INFO", "message": "Application started", "logger": "core", "timestamp": "2024-06-15T10:00:00"},
        {
            "level": "DEBUG",
            "message": "Loading config from disk",
            "logger": "config",
            "timestamp": "2024-06-15T10:00:01",
        },
        {"level": "INFO", "message": "Database connected", "logger": "db", "timestamp": "2024-06-15T10:00:02"},
        {
            "level": "WARNING",
            "message": "Slow query detected (450ms)",
            "logger": "db",
            "timestamp": "2024-06-15T10:01:00",
            "context": {"query": "SELECT *", "duration_ms": 450},
        },
        {
            "level": "ERROR",
            "message": "Connection pool exhausted",
            "logger": "db",
            "timestamp": "2024-06-15T10:02:00",
            "exception": "ConnectionError: pool full",
        },
        {"level": "INFO", "message": "Retrying connection", "logger": "db", "timestamp": "2024-06-15T10:02:01"},
        {"level": "SUCCESS", "message": "Connection restored", "logger": "db", "timestamp": "2024-06-15T10:02:05"},
        {
            "level": "INFO",
            "message": "Processing batch 1/3",
            "logger": "worker",
            "timestamp": "2024-06-15T10:03:00",
            "context": {"operation": "batch", "duration_ms": 120},
        },
        {
            "level": "INFO",
            "message": "Processing batch 2/3",
            "logger": "worker",
            "timestamp": "2024-06-15T10:03:30",
            "context": {"operation": "batch", "duration_ms": 95},
        },
        {
            "level": "INFO",
            "message": "Processing batch 3/3",
            "logger": "worker",
            "timestamp": "2024-06-15T10:04:00",
            "context": {"operation": "batch", "duration_ms": 140},
        },
        {
            "level": "ERROR",
            "message": "Failed to send notification",
            "logger": "notify",
            "timestamp": "2024-06-15T10:05:00",
            "exception": "TimeoutError: SMTP timeout",
        },
        {"level": "INFO", "message": "Shutdown complete", "logger": "core", "timestamp": "2024-06-15T10:06:00"},
    ]
    with path.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def demo_chain_reader() -> Path:
    """Demonstrate chain-able LogReader API."""
    console.rule("[ruby_red_bold]Chain-able LogReader[/ruby_red_bold]")

    tmp = Path(tempfile.mkdtemp()) / "demo.log.jsonl"
    _create_sample_logs(tmp)
    console.print(f"[gray]Created sample log: {tmp}[/gray]")
    console.print()

    reader = LogReader(tmp)

    total = reader.load().count()
    console.print(f"[white_bold]Total logs:[/white_bold] {total}")

    errors = reader.load().filter_by_level("ERROR").to_list()
    console.print(f"[white_bold]Errors:[/white_bold] {len(errors)}")
    for err in errors:
        console.print(f"  [red]• {err['message']}[/red]")

    db_logs = reader.load().filter_by_logger("db").count()
    console.print(f"[white_bold]DB logs:[/white_bold] {db_logs}")

    db_errors = reader.load().filter_by_logger("db").filter_by_level("ERROR").to_list()
    console.print(f"[white_bold]DB errors:[/white_bold] {len(db_errors)}")

    time_filtered = (
        reader.load()
        .filter_by_time(
            start=datetime(2024, 6, 15, 10, 2),
            end=datetime(2024, 6, 15, 10, 4),
        )
        .count()
    )
    console.print(f"[white_bold]Logs 10:02-10:04:[/white_bold] {time_filtered}")

    first = reader.load().first(2)
    console.print(f"[white_bold]First 2:[/white_bold] {[entry['message'] for entry in first]}")

    last = reader.load().last(2)
    console.print(f"[white_bold]Last 2:[/white_bold] {[entry['message'] for entry in last]}")

    return tmp


def demo_aggregator(log_file: Path) -> None:
    """Demonstrate LogAggregator analysis."""
    console.rule("[ruby_red_bold]LogAggregator[/ruby_red_bold]")

    reader = LogReader(log_file)
    logs = reader.load().to_list()
    agg = LogAggregator(logs)

    by_level = agg.count_by_level()
    console.print("[white_bold]By level:[/white_bold]")
    for level, count in sorted(by_level.items()):
        console.print(f"  {level:<10} {count}")

    by_logger = agg.count_by_logger()
    console.print("[white_bold]By logger:[/white_bold]")
    for name, count in sorted(by_logger.items(), key=lambda x: -x[1]):
        console.print(f"  {name:<10} {count}")

    timeline = agg.timeline(interval="hour")
    console.print("[white_bold]Timeline (hourly):[/white_bold]")
    for point in timeline:
        bucket = point["time"]
        total = sum(v for k, v in point.items() if k != "time")
        console.print(f"  {bucket}  {'█' * total} ({total})")

    error_summary = agg.error_summary()
    if error_summary["total_errors"]:
        console.print("[white_bold]Error summary:[/white_bold]")
        console.print(f"  Total errors: {error_summary['total_errors']}")
        console.print(f"  Unique messages: {error_summary['unique_messages']}")
        for logger_name, count in error_summary["by_logger"].items():
            console.print(f"  [red]• {logger_name}: {count}[/red]")


def demo_viewer(log_file: Path) -> None:
    """Demonstrate LogViewer Rich display."""
    console.rule("[ruby_red_bold]LogViewer[/ruby_red_bold]")

    reader = LogReader(log_file)
    logs = reader.load().to_list()
    viewer = LogViewer()

    console.print("[white_bold]display() — formatted log entries:[/white_bold]")
    viewer.display(logs[:4])
    console.print()

    console.print("[white_bold]display_table() — table view:[/white_bold]")
    viewer.display_table(logs[:4])
    console.print()

    console.print("[white_bold]display_with_stats() — logs + statistics panel:[/white_bold]")
    viewer.display_with_stats(logs)


def run_all_demos() -> None:
    """Run all reader/aggregator/viewer demos."""
    console.rule("[ruby_red_bold]Readers & Viewer Demo[/ruby_red_bold]", style="ruby_red")
    console.print()

    log_file = demo_chain_reader()
    console.print()

    demo_aggregator(log_file)
    console.print()

    demo_viewer(log_file)
    console.print()
