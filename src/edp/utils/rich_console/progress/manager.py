"""Modular progress bar manager with dynamic color transitions.

Context manager with per-component show/hide flags, multiple bar styles,
spinner/download/time columns, and description truncation.

Usage:
    >>> # Standard 4-color transition
    >>> with ProgressBarManager("Processing", total=100) as pb:
    ...     pb.advance(50)

    >>> # Custom 6-color rainbow
    >>> colors = {
    ...     17: ("red_bold", "red_bold"),
    ...     34: ("orange_bold", "orange_bold"),
    ...     51: ("yellow_bold", "yellow_bold"),
    ...     67: ("green_bold", "green_bold"),
    ...     84: ("blue_bold", "blue_bold"),
    ...     100: ("purple_bold", "purple_bold")
    ... }
    >>> with ProgressBarManager("Rainbow", total=100, colors=colors) as pb:
    ...     pb.advance(50)

    >>> # Download with bytes + speed
    >>> with ProgressBarManager("file.zip", total=100_000_000,
    ...     show_download=True, show_speed=True) as pb:
    ...     pb.advance(10_000_000)

    >>> # Truncate long names
    >>> with ProgressBarManager("very_long_filename.zip", total=100,
    ...     max_description_length=15, truncate_mode="middle") as pb:
    ...     pb.advance(50)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final, Literal

from rich.markup import escape
from rich.progress import (
    BarColumn,
    Progress,
    ProgressColumn,
    Task,
    TaskID,
    TextColumn,
)
from rich.spinner import Spinner
from rich.text import Text

from ..console import console
from ..utilities import format_bytes

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from types import TracebackType

    from rich.console import RenderableType

__all__ = [
    "ProgressBarBuilder",
    "ProgressBarManager",
]

# ── Constants ─────────────────────────────────────────────────────────────────

_DEFAULT_EMPTY_COLOR: Final[str] = "gray_bold"
"""Default color for empty progress bar sections."""

_BASE_INFO_WIDTH: Final[int] = 23
"""Base info panel width in characters."""

_DOWNLOAD_COLUMN_WIDTH: Final[int] = 35
"""Additional width for download byte columns."""

_ETA_COLUMN_WIDTH: Final[int] = 15
"""Additional width for ETA column."""

_MAX_BAR_WITH_DOWNLOAD: Final[int] = 35
"""Maximum bar width when download columns are visible."""

_MAX_BAR_NORMAL: Final[int] = 40
"""Maximum bar width in standard mode."""

_MIN_BAR_WIDTH: Final[int] = 3
"""Minimum bar width to prevent degenerate display."""

_MAX_DESCRIPTION_DISPLAY: Final[int] = 20
"""Maximum description characters counted toward layout width."""

_STYLE_FIELD: Final[str] = "style"
"""Per-task field name that overrides a column's shared ``style_name``."""

# ── Shared Helpers ────────────────────────────────────────────────────────────


def _truncate_description(description: str, max_length: int, mode: Literal["start", "middle", "end"]) -> str:
    """Truncate description with ellipsis based on mode.

    Args:
        description: Text to truncate.
        max_length: Maximum length (raised to 5 when smaller).
        mode: Truncation mode; unknown values fall back to ``'end'``.

    Returns:
        The description, shortened with ``...`` when it exceeds the limit.
    """
    max_length = max(5, max_length)

    if not description or len(description) <= max_length:
        return description

    if mode not in ("start", "middle", "end"):
        mode = "end"

    if mode == "start":
        return "..." + description[-(max_length - 3) :]
    if mode == "middle":
        left_size = (max_length - 3) // 2
        right_size = max_length - 3 - left_size
        return description[:left_size] + "..." + description[-right_size:]
    return description[: max_length - 3] + "..."


def _style_description(color: str, description: str) -> str:
    """Wrap a description in a color tag, escaping it first.

    Task descriptions are markup-parsed by ``rich.Progress``, so bracketed
    names like ``[draft] file.mkv`` must be escaped or Rich eats them as tags.

    Args:
        color: Rich style name for the description text.
        description: Raw label; rendered verbatim, brackets included.

    Returns:
        Markup string safe to pass as a task description.
    """
    return f"[{color}]{escape(description)}"


def _color_for_percentage(colors: dict[int, tuple[str, str]], percentage: int) -> tuple[str, str]:
    """Return the ``(text_color, bar_color)`` pair for a progress percentage.

    Args:
        colors: Color transitions as ``{percentage: (text_color, bar_color)}``.
        percentage: Progress percentage (0-100).

    Returns:
        The pair of the first threshold at or above *percentage*, or the last
        pair when the percentage exceeds every threshold.
    """
    for threshold, pair in sorted(colors.items()):
        if percentage <= threshold:
            return pair
    return list(colors.values())[-1]


def _fit_bar_width(description: str, *, show_download: bool, show_eta: bool) -> int:
    """Fit the bar between the description and the enabled info columns.

    Args:
        description: Task description counted toward the layout width.
        show_download: Whether the bytes and speed columns take width.
        show_eta: Whether the ETA column takes width.

    Returns:
        Bar width in characters, clamped to the shared minimum and maximum.
    """
    console_width = console.width
    desc_length = min(len(description) + 2, _MAX_DESCRIPTION_DISPLAY)

    info_width = _BASE_INFO_WIDTH
    if show_download:
        info_width += _DOWNLOAD_COLUMN_WIDTH
    if show_eta:
        info_width += _ETA_COLUMN_WIDTH

    available_width = console_width - desc_length - info_width
    max_bar = _MAX_BAR_WITH_DOWNLOAD if show_download else _MAX_BAR_NORMAL
    return max(_MIN_BAR_WIDTH, min(max_bar, available_width))


# ── Progress Bar Builders ─────────────────────────────────────────────────────


class ProgressBarBuilder:
    """Factory for creating custom styled progress bars."""

    @staticmethod
    def blocks(width: int, progress: float, color: str, empty_color: str = _DEFAULT_EMPTY_COLOR) -> str:
        """Create block-style progress bar (█▌░).

        Args:
            width: Bar width in characters.
            progress: Completion ratio (0.0–1.0, clamped).
            color: Rich style for filled portion.
            empty_color: Rich style for empty portion.

        Returns:
            Rich-markup string with filled and empty blocks.

        Raises:
            ValueError: If width is less than 1.
        """
        if width < 1:
            msg = f"width must be >= 1, got {width}"
            raise ValueError(msg)
        progress = max(0.0, min(1.0, progress))
        filled: int = int(width * progress)
        empty: int = width - filled
        if progress >= 1.0:
            filled_str: str = "█" * filled
        elif filled > 0:
            filled_str = "█" * (filled - 1) + "▌"
        else:
            filled_str = ""
        empty_str: str = "░" * empty
        return f"[{color}]{filled_str}[/{color}][{empty_color}]{empty_str}[/{empty_color}]"

    @staticmethod
    def custom(width: int, progress: float, color: str, empty_color: str, filled_char: str, empty_char: str) -> str:
        """Create custom character progress bar.

        Args:
            width: Bar width in characters.
            progress: Completion ratio (0.0–1.0, clamped).
            color: Rich style for filled portion.
            empty_color: Rich style for empty portion.
            filled_char: Character for completed segments.
            empty_char: Character for remaining segments.

        Returns:
            Rich-markup string with custom characters.

        Raises:
            ValueError: If width is less than 1.
        """
        if width < 1:
            msg = f"width must be >= 1, got {width}"
            raise ValueError(msg)
        progress = max(0.0, min(1.0, progress))
        filled: int = int(width * progress)
        empty: int = width - filled
        return f"[{color}]{filled_char * filled}[/{color}][{empty_color}]{empty_char * empty}[/{empty_color}]"


# ── Custom Progress Columns ───────────────────────────────────────────────────


class DynamicSpinnerColumn(ProgressColumn):
    """Spinner column with dynamic color updates.

    Attributes:
        style_name: Rich style name for spinner coloring.
        spinner: Rich Spinner instance.
        is_finished: Show checkmark instead of spinner.
    """

    def __init__(self, style_name: str, spinner_name: str = "dots") -> None:
        self.style_name: str = style_name
        self.spinner: Spinner = Spinner(spinner_name, style=style_name)
        self.is_finished: bool = False
        super().__init__()

    def render(self, task: Task) -> RenderableType:
        """Render spinner or checkmark when finished."""
        if self.is_finished or task.finished:
            return Text("✓", style=self.style_name)
        self.spinner.style = self.style_name
        return self.spinner.render(task.get_time())

    def mark_finished(self) -> None:
        """Mark as finished to show checkmark."""
        self.is_finished = True


class ColoredPercentageColumn(ProgressColumn):
    """Percentage column with dynamic color.

    Attributes:
        style_name: Rich style name for percentage text.
    """

    def __init__(self, style_name: str) -> None:
        self.style_name = style_name
        super().__init__()

    def render(self, task: Task) -> Text:
        """Render percentage or empty text for indeterminate tasks."""
        style = task.fields.get(_STYLE_FIELD) or self.style_name
        if task.total is None:
            return Text("", style=style)
        percentage = min(100, int(task.percentage))
        return Text(f"| {percentage:>3d}%", style=style)


class ColoredElapsedColumn(ProgressColumn):
    """Elapsed time column with dynamic color.

    Attributes:
        style_name: Rich style name for elapsed time text.
    """

    def __init__(self, style_name: str) -> None:
        self.style_name = style_name
        super().__init__()

    def render(self, task: Task) -> Text:
        """Render elapsed time as HH:MM:SS.mmm."""
        style = task.fields.get(_STYLE_FIELD) or self.style_name
        elapsed = task.elapsed if task.elapsed else 0
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        milliseconds = int((elapsed % 1) * 1000)
        return Text(
            f"| {hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}",
            style=style,
        )


class ColoredETAColumn(ProgressColumn):
    """Estimated time remaining column with dynamic color.

    Attributes:
        style_name: Rich style name for ETA text.
    """

    def __init__(self, style_name: str) -> None:
        self.style_name = style_name
        super().__init__()

    def render(self, task: Task) -> Text:
        """Render estimated time remaining."""
        style = task.fields.get(_STYLE_FIELD) or self.style_name
        if task.total is None:
            return Text("", style=style)
        remaining = task.time_remaining
        if remaining is None:
            return Text("| 00:00:00", style=style)
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        seconds = int(remaining % 60)
        return Text(f"| {hours:02d}:{minutes:02d}:{seconds:02d}", style=style)


class ColoredBytesColumn(ProgressColumn):
    """Download progress column showing completed/total bytes.

    Attributes:
        style_name: Rich style name for byte count text.
    """

    def __init__(self, style_name: str) -> None:
        self.style_name = style_name
        super().__init__()

    def render(self, task: Task) -> Text:
        """Render completed/total byte counts."""
        style = task.fields.get(_STYLE_FIELD) or self.style_name
        completed = int(task.completed)
        total = int(task.total) if task.total else 0
        completed_str = format_bytes(completed, precision=1)
        total_str = format_bytes(total, precision=1)
        return Text(f"| {completed_str}/{total_str}", style=style)


class ColoredSpeedColumn(ProgressColumn):
    """Transfer speed column with dynamic color.

    Attributes:
        style_name: Rich style name for speed text.
    """

    def __init__(self, style_name: str) -> None:
        self.style_name = style_name
        super().__init__()

    def render(self, task: Task) -> Text:
        """Render current transfer speed."""
        style = task.fields.get(_STYLE_FIELD) or self.style_name
        speed = task.finished_speed or task.speed
        if speed is None:
            return Text("| ? MB/s", style=style)
        speed_str = format_bytes(speed, precision=1)
        return Text(f"| {speed_str}/s", style=style)


# ── Progress Bar Manager ──────────────────────────────────────────────────────


class ProgressBarManager:
    """Modular progress bar with dynamic color transitions.

    Context manager for Rich progress bars with configurable components:
    bar, percentage, spinner, bytes, speed, and time tracking.
    Color scheme updates automatically as progress advances.

    Example:
        >>> with ProgressBarManager("Task", total=100) as pb:
        ...     pb.advance(50)

        >>> with ProgressBarManager("file.zip", total=100_000_000,
        ...     show_download=True, show_speed=True) as pb:
        ...     pb.advance(10_000_000)
    """

    DEFAULT_COLORS: Final[dict[int, tuple[str, str]]] = {
        25: ("red_bold", "red_bold"),
        50: ("orange_bold", "orange_bold"),
        75: ("yellow_bold", "yellow_bold"),
        100: ("green_bold", "green_bold"),
    }
    """Default 4-step color transition from red to green."""

    def __init__(
        self,
        description: str = "Processing...",
        total: int | None = None,
        colors: dict[int, tuple[str, str]] | None = None,
        bar: str = "rich",
        custom_chars: tuple[str, str] | None = None,
        unknown_style: str = "ruby_red_bold",
        max_description_length: int = 25,
        truncate_mode: Literal["start", "middle", "end"] = "end",
        show_bar: bool = True,
        show_percentage: bool = True,
        show_spinner: bool = False,
        show_elapsed: bool = True,
        show_eta: bool = False,
        show_download: bool = False,
        show_speed: bool = True,
    ) -> None:
        """Initialize progress bar with modular component flags.

        Args:
            description: Task description text.
            total: Total units. None for indeterminate progress.
            colors: Color transitions as ``{percentage: (text_color, bar_color)}``.
            bar: Bar style — ``'rich'``, ``'blocks'``, or ``'custom'``.
            custom_chars: ``(filled_char, empty_char)`` for custom bar style.
            unknown_style: Color for indeterminate progress.
            max_description_length: Maximum description length (min 5).
            truncate_mode: Truncation mode — ``'start'``, ``'middle'``, or ``'end'``.
            show_bar: Show progress bar.
            show_percentage: Show percentage.
            show_spinner: Show spinner animation.
            show_elapsed: Show elapsed time.
            show_eta: Show time remaining.
            show_download: Show bytes column.
            show_speed: Show speed column (requires show_download).
        """
        self.description = _truncate_description(description, max_description_length, truncate_mode)
        self.total = total
        self.colors = colors or self.DEFAULT_COLORS
        self.bar_type = bar
        self.custom_chars = custom_chars
        self.unknown_style = unknown_style

        self.show_bar = show_bar
        self.show_percentage = show_percentage
        self.show_download = show_download
        self.show_speed = show_speed
        self.show_eta = show_eta
        self.show_elapsed = show_elapsed
        self.show_spinner = show_spinner

        self.current_style = self._get_initial_color()
        self.last_successful_progress = 0
        self.task: TaskID | None = None

        self.bar_width = self._calculate_bar_width()
        self.bar_style = "rich" if total is None else bar
        self._init_custom_columns()
        self._init_progress()

    def _get_initial_color(self) -> str:
        """Get initial color based on progress type."""
        if self.total is not None:
            return next(iter(self.colors.values()))[0]
        return self.unknown_style

    def _calculate_bar_width(self) -> int:
        """Calculate optimal bar width based on console width and enabled features."""
        return _fit_bar_width(self.description, show_download=self.show_download, show_eta=self.show_eta)

    def _init_custom_columns(self) -> None:
        """Initialize all custom column components."""
        self.spinner: DynamicSpinnerColumn | None = (
            DynamicSpinnerColumn(self.current_style) if self.show_spinner else None
        )

        self.percentage_col: ColoredPercentageColumn | None = (
            ColoredPercentageColumn(self.current_style) if self.show_percentage else None
        )
        self.elapsed_col: ColoredElapsedColumn | None = (
            ColoredElapsedColumn(self.current_style) if self.show_elapsed else None
        )
        self.eta_col: ColoredETAColumn | None = ColoredETAColumn(self.current_style) if self.show_eta else None

        if self.show_download:
            self.bytes_col: ColoredBytesColumn | None = ColoredBytesColumn(self.current_style)
            self.speed_col: ColoredSpeedColumn | None = (
                ColoredSpeedColumn(self.current_style) if self.show_speed else None
            )
        else:
            self.bytes_col = None
            self.speed_col = None

        self.bar_column: BarColumn | None = None

    def _init_progress(self) -> None:
        """Initialize Rich Progress instance with modular columns."""
        if self.bar_style == "rich":
            self._init_rich_progress()
        else:
            self._init_custom_progress()

    def _init_rich_progress(self) -> None:
        """Initialize Rich-style progress bar."""
        columns: list[ProgressColumn] = []

        if self.spinner:
            columns.append(self.spinner)

        columns.append(TextColumn("[progress.description]{task.description}"))

        if self.show_bar and not self.show_spinner:
            last_color = (
                list(
                    self.colors.values(),
                )[-1][1]
                if self.total
                else self.current_style
            )
            self.bar_column = BarColumn(
                bar_width=self.bar_width,
                complete_style=self.current_style,
                finished_style=last_color,
                pulse_style=self.current_style if self.total is None else "ruby_red_bold",
            )
            columns.append(self.bar_column)

        if self.bytes_col:
            columns.append(self.bytes_col)
            if self.speed_col:
                columns.append(self.speed_col)

        if self.percentage_col:
            columns.append(self.percentage_col)

        if self.eta_col:
            columns.append(self.eta_col)
        if self.elapsed_col:
            columns.append(self.elapsed_col)

        self.progress = Progress(*columns, console=console, expand=False)

    def _init_custom_progress(self) -> None:
        """Initialize custom-styled progress bar (blocks/custom chars)."""
        columns: list[ProgressColumn] = [
            TextColumn("[progress.description]{task.description}"),
            TextColumn("{task.fields[custom_bar]}", justify="left"),
        ]

        if self.bytes_col:
            columns.append(self.bytes_col)
            if self.speed_col:
                columns.append(self.speed_col)

        if self.percentage_col:
            columns.append(self.percentage_col)

        if self.eta_col:
            columns.append(self.eta_col)
        if self.elapsed_col:
            columns.append(self.elapsed_col)

        self.progress = Progress(*columns, console=console, expand=False)

    def __enter__(self) -> ProgressBarManager:
        """Start progress tracking and return self."""
        self.progress.start()

        if self.bar_style == "rich":
            self.task = self.progress.add_task(
                _style_description(self.current_style, self.description),
                total=self.total,
            )
        else:
            initial_bar = self._build_custom_bar(0)
            self.task = self.progress.add_task(
                _style_description(self.current_style, self.description),
                total=self.total,
                custom_bar=initial_bar,
            )

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Complete progress on success, preserve state on error, and stop."""
        if exc_type is None and self.total and self.task is not None:
            self.update_style(self.total)
            self.progress.update(self.task, completed=self.total)
        elif exc_type is not None:
            self.update_style(self.last_successful_progress)

        if self.spinner:
            self.spinner.mark_finished()

        self.progress.stop()

    def advance(self, amount: int = 1) -> None:
        """Advance progress by specified amount."""
        if self.task is None:
            return
        try:
            self.progress.advance(self.task, amount)
            self.last_successful_progress += amount
            self.update_style(self.last_successful_progress)
        except Exception:
            _logger.debug("Progress advance failed")
            self.progress.update(self.task, completed=self.last_successful_progress)

    def update_style(self, current: int) -> None:
        """Update colors and bar based on current progress."""
        if not self.total or self.task is None:
            return

        try:
            percentage = min(100, int((current / self.total) * 100))
            self._update_colors(percentage)

            if self.bar_style != "rich":
                self._update_custom_bar(current)
        except Exception:
            _logger.debug("Style update failed")
            self.progress.update(self.task, completed=self.last_successful_progress)

    def _update_colors(self, percentage: int) -> None:
        """Update color scheme based on percentage."""
        if self.task is None:
            return

        text_color, bar_color = _color_for_percentage(self.colors, percentage)

        if self.current_style != bar_color:
            self.current_style = bar_color

            if self.spinner:
                self.spinner.style_name = bar_color

            if self.percentage_col:
                self.percentage_col.style_name = bar_color
            if self.elapsed_col:
                self.elapsed_col.style_name = bar_color
            if self.eta_col:
                self.eta_col.style_name = bar_color
            if self.bytes_col:
                self.bytes_col.style_name = bar_color
            if self.speed_col:
                self.speed_col.style_name = bar_color

            if self.bar_column:
                self.bar_column.complete_style = bar_color
                self.bar_column.pulse_style = bar_color

            self.progress.update(
                self.task,
                description=_style_description(text_color, self.description),
            )

    def _build_custom_bar(self, current: int) -> str:
        """Build custom styled bar (blocks or custom chars)."""
        progress_ratio = current / self.total if self.total else 0

        if self.bar_type == "custom" and self.custom_chars:
            return ProgressBarBuilder.custom(
                self.bar_width,
                progress_ratio,
                self.current_style,
                _DEFAULT_EMPTY_COLOR,
                self.custom_chars[0],
                self.custom_chars[1],
            )
        return ProgressBarBuilder.blocks(
            self.bar_width,
            progress_ratio,
            self.current_style,
        )

    def _update_custom_bar(self, current: int) -> None:
        """Update custom bar visual."""
        if self.task is None:
            return
        bar = self._build_custom_bar(current)
        self.progress.update(self.task, custom_bar=bar)
