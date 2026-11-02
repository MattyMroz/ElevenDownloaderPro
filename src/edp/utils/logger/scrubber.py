"""Sensitive data scrubber for log messages.

Mask API keys, tokens, passwords, and secrets before they reach log sinks.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import PurePath, PureWindowsPath
from traceback import FrameSummary, StackSummary, TracebackException
from typing import TYPE_CHECKING, Any, Final, cast

__all__ = ["scrub_message", "scrub_patcher", "set_url_route_prefixes"]

if TYPE_CHECKING:
    from loguru import Record, RecordException, RecordFile

# ── Constants ────────────────────────────────────────────────────────────────

_ABSOLUTE_PATH_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"""(?P<quote>["'])(?P<quoted>(?:[A-Za-z]:[\\/]|\\\\|/)[^\r\n]*?)(?P=quote)"""
    r"""|(?<![\w:/\\])(?P<plain>(?:[A-Za-z]:[\\/]|\\\\|/)(?:[^\r\n/\\<>"']+[\\/])*[^\s/\\<>"']+)""",
)
"""Quoted and unquoted absolute Windows, UNC and POSIX paths."""

_SCRUB_PATTERNS: Final[list[tuple[re.Pattern[str], str]]] = [
    (re.compile(r"(api[_-]?key|apikey|secret[_-]?key|access[_-]?key)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***"),
    (re.compile(r"(Bearer\s+)\S+", re.IGNORECASE), r"\1***"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "sk-***"),
    (re.compile(r"\bAIza[A-Za-z0-9_-]{35}\b"), "AIza***"),
    (re.compile(r"(password|passwd|pwd)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***"),
    (re.compile(r"(token|auth)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***"),
    (re.compile(r"\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*[0-9])[0-9a-f]{32}\b"), "***"),
]
"""Ordered (regex, replacement) pairs applied to mask secrets in messages."""

_SENSITIVE_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:api[_-]?key|apikey|secret|token|auth|password|passwd|pwd)",
    re.IGNORECASE,
)
"""Structured-field names whose values must never reach a sink."""

_SENSITIVE_VALUE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"(?:api[_-]?key|apikey|secret[_-]?key|access[_-]?key)\s*[=:]\s*(\S+)", re.IGNORECASE),
    re.compile(r"Bearer\s+(\S+)", re.IGNORECASE),
    re.compile(r"\b(sk-[A-Za-z0-9]{20,})\b"),
    re.compile(r"\b(AIza[A-Za-z0-9_-]{35})\b"),
    re.compile(r"(?:password|passwd|pwd)\s*[=:]\s*(\S+)", re.IGNORECASE),
    re.compile(r"(?:token|auth)\s*[=:]\s*(\S+)", re.IGNORECASE),
    re.compile(r"\b((?=[0-9a-f]*[a-f])(?=[0-9a-f]*[0-9])[0-9a-f]{32})\b"),
)
"""Secret values copied by Loguru from formatting arguments into ``extra``."""

# ── Configuration ────────────────────────────────────────────────────────────
_url_route_prefixes: tuple[str, ...] = ()


def set_url_route_prefixes(prefixes: tuple[str, ...]) -> None:
    """Exempt paths starting with any of ``prefixes`` from masking.

    Args:
        prefixes: URL route prefixes such as ``("/api/",)`` that must stay readable.
    """
    global _url_route_prefixes  # noqa: PLW0603
    _url_route_prefixes = prefixes


def scrub_message(text: str) -> str:
    """Replace sensitive patterns in a log message.

    Args:
        text: Raw log message.

    Returns:
        Message with secrets masked as ``***``.
    """
    for pattern, replacement in _SCRUB_PATTERNS:
        text = pattern.sub(replacement, text)
    return _ABSOLUTE_PATH_PATTERN.sub(_path_name, text)


def _path_name(match: re.Match[str]) -> str:
    """Retain only a path's basename and its surrounding quote."""
    quote: str = match.group("quote") or ""
    path: str = match.group("quoted") or match.group("plain")
    if path.startswith(_url_route_prefixes):
        return match.group(0)
    name: str = PureWindowsPath(path).name or "<path>"
    return f"{quote}{name}{quote}"


def scrub_patcher(record: Record) -> None:
    """Scrub sensitive data from a loguru record in-place.

    Install via ``logger.configure(patcher=scrub_patcher)``.

    Args:
        record: Loguru record to sanitize.
    """
    raw_message: str = record["message"]
    sensitive_values: frozenset[str] = _sensitive_values(raw_message)
    record["message"] = scrub_message(raw_message)
    source_file: RecordFile | None = record.get("file")
    if source_file is not None:
        source_file.path = source_file.name
    extra = record.get("extra")
    if isinstance(extra, Mapping):
        # Mapping input to _scrub_value always yields a dict via the Mapping branch.
        record["extra"] = cast("dict[Any, Any]", _scrub_value(extra, sensitive_values=sensitive_values))
    exception = record.get("exception")
    if exception is None:
        return
    record.setdefault("extra", {})["_safe_traceback"] = _safe_traceback(exception)
    original: str = str(exception.value)
    scrubbed: str = scrub_message(original)
    if scrubbed == original:
        return
    sanitized_value = RuntimeError(scrubbed)
    record["exception"] = type(exception)(
        exception.type,
        sanitized_value,
        exception.traceback,
    )


def _safe_traceback(exception: RecordException) -> str:
    """Preserve exception diagnostics without paths, source code or locals."""
    error: BaseException = exception.value if exception.value is not None else RuntimeError("Exception unavailable")
    summary: TracebackException = TracebackException(
        exception.type or type(error),
        error,
        exception.traceback,
        lookup_lines=False,
        capture_locals=False,
    )
    pending: list[TracebackException] = [summary]
    while pending:
        current: TracebackException = pending.pop()
        current.stack = StackSummary.from_list(
            [
                FrameSummary(PureWindowsPath(frame.filename).name, frame.lineno, frame.name, lookup_line=False, line="")
                for frame in current.stack
            ],
        )
        if hasattr(current, "filename"):
            current.filename = PureWindowsPath(current.filename or "").name
            current.text = ""
        pending.extend(item for item in (current.__cause__, current.__context__) if item is not None)
        pending.extend(current.exceptions or ())
    return scrub_message("".join(summary.format())).rstrip()


def _scrub_value(
    value: object,
    *,
    key: str = "",
    sensitive_values: frozenset[str] = frozenset(),
) -> object:
    """Return a recursively scrubbed structured log value."""
    if key and _SENSITIVE_KEY_PATTERN.search(key) is not None:
        return "***"
    if isinstance(value, str | PurePath):
        return _scrub_text(value, sensitive_values=sensitive_values)
    if isinstance(value, Mapping):
        return {
            _scrub_text(item_key, sensitive_values=sensitive_values): _scrub_value(
                item_value,
                key=str(item_key),
                sensitive_values=sensitive_values,
            )
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_scrub_value(item, sensitive_values=sensitive_values) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub_value(item, sensitive_values=sensitive_values) for item in value)
    if isinstance(value, set):
        return {_scrub_value(item, sensitive_values=sensitive_values) for item in value}
    return value


def _scrub_text(value: object, *, sensitive_values: frozenset[str] = frozenset()) -> str:
    """Sanitize text and retain only the name of rooted path objects."""
    text: str = str(value)
    if text in sensitive_values:
        return "***"
    if isinstance(value, PurePath) and value.root:
        text = value.name
    return scrub_message(text)


def _sensitive_values(text: str) -> frozenset[str]:
    """Extract values masked by message scrubbing for structured-field reuse."""
    return frozenset(match.group(1) for pattern in _SENSITIVE_VALUE_PATTERNS for match in pattern.finditer(text))
