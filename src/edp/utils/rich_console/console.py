r"""Preconfigured Rich console with custom theme and auto-highlighting.

Applies the 150+ style RICH_THEME, auto-highlights URLs/paths/numbers as
``Text`` spans (content is never re-parsed as markup, so brackets and
backslashes in paths survive verbatim), and normalizes decimal commas.

Usage:
    >>> from rich_console import console
    >>> console.print("Value: 123")  # 123 is auto-colored ruby_red
    >>> console.print(r"Saved C:\out\[draft] final.ass")  # path kept 1:1
    >>> console.print("Visit https://example.com")  # URL is blue
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Final

from rich.console import Console
from rich.text import Text

from .theme import RICH_THEME

if TYPE_CHECKING:
    from typing import Any

__all__ = [
    "auto_highlight_text",
    "console",
    "normalize_numbers",
]

# ── Auto-Highlighting ─────────────────────────────────────────────────────────

_CURLY_APOSTROPHE: Final[str] = "\u2019"
"""Right single quotation mark accepted in filenames alongside a plain apostrophe."""

_PATH_SEG: Final[str] = rf"[\w.@+(),'{_CURLY_APOSTROPHE}\[\]-]+"
"""Path segment without spaces."""

_PATH_EXT: Final[str] = r"\.[A-Za-z]\w{0,31}(?![\w.\]/\\])"
"""Letter-first file extension that ends the path (not mid-token or mid-path)."""

_PATH_SPACED_NAME: Final[str] = rf"(?:(?!{_PATH_EXT})[\w.@+(),'{_CURLY_APOSTROPHE} \[\]-])*{_PATH_EXT}"
"""Filename that may contain spaces, ending at the first terminal extension."""

_PATH_SPACED_TAIL: Final[str] = rf"(?:(?!{_PATH_EXT})[\w.@+(),'{_CURLY_APOSTROPHE} \[\]/\\-])*{_PATH_EXT}"
"""Multi-segment tail with spaces in any segment, ending at the first
terminal extension."""

_PATH_RE: Final[re.Pattern[str]] = re.compile(
    rf"(?:"
    rf"[A-Za-z]:[/\\](?:{_PATH_SPACED_TAIL}|(?:{_PATH_SEG}[/\\])*{_PATH_SEG}(?<![.,])[/\\]?)"
    rf"|"
    rf"(?<!\w)/(?:"
    rf"(?:(?!{_PATH_EXT})[\w.@+(),'{_CURLY_APOSTROPHE} \[\]-])*[/\\]{_PATH_SPACED_TAIL}"
    rf"|(?:{_PATH_SEG}[/\\])+(?:{_PATH_SEG}(?<![.,]))?"
    rf")"
    rf"|"
    rf"[\w.@+-]+(?:[/\\][\w.@+-]+)*[/\\](?=\[){_PATH_SPACED_NAME}"
    rf"|"
    rf"(?!\d+/\d)[\w.@+-]+(?:/[\w.@+-]+)+\.\w{{1,32}}"
    rf"|"
    rf"[\w.@+-]+(?:[/\\][\w.@+-]+){{2,}}[/\\]"
    rf")"
)
"""Match drive/POSIX absolute paths, relative paths with a bracketed final
segment, relative file paths with an extension, or relative 3+ segment
directories ending with a separator. A strong start (drive root, POSIX root
with 2+ segments) plus a terminating extension permits spaces in every
segment; without an extension only space-free segments match, so prose
around a path is never swallowed."""

_HIGHLIGHT_STYLES: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"https?://[^\s]+"), "repr.url"),
    (_PATH_RE, "repr.path"),
    (re.compile(r"\b(?:true|True|TRUE)\b"), "repr.bool_true"),
    (re.compile(r"\b(?:false|False|FALSE)\b"), "repr.bool_false"),
    (re.compile(r"\b(?:None|null|NULL|nil)\b"), "repr.none"),
    (re.compile(r"\bv\d+(?:\.\d+)+(?:[+\-][\w.]+)*"), "repr.number"),
    (re.compile(r"\b\d+\.\d+\.\d+(?:\.\d+)*(?:[+\-][\w.]+)*"), "repr.number"),
    (
        re.compile(r"\b\d+(?:\.\d+)?\s?(?:ms|MB|GB|TB|KB|kB|px|dp|pt|em|rem|fps|Hz|kHz|min|sec|s)\b"),
        "repr.number",
    ),
    (re.compile(r"\b\d+(?:/\d+)+\b"), "repr.number"),
    (re.compile(r"\b\d+\.?\d*\b"), "repr.number"),
)
"""Priority-ordered (pattern, style) pairs: URLs, paths, booleans, none,
versions, number+unit, slash-separated number sequences, numbers. Earlier
matches claim their span."""


def auto_highlight_text(text: str) -> Text:
    """Highlight common log patterns in text as a styled ``Text``.

    Patterns colored (in priority order):

    1. URLs (``https://...``) → ``repr.url`` (blue underline)
    2. File paths (``/foo/bar``, ``dir/sub/file.ext``) → ``repr.path`` (ruby_red)
    3. Booleans (``True``/``False``) → ``repr.bool_true``/``repr.bool_false``
    4. ``None``/``null`` → ``repr.none`` (red italic)
    5. Version strings (``v2.1.0``, ``3.13.11+cu128``) → ``repr.number``
    6. Number + unit (``1.33s``, ``245MB``, ``42ms``) → ``repr.number``
    7. Slash-separated numbers (``24/24``, ``1/2/3``) → ``repr.number``
    8. Standalone numbers (``123``, ``45.67``) → ``repr.number``

    Styles are applied as spans on the raw string — content is never
    re-parsed as Rich markup — so brackets and backslashes in paths are
    preserved verbatim. Text containing real Rich markup keeps its tags and
    is highlighted only outside them.

    Args:
        text: Plain text or text with Rich markup tags.

    Returns:
        Styled ``Text`` ready for printing.
    """
    if _has_rich_markup(text):
        return _highlight_outside_rich_markup(text)
    return _highlight_plain(text)


def _highlight_plain(text: str) -> Text:
    """Stylize pattern matches as spans; earlier patterns win overlaps."""
    result = Text(text)
    claimed: list[tuple[int, int]] = []
    for pattern, style in _HIGHLIGHT_STYLES:
        for match in pattern.finditer(text):
            start, end = match.span()
            if any(start < claimed_end and claimed_start < end for claimed_start, claimed_end in claimed):
                continue
            result.stylize(style, start, end)
            claimed.append((start, end))
    return result


# ── Number Normalization ──────────────────────────────────────────────────────


def normalize_numbers(text: str) -> str:
    """Normalize decimal separator from comma to dot (1,5 → 1.5).

    Args:
        text: Text containing numbers with comma decimals.

    Returns:
        Text with dot-separated decimals.
    """
    return re.sub(r"(\d),(\d)", r"\1.\2", text)


# ── Console Instance ──────────────────────────────────────────────────────────


def _build_console() -> Console:
    """Build a Rich console honoring the cross-tool ``FORCE_COLOR`` convention."""
    force_color = os.environ.get("FORCE_COLOR", "").lower() in {"1", "true", "yes"}
    if force_color:
        return Console(
            theme=RICH_THEME,
            force_terminal=True,
            color_system="truecolor",
            legacy_windows=False,
            width=400,
        )
    return Console(theme=RICH_THEME)


console: Console = _build_console()

# ── Rich Tag Detection ────────────────────────────────────────────────────────

_RICH_TAG_PREFIXES: Final[tuple[str, ...]] = (
    "[/",
    "[bold]",
    "[italic]",
    "[underline]",
    "[dim]",
    "[blink]",
    "[reverse]",
    "[info]",
    "[success]",
    "[warning]",
    "[error]",
    "[debug]",
    "[critical]",
    "[purple]",
    "[purple_",
    "[ruby_red]",
    "[ruby_red_",
    "[pink]",
    "[pink_",
    "[red]",
    "[red_",
    "[brown]",
    "[brown_",
    "[orange]",
    "[orange_",
    "[yellow]",
    "[yellow_",
    "[green]",
    "[green_",
    "[blue]",
    "[blue_",
    "[white]",
    "[white_",
    "[normal]",
    "[normal_",
    "[gray]",
    "[gray_",
    "[black]",
    "[black_",
    "[operator]",
    "[punctuation]",
    "[special]",
    "[repr.",
    "[markdown.",
    "[log.",
    "[logging.",
    "[tree.",
    "[progress.",
)
"""Known Rich markup prefixes for tag detection.

Prevent double-highlighting and accidental literal-bracket styling.
Single source of truth for ``_has_rich_markup`` and ``_highlight_outside_rich_markup``.
"""

_GENERIC_RICH_TAG_PAIR_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\[([a-zA-Z_][a-zA-Z0-9_.-]*)\](.*?)\[/\1\]",
    re.DOTALL,
)
"""Regex matching paired Rich markup tags like ``[style]text[/style]``."""

_LEAF_RICH_TAG_PREFIXES: Final[tuple[str, ...]] = (
    "repr.",
    "json.",
    "iso8601.",
    "logging.",
    "log.",
    "progress.",
    "bar.",
    "table.",
    "markdown.",
    "prompt.",
    "inspect.",
    "scope.",
)
"""Rich style prefixes whose inner text should not be auto-highlighted again."""


def _has_rich_markup(text: str) -> bool:
    """Return True if text contains known or generic paired Rich markup tags."""
    if any(tag in text for tag in _RICH_TAG_PREFIXES):
        return True
    return _GENERIC_RICH_TAG_PAIR_PATTERN.search(text) is not None


def _highlight_outside_rich_markup(text: str) -> Text:
    """Apply auto-highlighting around and inside paired Rich markup tags."""
    result = Text()
    position = 0

    for match in _GENERIC_RICH_TAG_PAIR_PATTERN.finditer(text):
        _append_highlighted(result, text[position : match.start()])

        style = match.group(1)
        inner_text = match.group(2)
        if style.startswith(_LEAF_RICH_TAG_PREFIXES):
            result.append_text(Text.from_markup(match.group(0)))
        else:
            segment = _highlight_outside_rich_markup(inner_text)
            # Base style sits under inner spans, so nested highlights keep their colors.
            segment.style = style
            result.append_text(segment)
        position = match.end()

    _append_highlighted(result, text[position:])
    return result


def _append_highlighted(result: Text, segment: str) -> None:
    """Append a segment, markup-parsed if it still contains Rich tags."""
    if not segment:
        return
    if _has_rich_markup(segment):
        result.append_text(Text.from_markup(segment))
        return
    result.append_text(_highlight_plain(segment))


# ── Enhanced Console Print ────────────────────────────────────────────────────

_original_console_print = console.print


def _patched_console_print(*args: Any, **kwargs: Any) -> None:
    """Wrap console.print with number normalization and span-based highlighting."""
    explicit_highlight: bool | None = kwargs.get("highlight")

    processed_args: list[Any] = []
    for arg in args:
        if not isinstance(arg, str):
            processed_args.append(arg)
            continue

        text: str = normalize_numbers(arg)
        if explicit_highlight is False:
            # Wrap plain strings in Text so literal brackets are never parsed as tags.
            processed_args.append(text if _has_rich_markup(text) else Text(text))
            continue
        processed_args.append(auto_highlight_text(text))

    _original_console_print(*processed_args, **kwargs)


console.print = _patched_console_print  # type: ignore[method-assign]  # intentional monkeypatch
