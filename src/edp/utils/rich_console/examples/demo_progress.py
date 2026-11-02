"""Demo progress bar system — all styles and modular features.

Demonstrate ProgressBarManager capabilities:
- Unknown progress (spinner)
- Standard 4-color transition
- Full palette 13-color transition
- Custom chars (█░, ﷼)
- All colors palette showcase
- Download mode with bytes + speed (show_download=True)
- ETA with time remaining (show_eta=True)
- Modular component mixing (spinner, bar, percentage, elapsed, bytes)
- Description truncation modes (end, start, middle)
- Multi-task concurrent bars with independent per-task colors
- Multi-task per-row configuration (each row its own columns and colors)
- Multi-task alignment modes (aligned columns vs independent bar widths)
- Multi-task thread-safe parallel workers

Usage (via module entry point):

    python -m <pkg>.rich_console.examples --progress
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Final, Literal

from ..console import console
from ..progress import MultiProgressManager, ProgressBarManager

if TYPE_CHECKING:
    from rich.progress import TaskID

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


def _run_per_row_config(align: Literal["aligned", "independent"]) -> None:
    """Animate the same six differently-configured rows in one align mode."""
    ocean_colors = {
        33: ("blue_bold", "blue_bold"),
        66: ("purple_bold", "purple_bold"),
        100: ("pink_bold", "pink_bold"),
    }
    download_total = 40_000_000
    with MultiProgressManager(align=align) as mp:
        download = mp.add_task("tools.zip", total=download_total, show_download=True, show_eta=True)
        percent_only = mp.add_task("data.bin", show_elapsed=False)
        spinner = mp.add_task("Analyzing data...", show_spinner=True, show_percentage=False)
        eta_only = mp.add_task("Waiting", show_bar=False, show_percentage=False, show_elapsed=False, show_eta=True)
        colored = mp.add_task("ocean_colors", colors=ocean_colors)
        truncated = mp.add_task("very_long_file_name_that_gets_truncated.bin")
        for _step in range(100):
            mp.advance(download, download_total // 100)
            mp.advance(percent_only, 1)
            mp.advance(spinner, 1)
            mp.advance(eta_only, 1)
            mp.advance(colored, 1)
            mp.advance(truncated, 1)
            time.sleep(0.04)


def _demo_core_styles() -> None:
    """Run demos 1-6: unknown progress, color transitions, custom chars."""
    console.print("1. Unknown Progress (no total):", style="white_bold")
    with ProgressBarManager("Processing unknown amount", total=None, bar="rich", show_percentage=False) as pb:
        time.sleep(1.5)

    console.print("\n2. Standard 4-Color (RICH):", style="white_bold")
    with ProgressBarManager("Processing data", total=100, bar="rich") as pb:
        for _i in range(100):
            pb.advance(1)
            time.sleep(0.02)

    console.print("\n3. Full Palette 13-Color (BLOCKS):", style="white_bold")
    with ProgressBarManager(
        "Loading colors",
        total=100,
        bar="blocks",
        colors={
            8: ("purple_bold", "purple_bold"),
            16: ("ruby_red_bold", "ruby_red_bold"),
            24: ("pink_bold", "pink_bold"),
            32: ("red_bold", "red_bold"),
            40: ("brown_bold", "brown_bold"),
            48: ("orange_bold", "orange_bold"),
            56: ("yellow_bold", "yellow_bold"),
            64: ("green_bold", "green_bold"),
            72: ("blue_bold", "blue_bold"),
            80: ("white_bold", "white_bold"),
            88: ("normal_bold", "normal_bold"),
            92: ("gray_bold", "gray_bold"),
            100: ("black_bold", "black_bold"),
        },
    ) as pb:
        for _i in range(100):
            pb.advance(1)
            time.sleep(0.05)

    console.print("\n4. Custom Chars (█░):", style="white_bold")
    with ProgressBarManager("Custom blocks", total=50, bar="custom", custom_chars=("█", "░")) as pb:
        for _i in range(50):
            pb.advance(1)
            time.sleep(0.02)

    console.print("\n5. ALL Colors Demo (every color from palette):", style="white_bold")
    all_colors = [
        ("purple_bold", 8),
        ("ruby_red_bold", 8),
        ("pink_bold", 8),
        ("red_bold", 8),
        ("brown_bold", 8),
        ("orange_bold", 8),
        ("yellow_bold", 8),
        ("green_bold", 8),
        ("blue_bold", 8),
        ("white_bold", 8),
        ("normal_bold", 8),
        ("gray_bold", 8),
        ("black_bold", 8),
    ]

    for color_name, steps in all_colors:
        color_display = color_name.replace("_bold", "").upper()
        with ProgressBarManager(
            f"{color_display:12s}",
            total=steps,
            bar="blocks",
            colors={steps: (color_name, color_name)},
        ) as pb:
            for _i in range(steps):
                pb.advance(1)
                time.sleep(0.01)

    console.print("\n6. Custom Chars (﷼ space) ARABIC:", style="white_bold")
    with ProgressBarManager("Custom ARABIC", total=50, bar="custom", custom_chars=("﷼", " ")) as pb:
        for _i in range(50):
            pb.advance(1)
            time.sleep(0.02)


def _demo_download_mode() -> None:
    """Run demos 7-9: download mode with bytes + speed, one per bar style."""
    print_section("MODULAR FEATURES - Download with bytes + speed")

    console.print("7. DOWNLOAD with bytes + speed (bar='rich'):", style="white_bold")
    with ProgressBarManager(
        "large_dataset.zip",
        total=100_000_000,
        bar="rich",
        show_download=True,
        show_eta=True,
    ) as pb:
        for _i in range(100):
            pb.advance(1_000_000)
            time.sleep(0.05)

    console.print("\n8. DOWNLOAD with bytes + speed (bar='blocks'):", style="white_bold")
    with ProgressBarManager(
        "video_file.mp4",
        total=250_000_000,
        bar="blocks",
        show_download=True,
        show_eta=True,
        colors={
            33: ("red_bold", "red_bold"),
            66: ("yellow_bold", "yellow_bold"),
            100: ("green_bold", "green_bold"),
        },
    ) as pb:
        for _i in range(100):
            pb.advance(2_500_000)
            time.sleep(0.05)

    console.print("\n9. DOWNLOAD with bytes + speed (bar='custom' █░):", style="white_bold")
    with ProgressBarManager(
        "archive.tar.gz",
        total=50_000_000,
        bar="custom",
        custom_chars=("█", "░"),
        show_download=True,
        show_eta=True,
        colors={
            25: ("ruby_red_bold", "ruby_red_bold"),
            50: ("orange_bold", "orange_bold"),
            75: ("yellow_bold", "yellow_bold"),
            100: ("green_bold", "green_bold"),
        },
    ) as pb:
        for _i in range(100):
            pb.advance(500_000)
            time.sleep(0.05)


def _demo_modular_mixing() -> None:
    """Run demos 10-16: mix any subset of components (spinner/bar/eta/bytes/...)."""
    print_section("FULL MODULARITY - Mix ANY components!")

    console.print("10. ONLY SPINNER (nothing else):", style="white_bold")
    with ProgressBarManager("Thinking...", total=None, show_spinner=True, show_elapsed=False) as pb:
        time.sleep(1.5)

    console.print("\n11. ONLY TIME (elapsed only):", style="white_bold")
    with ProgressBarManager(
        "Timer",
        total=100,
        show_bar=False,
        show_percentage=False,
        show_elapsed=True,
        colors={100: ("green_bold", "green_bold")},
    ) as pb:
        for _i in range(100):
            pb.advance(1)
            time.sleep(0.02)

    console.print("\n12. ONLY PERCENTAGE (no bar, no time):", style="white_bold")
    with ProgressBarManager("Counting", total=50, show_bar=False, show_percentage=True, show_elapsed=False) as pb:
        for _i in range(50):
            pb.advance(1)
            time.sleep(0.03)

    console.print("\n13. ONLY ETA (remaining time only):", style="white_bold")
    with ProgressBarManager(
        "Waiting",
        total=50,
        show_bar=False,
        show_percentage=False,
        show_eta=True,
        show_elapsed=False,
    ) as pb:
        for _i in range(50):
            pb.advance(1)
            time.sleep(0.03)

    console.print("\n14. ONLY BYTES (no speed, no bar, no time):", style="white_bold")
    with ProgressBarManager(
        "Downloading",
        total=50_000_000,
        show_bar=False,
        show_percentage=False,
        show_download=True,
        show_speed=False,
        show_elapsed=False,
        show_eta=False,
    ) as pb:
        for _i in range(100):
            pb.advance(500_000)
            time.sleep(0.03)

    console.print("\n15. SPINNER + DOWNLOAD (spinner with bytes):", style="white_bold")
    with ProgressBarManager(
        "Syncing...",
        total=30_000_000,
        show_spinner=True,
        show_download=True,
        show_percentage=True,
        show_elapsed=True,
    ) as pb:
        for _i in range(100):
            pb.advance(300_000)
            time.sleep(0.03)

    console.print("\n16. ONLY NAME (description only - nothing else!):", style="white_bold")
    with ProgressBarManager("Done!", total=10, show_bar=False, show_percentage=False, show_elapsed=False) as pb:
        for _i in range(10):
            pb.advance(1)
            time.sleep(0.1)


def _demo_truncate_modes() -> None:
    """Run demos 17-24: description truncation modes and edge cases."""
    print_section("TRUNCATE MODES - Description length control")

    console.print("17. TRUNCATE END (start...):", style="white_bold")
    with ProgressBarManager(
        "very_long_filename_example_that_should_be_truncated.zip",
        total=50,
        max_description_length=25,
        truncate_mode="end",
    ) as pb:
        for _i in range(50):
            pb.advance(1)
            time.sleep(0.02)

    console.print("\n18. TRUNCATE START (...end):", style="white_bold")
    with ProgressBarManager(
        "very_long_filename_example_that_should_be_truncated.zip",
        total=50,
        max_description_length=25,
        truncate_mode="start",
    ) as pb:
        for _i in range(50):
            pb.advance(1)
            time.sleep(0.02)

    console.print("\n19. TRUNCATE MIDDLE (mid...dle):", style="white_bold")
    with ProgressBarManager(
        "very_long_filename_example_that_should_be_truncated.zip",
        total=50,
        max_description_length=25,
        truncate_mode="middle",
    ) as pb:
        for _i in range(50):
            pb.advance(1)
            time.sleep(0.02)

    console.print("\n20. MINIMUM LENGTH (5 chars - '1...6'):", style="white_bold")
    with ProgressBarManager("123456789", total=30, max_description_length=5, truncate_mode="middle") as pb:
        for _i in range(30):
            pb.advance(1)
            time.sleep(0.02)

    console.print("\n21. SHORT NAME (no truncate needed):", style="white_bold")
    with ProgressBarManager("abc", total=30, max_description_length=25) as pb:
        for _i in range(30):
            pb.advance(1)
            time.sleep(0.02)

    console.print("\n22. EMPTY NAME (edge case):", style="white_bold")
    with ProgressBarManager("", total=20, max_description_length=10) as pb:
        for _i in range(20):
            pb.advance(1)
            time.sleep(0.03)

    console.print("\n24. INVALID TRUNCATE MODE (fallback to 'end'):", style="white_bold")
    with ProgressBarManager(
        "test_invalid_mode.zip",
        total=30,
        max_description_length=10,
        truncate_mode="invalid",  # type: ignore[arg-type]  # intentional: test fallback
    ) as pb:
        for _i in range(30):
            pb.advance(1)
            time.sleep(0.02)


def _demo_multi_task() -> None:
    """Run demos 25-28: multi-task concurrent bars, per-row config, workers."""
    print_section("MULTI-TASK - Many bars in one live display")

    console.print("25. MULTI-TASK DOWNLOAD (concurrent bars, independent colors):", style="white_bold")
    fast_total = 89_000_000
    slow_total = 169_000_000
    with MultiProgressManager(show_download=True) as mp:
        fast = mp.add_task("fast.zip", total=fast_total)
        slow = mp.add_task("slow.zip", total=slow_total)
        for _step in range(100):
            mp.advance(fast, fast_total // 100)
            mp.advance(slow, slow_total // 200)
            time.sleep(0.02)
        mp.update(slow, slow_total)

    console.print("\n26. MULTI-TASK PER-ROW CONFIG - ALIGNED (columns line up):", style="white_bold")
    _run_per_row_config("aligned")

    console.print("\n27. MULTI-TASK PARALLEL WORKERS (thread-safe updates):", style="white_bold")
    with MultiProgressManager(show_download=True, show_eta=True) as mp:
        worker_tasks = [mp.add_task(f"worker-{index}.bin", total=(index + 1) * 10_000_000) for index in range(4)]

        def _worker(task_id: TaskID, chunk: int) -> None:
            for _step in range(100):
                mp.advance(task_id, chunk)
                time.sleep(0.02)

        workers = [
            threading.Thread(target=_worker, args=(task_id, (index + 1) * 100_000))
            for index, task_id in enumerate(worker_tasks)
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()

    console.print(
        "\n28. MULTI-TASK PER-ROW CONFIG - INDEPENDENT (values glued to each bar):",
        style="white_bold",
    )
    _run_per_row_config("independent")


def _print_summary() -> None:
    """Print the demo suite summary section."""
    print_section("DEMO SUMMARY")
    console.print("  • 6 demos: Core styles (rich, blocks, custom chars)", style="white_bold")
    console.print("  • 3 demos: Download mode (bytes + speed)", style="white_bold")
    console.print("  • 7 demos: Modular components (mix any features)", style="white_bold")
    console.print("  • 7 demos: Truncation modes (end, start, middle + edge cases)", style="white_bold")
    console.print("  • 4 demos: Multi-task (download, aligned vs independent, workers)", style="white_bold")
    console.print("  • Total: 27 demos", style="white_bold")


def run_all_demos() -> None:
    """Run complete progress bar demo suite."""
    print_section("PROGRESS BAR SYSTEM TESTS")
    _demo_core_styles()
    _demo_download_mode()
    _demo_modular_mixing()
    _demo_truncate_modes()
    _demo_multi_task()
    _print_summary()


if __name__ == "__main__":
    run_all_demos()
