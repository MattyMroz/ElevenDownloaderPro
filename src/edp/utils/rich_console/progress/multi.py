"""Multi-task progress display — per-task-customizable twin of the single bar.

Renders N progress rows at once inside a single ``rich.Progress`` live
display. Every row is a faithful multiplication of
:class:`~.manager.ProgressBarManager`: the same block-style bar, the same
dynamic color transitions and the same seven modular column flags — but
resolved per task. The constructor sets the defaults every new task
inherits; ``add_task`` overrides any of them for one specific row, so a
download row with bytes and speed can animate next to a percent-only row.

Two alignment modes control the layout. ``'aligned'`` (default) renders all
rows in one shared table: bars share one width and the value columns line
up vertically even when rows enable different columns. ``'independent'``
renders every row as one self-contained line: the bar is sized from the
row's own flags and its value columns sit immediately after its own bar,
so nothing aligns across rows and no space is reserved for columns other
rows have.

Per-row state travels in ``task.fields``: the current style (same
``_STYLE_FIELD`` mechanism the single bar uses), the pre-rendered block bar,
and one visibility flag per optional column. All mutating methods are
thread-safe — parallel workers update different tasks without an external
lock.

Usage:
    >>> with MultiProgressManager() as mp:
    ...     episode = mp.add_task("episode 1.mkv")
    ...     archive = mp.add_task("tools.zip", total=8_000_000, show_download=True)
    ...     mp.update(episode, 40)
    ...     mp.advance(archive, 250_000)
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Literal, Protocol

from rich.progress import Progress, ProgressColumn, TaskID, TextColumn
from rich.text import Text

from ..console import console
from .manager import (
    _STYLE_FIELD,
    ColoredBytesColumn,
    ColoredElapsedColumn,
    ColoredETAColumn,
    ColoredPercentageColumn,
    ColoredSpeedColumn,
    DynamicSpinnerColumn,
    ProgressBarBuilder,
    ProgressBarManager,
    _color_for_percentage,
    _fit_bar_width,
    _style_description,
    _truncate_description,
)

if TYPE_CHECKING:
    from types import TracebackType

    from rich.console import RenderableType
    from rich.progress import Task

__all__ = ["MultiProgressManager"]

# ── Constants ─────────────────────────────────────────────────────────────────

_BAR_FIELD: Final[str] = "custom_bar"
"""Per-task field carrying the pre-rendered block-bar markup."""

_SHOW_SPINNER_FIELD: Final[str] = "show_spinner"
"""Per-task field toggling the spinner column for one row."""

_SHOW_BYTES_FIELD: Final[str] = "show_bytes"
"""Per-task field toggling the bytes column for one row."""

_SHOW_SPEED_FIELD: Final[str] = "show_speed"
"""Per-task field toggling the speed column for one row."""

_SHOW_PERCENTAGE_FIELD: Final[str] = "show_percentage"
"""Per-task field toggling the percentage column for one row."""

_SHOW_ETA_FIELD: Final[str] = "show_eta"
"""Per-task field toggling the ETA column for one row."""

_SHOW_ELAPSED_FIELD: Final[str] = "show_elapsed"
"""Per-task field toggling the elapsed-time column for one row."""

# ── Per-Task Column Wrapper ───────────────────────────────────────────────────


class _StyledColumn(Protocol):
    """Column contract for :class:`_PerTaskColumn`: settable style + render."""

    style_name: str

    def render(self, task: Task) -> RenderableType:
        """Render the column cell for one task."""
        ...


class _PerTaskColumn(ProgressColumn):
    """Render a wrapped single-bar column only for tasks that enabled it.

    The shared ``rich.Progress`` table has one fixed column list, so per-task
    visibility is driven through ``task.fields``: rows that disabled the
    column render an empty cell. The task's current style (``_STYLE_FIELD``)
    is pushed onto the wrapped column before rendering, mirroring how the
    single bar drives per-task colors.
    """

    def __init__(self, inner: _StyledColumn, visible_field: str) -> None:
        self._inner = inner
        self._visible_field = visible_field
        super().__init__()

    def render(self, task: Task) -> RenderableType:
        """Render the wrapped column, or an empty cell when the row hides it."""
        if not task.fields.get(self._visible_field):
            return Text("")
        style = task.fields.get(_STYLE_FIELD)
        if style:
            self._inner.style_name = style
        return self._inner.render(task)


class _IndependentRowColumn(ProgressColumn):
    """Render one task as a single fully self-contained row.

    The only column of the ``'independent'`` mode: spinner, description,
    bar and every enabled value cell concatenate into one ``Text``, each
    separated by a single space. Because the whole row is one table cell,
    no value column aligns with any other row — a row's values sit right
    after its own bar and rows with fewer columns are simply shorter.
    """

    def __init__(self, style_name: str) -> None:
        self._spinner = _PerTaskColumn(DynamicSpinnerColumn(style_name), _SHOW_SPINNER_FIELD)
        self._values: tuple[_PerTaskColumn, ...] = (
            _PerTaskColumn(ColoredBytesColumn(style_name), _SHOW_BYTES_FIELD),
            _PerTaskColumn(ColoredSpeedColumn(style_name), _SHOW_SPEED_FIELD),
            _PerTaskColumn(ColoredPercentageColumn(style_name), _SHOW_PERCENTAGE_FIELD),
            _PerTaskColumn(ColoredETAColumn(style_name), _SHOW_ETA_FIELD),
            _PerTaskColumn(ColoredElapsedColumn(style_name), _SHOW_ELAPSED_FIELD),
        )
        super().__init__()

    def render(self, task: Task) -> Text:
        """Concatenate the task's enabled cells into one row."""
        row = Text()
        spinner_cell = self._spinner.render(task)
        if isinstance(spinner_cell, Text) and spinner_cell.plain:
            row.append(spinner_cell)
            row.append(" ")
        row.append(Text.from_markup(task.description))
        bar_markup = task.fields.get(_BAR_FIELD, "")
        if bar_markup:
            row.append(" ")
            row.append(Text.from_markup(bar_markup))
        for column in self._values:
            cell = column.render(task)
            if isinstance(cell, Text) and cell.plain:
                row.append(" ")
                row.append(cell)
        return row


# ── Task State ────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class _TaskState:
    """Mutable per-task bookkeeping.

    Attributes:
        description: Truncated task label (without color markup).
        total: Total units of the task.
        completed: Units completed so far.
        style: Current bar color of the task's row.
        colors: Color transitions of this task.
        bar_width: Block-bar width of this task's row.
        show_bar: Whether this task renders a block bar.
    """

    description: str
    total: int
    completed: int
    style: str
    colors: dict[int, tuple[str, str]]
    bar_width: int
    show_bar: bool


# ── Multi Progress Manager ────────────────────────────────────────────────────


class MultiProgressManager:
    """Thread-safe multi-row progress display with per-task customization.

    The multi-task twin of :class:`ProgressBarManager`: same block-style
    bars, same dynamic color transitions, same seven modular flags. The
    constructor supplies the defaults every task inherits; :meth:`add_task`
    overrides any of them for one row, so tasks mix freely — one row with
    bytes and speed, another percent-only, another spinner-only, each with
    its own color scheme. In the default ``'aligned'`` mode all rows render
    in one shared table: every bar shares one width (set by the most
    demanding row) and the value columns line up vertically. In
    ``'independent'`` mode every row renders as one self-contained line:
    the bar is sized from the row's own flags and its values sit right
    after its own bar, without aligning to any other row. All mutating
    methods take an internal lock, so parallel workers update different
    tasks without external locking.

    Example:
        >>> with MultiProgressManager() as mp:
        ...     episode = mp.add_task("episode 1.mkv")
        ...     archive = mp.add_task("tools.zip", total=8_000_000, show_download=True)
        ...     mp.update(episode, 100)
        ...     mp.advance(archive, 8_000_000)
    """

    def __init__(
        self,
        *,
        align: Literal["aligned", "independent"] = "aligned",
        colors: dict[int, tuple[str, str]] | None = None,
        max_description_length: int = 25,
        truncate_mode: Literal["start", "middle", "end"] = "end",
        show_bar: bool = True,
        show_percentage: bool = True,
        show_spinner: bool = False,
        show_elapsed: bool = True,
        show_eta: bool = False,
        show_download: bool = False,
        show_speed: bool = True,
        transient: bool = False,
    ) -> None:
        """Initialize the display defaults without starting the live render.

        Every argument is the default a new task inherits; :meth:`add_task`
        can override any per-task option for one specific row.

        Args:
            align: Layout mode — ``'aligned'`` renders all rows in one shared
                table (one bar width, value columns line up vertically);
                ``'independent'`` renders each row self-contained, with its
                values glued right after its own bar.
            colors: Color transitions as ``{percentage: (text_color, bar_color)}``;
                defaults to ``ProgressBarManager.DEFAULT_COLORS``.
            max_description_length: Maximum description length (min 5).
            truncate_mode: Truncation mode — ``'start'``, ``'middle'``, or ``'end'``.
            show_bar: Show the block bar (hidden while the spinner is shown).
            show_percentage: Show percentage.
            show_spinner: Show spinner animation (checkmark when finished).
            show_elapsed: Show elapsed time.
            show_eta: Show time remaining.
            show_download: Show bytes column.
            show_speed: Show speed column (requires show_download).
            transient: Remove all rows when the display stops, leaving no
                trace in the scrollback (use for a phase whose bars a later
                phase replaces in place).
        """
        self._align = align
        self._shared_bar_width: int | None = None
        self._colors = colors or ProgressBarManager.DEFAULT_COLORS
        self._max_description_length = max(5, max_description_length)
        self._truncate_mode = truncate_mode
        self._show_bar = show_bar
        self._show_percentage = show_percentage
        self._show_spinner = show_spinner
        self._show_elapsed = show_elapsed
        self._show_eta = show_eta
        self._show_download = show_download
        self._show_speed = show_speed
        self._lock = threading.Lock()
        self._states: dict[TaskID, _TaskState] = {}
        initial_style = next(iter(self._colors.values()))[0]
        if align == "aligned":
            columns = self._aligned_columns(initial_style)
        else:
            columns = (_IndependentRowColumn(initial_style),)
        self._progress = Progress(*columns, console=console, expand=False, transient=transient)

    def __enter__(self) -> MultiProgressManager:
        """Start the live display and return self."""
        self._progress.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Stop the live display, leaving every task at its last state."""
        self._progress.stop()

    def add_task(
        self,
        description: str,
        *,
        total: int = 100,
        colors: dict[int, tuple[str, str]] | None = None,
        show_bar: bool | None = None,
        show_percentage: bool | None = None,
        show_spinner: bool | None = None,
        show_elapsed: bool | None = None,
        show_eta: bool | None = None,
        show_download: bool | None = None,
        show_speed: bool | None = None,
    ) -> TaskID:
        """Add one row and return its id.

        Every ``None`` override keeps the constructor default for that
        option, so a bare ``add_task("name")`` inherits the manager's
        configuration completely.

        Args:
            description: Row label; truncated per the manager's truncate settings.
            total: Total units; pass byte counts to drive the bytes and speed
                columns with real download figures.
            colors: Row-specific color transitions ``{percentage: (text, bar)}``.
            show_bar: Show the block bar (hidden while the spinner is shown).
            show_percentage: Show percentage.
            show_spinner: Show spinner animation (checkmark when finished).
            show_elapsed: Show elapsed time.
            show_eta: Show time remaining.
            show_download: Show bytes column.
            show_speed: Show speed column (requires show_download).

        Returns:
            The task id accepted by :meth:`advance` and :meth:`update`.
        """
        task_colors = colors or self._colors
        bar_flag = self._pick(show_bar, self._show_bar)
        spinner_flag = self._pick(show_spinner, self._show_spinner)
        download_flag = self._pick(show_download, self._show_download)
        speed_flag = download_flag and self._pick(show_speed, self._show_speed)
        eta_flag = self._pick(show_eta, self._show_eta)
        bar_visible = bar_flag and not spinner_flag
        with self._lock:
            label = _truncate_description(description, self._max_description_length, self._truncate_mode)
            text_color, bar_color = _color_for_percentage(task_colors, 0)
            bar_width = _fit_bar_width(label, show_download=download_flag, show_eta=eta_flag)
            if self._align == "aligned":
                bar_width = self._share_width(bar_width)
            fields: dict[str, Any] = {
                _STYLE_FIELD: bar_color,
                _BAR_FIELD: ProgressBarBuilder.blocks(bar_width, 0.0, bar_color) if bar_visible else "",
                _SHOW_SPINNER_FIELD: spinner_flag,
                _SHOW_BYTES_FIELD: download_flag,
                _SHOW_SPEED_FIELD: speed_flag,
                _SHOW_PERCENTAGE_FIELD: self._pick(show_percentage, self._show_percentage),
                _SHOW_ETA_FIELD: eta_flag,
                _SHOW_ELAPSED_FIELD: self._pick(show_elapsed, self._show_elapsed),
            }
            task_id = self._progress.add_task(_style_description(text_color, label), total=total, **fields)
            self._states[task_id] = _TaskState(label, total, 0, bar_color, task_colors, bar_width, bar_visible)
            return task_id

    def advance(self, task_id: TaskID, amount: int = 1) -> None:
        """Advance one task by *amount* units.

        Args:
            task_id: Task returned by :meth:`add_task`.
            amount: Units to add to the task's completed count.
        """
        with self._lock:
            state = self._states[task_id]
            self._apply(task_id, state, state.completed + amount)

    def update(self, task_id: TaskID, completed: int) -> None:
        """Set one task's absolute completed count.

        Args:
            task_id: Task returned by :meth:`add_task`.
            completed: Absolute completed units (clamped to the task total).
        """
        with self._lock:
            self._apply(task_id, self._states[task_id], completed)

    def update_description(self, task_id: TaskID, description: str) -> None:
        """Replace one task's label without changing its position or progress."""
        with self._lock:
            state = self._states[task_id]
            label = _truncate_description(description, self._max_description_length, self._truncate_mode)
            state.description = label
            percentage = min(100, int((state.completed / state.total) * 100)) if state.total else 0
            text_color, _bar_color = _color_for_percentage(state.colors, percentage)
            self._progress.update(task_id, description=_style_description(text_color, label))

    def set_task_presentation(
        self,
        task_id: TaskID,
        *,
        show_bar: bool,
        show_percentage: bool,
        show_spinner: bool,
    ) -> None:
        """Change the visual mode of an existing row without replacing it."""
        with self._lock:
            state = self._states[task_id]
            bar_visible: bool = show_bar and not show_spinner
            state.show_bar = bar_visible
            percentage: float = state.completed / state.total if state.total else 0.0
            fields: dict[str, Any] = {
                _SHOW_SPINNER_FIELD: show_spinner,
                _SHOW_PERCENTAGE_FIELD: show_percentage,
                _BAR_FIELD: (
                    ProgressBarBuilder.blocks(
                        state.bar_width,
                        percentage,
                        state.style,
                    )
                    if bar_visible
                    else ""
                ),
            }
            self._progress.update(task_id, **fields)

    def stop_task(self, task_id: TaskID) -> None:
        """Freeze one task's elapsed time without changing its completion."""
        with self._lock:
            self._progress.stop_task(task_id)

    def reset_task(self, task_id: TaskID, *, completed: int = 0) -> None:
        """Restart one task's timer and set its completion without moving its row."""
        with self._lock:
            state = self._states[task_id]
            self._progress.reset(task_id, total=state.total, completed=0, start=True)
            self._progress.tasks[task_id].stop_time = None
            self._apply(task_id, state, completed)

    @staticmethod
    def _aligned_columns(style: str) -> tuple[ProgressColumn, ...]:
        """Build the shared table columns for the ``'aligned'`` mode."""
        return (
            _PerTaskColumn(DynamicSpinnerColumn(style), _SHOW_SPINNER_FIELD),
            TextColumn("{task.description}"),
            TextColumn(f"{{task.fields[{_BAR_FIELD}]}}", justify="left"),
            _PerTaskColumn(ColoredBytesColumn(style), _SHOW_BYTES_FIELD),
            _PerTaskColumn(ColoredSpeedColumn(style), _SHOW_SPEED_FIELD),
            _PerTaskColumn(ColoredPercentageColumn(style), _SHOW_PERCENTAGE_FIELD),
            _PerTaskColumn(ColoredETAColumn(style), _SHOW_ETA_FIELD),
            _PerTaskColumn(ColoredElapsedColumn(style), _SHOW_ELAPSED_FIELD),
        )

    @staticmethod
    def _pick(override: bool | None, default: bool) -> bool:
        """Return the per-task override when given, else the manager default."""
        return default if override is None else override

    def _share_width(self, fitted: int) -> int:
        """Fold one row's fitted width into the shared bar width.

        The most demanding row wins: the shared width is the minimum of all
        fitted widths seen so far. When a new row shrinks it, every existing
        bar is re-rendered at the new width so all rows stay equal.
        """
        shared = fitted if self._shared_bar_width is None else min(self._shared_bar_width, fitted)
        if shared == self._shared_bar_width:
            return shared
        self._shared_bar_width = shared
        for task_id, state in self._states.items():
            state.bar_width = shared
            if state.show_bar:
                ratio = state.completed / state.total if state.total else 0.0
                fields: dict[str, Any] = {_BAR_FIELD: ProgressBarBuilder.blocks(shared, ratio, state.style)}
                self._progress.update(task_id, **fields)
        return shared

    def _apply(self, task_id: TaskID, state: _TaskState, completed: int) -> None:
        """Write one task's new completed count, restyling its row when needed."""
        state.completed = max(0, min(state.total, completed))
        percentage = min(100, int((state.completed / state.total) * 100)) if state.total else 0
        text_color, bar_color = _color_for_percentage(state.colors, percentage)
        fields: dict[str, Any] = {}
        if state.show_bar:
            ratio = state.completed / state.total if state.total else 0.0
            fields[_BAR_FIELD] = ProgressBarBuilder.blocks(state.bar_width, ratio, bar_color)
        if bar_color != state.style:
            state.style = bar_color
            fields[_STYLE_FIELD] = bar_color
            description = _style_description(text_color, state.description)
            self._progress.update(task_id, completed=state.completed, description=description, **fields)
        else:
            self._progress.update(task_id, completed=state.completed, **fields)
        if state.total > 0 and state.completed >= state.total:
            self._progress.stop_task(task_id)
