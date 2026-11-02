"""Demo Rich Console utility functions.

Demonstrates status icons, byte formatting, duration formatting,
percentage formatting, and auto-highlighting.

Usage (via module entry point):

    python -m <pkg>.rich_console.examples --utilities
"""

from __future__ import annotations

from typing import Final

from .. import (
    StatusType,
    console,
    format_bytes,
    format_duration,
    format_percentage,
    get_status_icon,
)

__all__ = ["run_all_demos"]

# ── Constants ─────────────────────────────────────────────────────────────────

HEADER_WIDTH: Final[int] = 70
"""Character width of demo section headers."""

SECTION_SEPARATOR: Final[str] = "═" * HEADER_WIDTH
"""Horizontal rule printed above and below each section title."""


# ── Helpers ───────────────────────────────────────────────────────────────────


def print_section(title: str) -> None:
    """Print section header with centered title."""
    console.print(f"\n{SECTION_SEPARATOR}")
    console.print(title.center(HEADER_WIDTH), style="white_bold")
    console.print(f"{SECTION_SEPARATOR}\n")


# ── Demo Functions ────────────────────────────────────────────────────────────


def demo_status_icons() -> None:
    """Demonstrate status icon function with all available icons."""
    print_section("STATUS ICONS")

    console.print("Available Icons:")
    statuses: list[StatusType] = [
        "success",
        "error",
        "warning",
        "info",
        "debug",
        "critical",
        "pending",
        "running",
        "stopped",
    ]
    for status in statuses:
        console.print(f"  {get_status_icon(status)} {status.capitalize()}")

    console.print("\nUsage Examples:")
    console.print(f"  {get_status_icon('success')} Database connected")
    console.print(f"  {get_status_icon('error')} Connection failed")
    console.print(f"  {get_status_icon('warning')} Cache miss")
    console.print(f"  {get_status_icon('running')} Processing batch 5/10")
    console.print(f"  {get_status_icon('pending')} Waiting for approval")


def demo_format_bytes() -> None:
    """Demonstrate byte size formatting with binary and decimal units."""
    print_section("BYTE SIZE FORMATTING")

    console.print("Decimal Units (1000-based, KB/MB/GB) — default:")
    sizes_decimal: list[float] = [1000, 1000**2, 1000**3]
    labels_decimal = ["1 KB", "1 MB", "1 GB"]
    for decimal_label, decimal_size in zip(labels_decimal, sizes_decimal, strict=True):
        console.print(f"  {decimal_label:15} = {format_bytes(decimal_size)}")

    console.print("\nBinary Units (1024-based, KiB/MiB/GiB):")
    sizes_binary: list[float] = [1024, 1024**2 * 1.5, 1024**3 * 5, 1024**4 * 2.5]
    labels_binary = ["1 KiB", "1.5 MiB", "5 GiB", "2.5 TiB"]
    for binary_label, binary_size in zip(labels_binary, sizes_binary, strict=True):
        console.print(f"  {binary_label:15} = {format_bytes(binary_size, binary=True)}")

    console.print("\nReal-world Examples:")
    examples: dict[str, float] = {
        "Small file": 45678,
        "Image file": 1024**2 * 3.5,
        "Video file": 1024**3 * 1.2,
        "Database dump": 1024**3 * 15.7,
    }
    for example_label, example_size in examples.items():
        console.print(f"  {example_label:15} = {format_bytes(example_size)}")


def demo_format_duration() -> None:
    """Demonstrate time duration formatting."""
    print_section("TIME DURATION FORMATTING")

    console.print("Various Durations:")
    durations = [
        (0.5, "0.5 seconds"),
        (45, "45 seconds"),
        (90, "90 seconds"),
        (300, "5 minutes"),
        (3600, "1 hour"),
        (5400, "1.5 hours"),
        (9045, "2h 30m 45s"),
    ]
    for seconds, label in durations:
        console.print(f"  {label:15} = {format_duration(seconds)}")

    console.print("\nReal-world Examples:")
    examples = {
        "API response": 0.125,
        "Build time": 285,
        "Test suite": 1547,
        "Full backup": 7823,
    }
    for label, seconds in examples.items():
        console.print(f"  {label:15} = {format_duration(seconds)}")

    console.print("\nAuto-Highlighting Test (numbers should be ruby_red):")
    console.print("  Time: 0.5s 1.25s 45ms 123.45ms 3600s")
    console.print("  Size: 512B 1.5KB 2.5MB 10.75GB 3.14TB")
    console.print("  Memory: 256KiB 1024MiB 8.5GiB 16TiB")
    console.print("  Percent: 0% 25.5% 50% 75.25% 100%")
    console.print("  Mixed: Speed 10.5MB/s, Time 45.00s, Size 1.75GiB")


def demo_format_percentage() -> None:
    """Demonstrate percentage formatting."""
    print_section("PERCENTAGE FORMATTING")

    console.print("Basic Calculations:")
    examples = [
        (75, 100, None, "75 / 100"),
        (1, 3, 2, "1 / 3 (2 decimals)"),
        (50, 200, None, "50 / 200"),
        (100, 100, None, "100 / 100"),
    ]
    for current, total, precision, label in examples:
        if precision:
            result = format_percentage(current, total, precision=precision)
        else:
            result = format_percentage(current, total)
        console.print(f"  {label:20} = {result}")

    console.print("\nReal-world Examples:")
    real_examples = {
        "Test coverage": (1847, 2000),
        "Success rate": (9852, 10000),
        "Cache hit": (6543, 10000),
        "Error rate": (123, 10000),
    }
    for label, (current, total) in real_examples.items():
        console.print(f"  {label:15} = {format_percentage(current, total)}")


def demo_auto_highlighting() -> None:
    """Demonstrate auto-highlighting of special characters."""
    print_section("AUTO-HIGHLIGHTING")

    console.print("Special Characters (all should be ruby_red):")
    console.print("  ASCII Operators: + - * / % = < > ! & | ^")
    console.print("  ASCII Punctuation: @ # $ , . ; : ( ) [ ] { } ?")
    console.print("  Math Unicode: ≥ ≤ ± × ÷ ≠ ≈ ∞")
    console.print("  Arrows: → ← ↑ ↓ ↔ ⇒ ⇐")
    console.print("  Symbols: ™ ® © € £ ¥")
    console.print("  Backslash: \\ C:\\path\\file.txt")
    console.print("  Mixed: x ≥ 80%, y ≤ 50%, z ≠ 0")


def run_all_demos() -> None:
    """Run all utility demonstrations."""
    console.print(f"\n{SECTION_SEPARATOR}")
    console.print("RICH CONSOLE UTILITIES - Visual Test Suite".center(HEADER_WIDTH), style="white_bold")
    console.print(f"{SECTION_SEPARATOR}\n")

    demo_status_icons()
    demo_format_bytes()
    demo_format_duration()
    demo_format_percentage()
    demo_auto_highlighting()

    console.print(f"\n{SECTION_SEPARATOR}")
    console.print("Test Complete".center(HEADER_WIDTH), style="white_bold")
    console.print(f"{SECTION_SEPARATOR}\n")

    console.print("Summary:")
    console.print("  • Status icons: 9 types with styling")
    console.print("  • Byte formatting: Binary (KiB) and Decimal (KB)")
    console.print("  • Duration formatting: Human-readable time")
    console.print("  • Percentage formatting: Flexible precision")
    console.print("  • Auto-highlighting: Numbers and special chars")


if __name__ == "__main__":
    run_all_demos()
