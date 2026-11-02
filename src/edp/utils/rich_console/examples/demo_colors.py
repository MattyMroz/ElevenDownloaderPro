"""Demo auto-highlighting patterns in Rich console output.

Demonstrates all 8 auto-highlighted pattern types and bracket escaping.
Punctuation is intentionally NOT colored for readability.

Usage (via module entry point):

    python -m <pkg>.rich_console.examples --colors
"""

from __future__ import annotations

from typing import Final

from ..console import console

__all__ = ["demo_colors"]

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


def _demo_urls() -> None:
    """Print pattern type 1: URLs."""
    console.print("1. URLs (BLUE UNDERLINE):", style="white_bold")
    console.print("  https://example.com")
    console.print("  http://api.example.com/v1/users?page=3")
    console.print("  https://github.com/user/repo/releases/tag/v2.1.0")
    console.print()


def _demo_paths() -> None:
    """Print pattern type 2: file paths, including bracketed names."""
    console.print("2. File Paths (RUBY_RED):", style="white_bold")
    console.print("  Absolute: /home/user/.cache/models/v2.1.0")
    console.print(r"  Windows:  C:\Users\user\Documents\project")
    console.print("  Relative 3+: output/dir_01/sub_03/")
    console.print("  With ext: dir_01/file_01.dat")
    bracketed_paths = [
        r"C:\Users\me\output\[draft] Report Final - v2.pdf",
        r"C:\Users\me\output\[backup] Data Set - 03 (1080p) [checksum].zip",
        (
            r"C:\Users\me\output\TASK [module.core] Build Step - 01 "
            r"[stage-2] run - 2.00s notes.log"
        ),
        (
            r"C:\Users\me\output\JOB [tool+] Weekly Export - S01E01v2 "
            r"(REGION WEB-DL 1080p AVC AAC) [86445822] items 0.01s.log"
        ),
    ]
    for path in bracketed_paths:
        console.print(f"    [gray]-> {path}[/gray]")
    console.print("  NOT a path: 24/24 items (→ fraction)")
    console.print()


def _demo_booleans_and_none() -> None:
    """Print pattern types 3-4: booleans and None/null."""
    console.print("3. Booleans (GREEN / RED):", style="white_bold")
    console.print("  CUDA available: True")
    console.print("  Debug mode: False")
    console.print("  Config: verbose=TRUE, dry_run=FALSE")
    console.print()

    console.print("4. None/null (RED ITALIC):", style="white_bold")
    console.print("  Result: None")
    console.print("  Fallback: null")
    console.print("  Optional field: nil")
    console.print()


def _demo_versions_and_numbers() -> None:
    """Print pattern types 5-8: versions, number+unit, fractions, plain numbers."""
    console.print("5. Versions (RUBY_RED BOLD):", style="white_bold")
    console.print("  MyApp v2.1.0 starting")
    console.print("  Python 3.13.11")
    console.print("  torch 2.6.0+cu128")
    console.print("  v0.1.0-beta.2")
    console.print()

    console.print("6. Number + Unit (RUBY_RED BOLD):", style="white_bold")
    console.print("  Loaded in 1.33s")
    console.print("  Latency: 42ms (avg 27ms/item)")
    console.print("  File size: 245MB, cache: 1.2GB")
    console.print("  Resolution: 1920px x 1080px")
    console.print("  Framerate: 60fps, refresh: 144Hz")
    console.print()

    console.print("7. Slash-separated numbers (RUBY_RED BOLD):", style="white_bold")
    console.print("  Batch 3/5 done")
    console.print("  Detection: 156/156 regions complete")
    console.print("  Progress: 24/24 items processed")
    console.print("  LLM tokens: 20189/20255/40444")
    console.print()

    console.print("8. Numbers (RUBY_RED BOLD):", style="white_bold")
    console.print("  Integer: 42")
    console.print("  Float: 3.14159")
    console.print("  Count: 1024 items in 7 batches")
    console.print()


def _demo_bracket_escaping() -> None:
    """Print the bracket-escaping section."""
    print_section("BRACKET ESCAPING")
    console.print("  result[0] = 42")
    console.print("  array[1:3] sliced")
    console.print("  config[section] loaded")
    console.print()


def _demo_uncolored_punctuation() -> None:
    """Print the section showing punctuation left uncolored on purpose."""
    print_section("PUNCTUATION — NOT COLORED (INTENTIONAL)")
    console.print("  Colons:     key: value, time: 10:30:45")
    console.print("  Commas:     files: 24, size: 12MB, items: 156")
    console.print("  Parens:     func(x, y) → result")
    console.print("  Em-dash:    loaded — 3 profiles active")
    console.print("  Operators:  5 + 3 = 8, x > 5, a == b")
    console.print()


def _demo_real_world_logs() -> None:
    """Print the real-world log line examples section."""
    print_section("REAL-WORLD LOG EXAMPLES")
    console.print("  Loaded 4 models from /home/user/.cache/models in 3.45s")
    console.print("  Worker v2.1.0: processed 24/24 items, avg 42ms/item")
    console.print("  Pipeline complete: 156/156 regions, output: 245MB")
    console.print("  CUDA: True, torch 2.6.0+cu128, Python 3.13.11")
    console.print("  Saved to output/dir_01/sub_03/item_001.dat")
    console.print("  Config: debug=False, cache=None, workers=4")
    console.print("  API: https://api.example.com/v2/translate (latency: 127ms)")
    console.print()


def demo_colors() -> None:
    """Demonstrate all auto-highlight patterns and edge cases."""
    print_section("AUTO-HIGHLIGHTING — 8 PATTERN TYPES")
    _demo_urls()
    _demo_paths()
    _demo_booleans_and_none()
    _demo_versions_and_numbers()
    _demo_bracket_escaping()
    _demo_uncolored_punctuation()
    _demo_real_world_logs()


if __name__ == "__main__":
    demo_colors()
