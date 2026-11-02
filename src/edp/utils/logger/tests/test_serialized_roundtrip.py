from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Any

import pytest
from loguru import logger
from rich.console import Console

from ...rich_console.theme import RICH_THEME
from .. import get_logger, log_viewer
from ..cli import apply_filters, main
from ..config import LoggerMode
from ..core import InterceptHandler, setup_mode, shutdown_logger
from ..log_reader import LogReader
from ..readers import LogAggregator
from ..readers import LogReader as FluentLogReader

if TYPE_CHECKING:
    from loguru import Logger, Record


def _emit_at(log: Logger, timestamp: datetime, level: str, message: str) -> None:
    def stamp(record: Record) -> None:
        record["time"] = timestamp

    log.patch(stamp).log(level, message)


@pytest.fixture
def serialized_log(tmp_path: Path) -> Path:
    path: Path = tmp_path / "application.jsonl"
    now: datetime = datetime.now(UTC)
    setup_mode(LoggerMode.PRODUCTION, console_enabled=False, file_path=path)
    try:
        log: Logger = get_logger("roundtrip").bind(api_key="private-key-sentinel", episode="public-sentinel")
        _emit_at(log, now - timedelta(hours=2), "ERROR", "old-error-sentinel")
        _emit_at(log, now - timedelta(minutes=5), "ERROR", "recent-error-sentinel token=private-token-sentinel")
        _emit_at(log, now - timedelta(minutes=5), "INFO", "recent-info-sentinel")
        _emit_at(log, now + timedelta(hours=2), "ERROR", "future-error-sentinel")
    finally:
        shutdown_logger()
    return path


def test_both_readers_interpret_production_records_identically(serialized_log: Path) -> None:
    reader: LogReader = LogReader(serialized_log)
    logs: list[dict[str, Any]] = reader.read_all()
    fluent: FluentLogReader = FluentLogReader(serialized_log).load()

    assert logs == fluent.to_list()
    assert reader.get_stats() == {
        "total": 4,
        "by_level": {"ERROR": 3, "INFO": 1},
        "by_logger": {"roundtrip": 4},
    }
    assert LogAggregator(logs).count_by_level() == {"ERROR": 3, "INFO": 1}
    assert len(reader.filter_by_level("ERROR")) == 3
    assert [entry["message"] for entry in fluent.filter_by_level("ERROR").filter_by_time(hours=1).to_list()] == [
        "recent-error-sentinel token=***"
    ]
    assert all(entry["api_key"] == "***" and entry["episode"] == "public-sentinel" for entry in logs)


@pytest.mark.parametrize("window", [{"minutes": 30}, {"hours": 1}])
def test_cli_composes_time_and_level_filters(serialized_log: Path, window: dict[str, int]) -> None:
    logs: list[dict[str, Any]] = apply_filters(LogReader(serialized_log), {"level": "ERROR", **window})

    assert [entry["message"] for entry in logs] == ["recent-error-sentinel token=***"]


def test_cli_displays_only_matching_production_records(
    serialized_log: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream: StringIO = StringIO()
    console: Console = Console(file=stream, theme=RICH_THEME, width=140, color_system=None)
    monkeypatch.setattr(log_viewer, "console", console)
    monkeypatch.setattr(sys, "argv", ["log-viewer", str(serialized_log), "--level", "ERROR", "--hours", "1"])

    main()

    output: str = stream.getvalue()
    assert "recent-error-sentinel token=***" in output
    assert "ERROR" in output
    assert "roundtrip" in output
    assert all(value not in output for value in ("old-error", "future-error", "recent-info", "private-"))


def test_production_json_keeps_source_names_without_absolute_paths(serialized_log: Path) -> None:
    payload: str = serialized_log.read_text(encoding="utf-8")
    records: list[dict[str, Any]] = [json.loads(line)["record"] for line in payload.splitlines()]

    assert "private-key-sentinel" not in payload
    assert "private-token-sentinel" not in payload
    assert "public-sentinel" in payload
    for record in records:
        source: dict[str, str] = record["file"]
        assert source["path"] == source["name"] == Path(__file__).name
        assert not Path(source["path"]).is_absolute()
        assert not PureWindowsPath(source["path"]).is_absolute()


def test_source_metadata_still_formats_in_a_plain_sink(tmp_path: Path) -> None:
    stream: StringIO = StringIO()
    setup_mode(LoggerMode.PRODUCTION, console_enabled=False, file_path=tmp_path / "application.jsonl")
    try:
        logger.add(stream, format="{file.name}|{file.path}|{line}|{message}", catch=False)
        get_logger("roundtrip").warning("plain-sink-sentinel")
    finally:
        shutdown_logger()

    output: str = stream.getvalue()
    assert output.count(Path(__file__).name) == 2
    assert str(Path(__file__).parent) not in output
    assert "plain-sink-sentinel" in output


@pytest.mark.parametrize(
    "source_path",
    [
        Path("/private-directory-sentinel/file.txt"),
        PurePosixPath("/private-directory-sentinel/file.txt"),
        PureWindowsPath("C:/private-directory-sentinel/file.txt"),
    ],
)
def test_serialized_paths_are_redacted_in_structured_values_and_keys(tmp_path: Path, source_path: PurePath) -> None:
    path: Path = tmp_path / "application.jsonl"
    setup_mode(LoggerMode.PRODUCTION, console_enabled=False, file_path=path)
    try:
        get_logger("roundtrip").error(
            "path-object-proof",
            source_path=source_path,
            nested={"items": [source_path], source_path: "preserved-value"},
        )
    finally:
        shutdown_logger()

    for log_path in (path, path.parent / "errors.log.jsonl"):
        payload: str = log_path.read_text(encoding="utf-8")
        extra: dict[str, Any] = json.loads(payload)["record"]["extra"]
        assert "private-directory-sentinel" not in payload
        assert extra["source_path"] == "file.txt"
        assert extra["nested"] == {"items": ["file.txt"], "file.txt": "preserved-value"}


def test_serialized_mapping_keys_mask_known_secret_values(tmp_path: Path) -> None:
    path: Path = tmp_path / "application.jsonl"
    secret: str = "sensitive-value-sentinel"  # noqa: S105
    setup_mode(LoggerMode.PRODUCTION, console_enabled=False, file_path=path)
    try:
        get_logger("roundtrip").error(
            "token={credential}",
            credential=secret,
            nested={secret: "preserved-value"},
            copied=PurePosixPath(secret),
        )
    finally:
        shutdown_logger()

    for log_path in (path, path.parent / "errors.log.jsonl"):
        payload: str = log_path.read_text(encoding="utf-8")
        extra: dict[str, Any] = json.loads(payload)["record"]["extra"]
        assert secret not in payload
        assert extra["credential"] == extra["copied"] == "***"
        assert extra["nested"] == {"***": "preserved-value"}


def test_stdlib_custom_numeric_level_reaches_serialized_sink(tmp_path: Path) -> None:
    path: Path = tmp_path / "custom-level.jsonl"
    setup_mode(LoggerMode.PRODUCTION, console_enabled=False, file_path=path)
    record: logging.LogRecord = logging.LogRecord("vendor", 35, __file__, 1, "custom-level-sentinel", (), None)
    try:
        InterceptHandler().emit(record)
    finally:
        shutdown_logger()

    emitted: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))["record"]
    assert emitted["level"]["no"] == 35
    assert emitted["message"] == "custom-level-sentinel"


def test_serialized_exceptions_keep_safe_stack_details_without_source_paths(tmp_path: Path) -> None:
    path: Path = tmp_path / "application.jsonl"
    setup_mode(LoggerMode.PRODUCTION, console_enabled=False, file_path=path)

    def raise_private_error() -> None:
        message: str = "api_key=exception-private-sentinel {literal} <tag>"
        raise RuntimeError(message)

    try:
        raise_private_error()
    except RuntimeError:
        get_logger("roundtrip").exception("exception-proof-sentinel")
    finally:
        shutdown_logger()

    for log_path in (path, path.parent / "errors.log.jsonl"):
        payload: str = log_path.read_text(encoding="utf-8")
        emitted: dict[str, Any] = json.loads(payload)
        text: str = emitted["text"]
        assert "exception-private-sentinel" not in payload
        assert str(Path(__file__).resolve().parent) not in text
        assert Path(__file__).name in text
        assert "raise_private_error" in text
        assert "RuntimeError: api_key=*** {literal} <tag>" in text
        assert emitted["record"]["exception"]["type"] == "RuntimeError"


def test_serialized_exceptions_preserve_redacted_causes(tmp_path: Path) -> None:
    path: Path = tmp_path / "application.jsonl"
    setup_mode(LoggerMode.PRODUCTION, console_enabled=False, file_path=path)

    def fail_operation() -> None:
        try:
            message: str = "token=private-cause-sentinel"
            raise ValueError(message)
        except ValueError as cause:
            message = "operation-failure-sentinel"
            raise RuntimeError(message) from cause

    try:
        fail_operation()
    except RuntimeError:
        get_logger("roundtrip").exception("failure-with-cause")
    finally:
        shutdown_logger()

    payload: str = path.read_text(encoding="utf-8")
    text: str = json.loads(payload)["text"]
    assert "private-cause-sentinel" not in payload
    assert "ValueError: token=***" in text
    assert "RuntimeError: operation-failure-sentinel" in text
    assert "direct cause" in text
    assert str(Path(__file__).resolve().parent) not in text


@pytest.mark.parametrize(
    "private_path",
    [
        "C:/private-directory-sentinel/file-sentinel.txt",
        r"C:\private-directory-sentinel\file-sentinel.txt",
        "/private-directory-sentinel/file-sentinel.txt",
        r"\\private-server-sentinel\private-directory-sentinel\file-sentinel.txt",
        "C:/private-directory-sentinel with spaces/file-sentinel.txt",
        "/private-directory-sentinel with spaces/file-sentinel.txt",
    ],
)
def test_real_exception_sinks_scrub_paths_notes_and_causes(tmp_path: Path, private_path: str) -> None:
    path: Path = tmp_path / "application.jsonl"
    note: str = f"Inspect {private_path.replace('file-sentinel', 'note-sentinel')}"
    error: FileNotFoundError = FileNotFoundError(2, "file missing", private_path)
    error.add_note(note)
    error.__cause__ = ValueError(f"Cause at {private_path.replace('file-sentinel', 'cause-sentinel')!r}")
    setup_mode(LoggerMode.PRODUCTION, console_enabled=False, file_path=path)
    try:
        raise error
    except FileNotFoundError:
        get_logger("roundtrip").exception("safe-operation-label")
    finally:
        shutdown_logger()

    for log_path in (path, path.parent / "errors.log.jsonl"):
        payload: str = log_path.read_text(encoding="utf-8")
        emitted: dict[str, Any] = json.loads(payload)
        text: str = emitted["text"]
        assert "private-directory-sentinel" not in payload
        assert "private-server-sentinel" not in payload
        assert "FileNotFoundError: [Errno 2] file missing: 'file-sentinel.txt'" in text
        assert "note-sentinel.txt" in text
        assert "cause-sentinel.txt" in text
        assert "ValueError:" in text
        assert "direct cause" in text
        assert emitted["record"]["exception"]["type"] == "FileNotFoundError"
        assert emitted["record"]["exception"]["value"] == "[Errno 2] file missing: 'file-sentinel.txt'"
    assert error.filename == private_path
    assert error.__notes__ == [note]


@pytest.mark.parametrize("container", ["direct", "cause", "group"])
def test_syntax_exception_sinks_omit_source_text_and_paths(tmp_path: Path, container: str) -> None:
    path: Path = tmp_path / "application.jsonl"
    setup_mode(LoggerMode.PRODUCTION, console_enabled=False, file_path=path)
    try:
        compile("private_source_sentinel = $\n", "C:/private-directory-sentinel/syntax-sentinel.py", "exec")
    except SyntaxError as error:
        logged: Exception = error
        if container == "cause":
            logged = RuntimeError("outer failure")
            logged.__cause__ = error
        elif container == "group":
            logged = ExceptionGroup("group failure", [error])
        get_logger("roundtrip").opt(exception=logged).error("syntax-operation-label")
    finally:
        shutdown_logger()

    for log_path in (path, path.parent / "errors.log.jsonl"):
        payload: str = log_path.read_text(encoding="utf-8")
        text: str = json.loads(payload)["text"]
        assert "private-directory-sentinel" not in payload
        assert "private_source_sentinel" not in payload
        assert "syntax-sentinel.py" in text
        assert "SyntaxError: invalid syntax" in text
