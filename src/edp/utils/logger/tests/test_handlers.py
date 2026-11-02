from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

from ..config import ConsoleConfig
from ..formatters import JSONFormatter
from ..handlers import rich_handler as _rich_handler_mod
from ..handlers.json_handler import JSONHandler
from ..handlers.rich_handler import RichHandler

if TYPE_CHECKING:
    from pathlib import Path

_RICH_CONSOLE = f"{_rich_handler_mod.__name__}.console"


def _make_loguru_message(
    level: str = "INFO",
    message: str = "test msg",
    logger_name: str = "testlog",
    file_name: str = "test.py",
    function: str = "test_fn",
    line: int = 42,
    exception: object = None,
) -> Any:
    record: dict[str, Any] = {
        "level": SimpleNamespace(name=level),
        "message": message,
        "time": datetime(2024, 6, 15, 12, 0, 0),
        "extra": {"logger_name": logger_name},
        "file": SimpleNamespace(name=file_name, path=file_name),
        "function": function,
        "line": line,
        "exception": exception,
    }
    return SimpleNamespace(record=record)


class TestJSONHandler:
    def test_write_creates_file(self, tmp_path: Path) -> None:
        fp = tmp_path / "logs" / "test.log.jsonl"
        handler = JSONHandler(fp)
        handler.write(_make_loguru_message())
        assert fp.exists()

    def test_write_appends_json_line(self, tmp_path: Path) -> None:
        fp = tmp_path / "test.log.jsonl"
        handler = JSONHandler(fp)
        handler.write(_make_loguru_message(message="first"))
        handler.write(_make_loguru_message(message="second"))
        lines = fp.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        data = json.loads(lines[0])
        assert data["message"] == "first"

    def test_write_includes_level(self, tmp_path: Path) -> None:
        fp = tmp_path / "test.log.jsonl"
        handler = JSONHandler(fp)
        handler.write(_make_loguru_message(level="ERROR"))
        data = json.loads(fp.read_text(encoding="utf-8").strip())
        assert data["level"] == "ERROR"

    def test_write_includes_logger_name(self, tmp_path: Path) -> None:
        fp = tmp_path / "test.log.jsonl"
        handler = JSONHandler(fp)
        handler.write(_make_loguru_message(logger_name="myapp"))
        data = json.loads(fp.read_text(encoding="utf-8").strip())
        assert data["logger"] == "myapp"

    def test_write_with_exception(self, tmp_path: Path) -> None:
        fp = tmp_path / "test.log.jsonl"
        handler = JSONHandler(fp)
        exc = SimpleNamespace(type=ValueError, value=ValueError("bad"))
        handler.write(_make_loguru_message(exception=exc))
        data = json.loads(fp.read_text(encoding="utf-8").strip())
        assert "exception" in data
        assert "ValueError" in data["exception"]

    def test_custom_formatter(self, tmp_path: Path) -> None:
        fp = tmp_path / "test.log.jsonl"
        fmt = JSONFormatter(indent=2)
        handler = JSONHandler(fp, formatter=fmt)
        handler.write(_make_loguru_message())
        content = fp.read_text(encoding="utf-8")
        assert "\n" in content.strip()

    def test_ensure_directory(self, tmp_path: Path) -> None:
        fp = tmp_path / "deep" / "nested" / "test.log"
        JSONHandler(fp)
        assert fp.parent.exists()

    def test_write_with_file_path_in_record(self, tmp_path: Path) -> None:
        fp = tmp_path / "test.log.jsonl"
        handler = JSONHandler(fp)
        handler.write(_make_loguru_message(file_name="app.py"))
        data = json.loads(fp.read_text(encoding="utf-8").strip())
        assert data.get("location", {}).get("file") == "app.py"


class TestRichHandler:
    @patch(_RICH_CONSOLE)
    def test_write_calls_console_print(self, mock_console: MagicMock) -> None:
        handler = RichHandler()
        handler.write(_make_loguru_message())
        mock_console.print.assert_called_once()

    @patch(_RICH_CONSOLE)
    def test_write_includes_message(self, mock_console: MagicMock) -> None:
        handler = RichHandler()
        handler.write(_make_loguru_message(message="hello world"))
        output = mock_console.print.call_args[0][0]
        assert "hello world" in output

    @patch(_RICH_CONSOLE)
    def test_write_includes_level(self, mock_console: MagicMock) -> None:
        handler = RichHandler()
        handler.write(_make_loguru_message(level="ERROR"))
        output = mock_console.print.call_args[0][0]
        assert "ERROR" in output

    @patch(_RICH_CONSOLE)
    def test_write_includes_logger_name(self, mock_console: MagicMock) -> None:
        handler = RichHandler()
        handler.write(_make_loguru_message(logger_name="myapp"))
        output = mock_console.print.call_args[0][0]
        assert "myapp" in output

    @patch(_RICH_CONSOLE)
    def test_format_time_hms(self, mock_console: MagicMock) -> None:
        config = ConsoleConfig(time_format="HH:MM:SS")
        handler = RichHandler(config=config)
        handler.write(_make_loguru_message())
        output = mock_console.print.call_args[0][0]
        assert "12:00:00" in output

    @patch(_RICH_CONSOLE)
    def test_format_time_iso(self, mock_console: MagicMock) -> None:
        config = ConsoleConfig(time_format="ISO8601")
        handler = RichHandler(config=config)
        handler.write(_make_loguru_message())
        output = mock_console.print.call_args[0][0]
        assert "2024-06-15" in output

    @patch(_RICH_CONSOLE)
    def test_format_time_timestamp(self, mock_console: MagicMock) -> None:
        config = ConsoleConfig(time_format="timestamp")
        handler = RichHandler(config=config)
        handler.write(_make_loguru_message())
        mock_console.print.assert_called_once()

    @patch(_RICH_CONSOLE)
    def test_show_date(self, mock_console: MagicMock) -> None:
        config = ConsoleConfig(show_date=True, time_format="HH:MM:SS")
        handler = RichHandler(config=config)
        handler.write(_make_loguru_message())
        output = mock_console.print.call_args[0][0]
        assert "2024-06-15" in output

    @patch(_RICH_CONSOLE)
    def test_show_location(self, mock_console: MagicMock) -> None:
        config = ConsoleConfig(show_location=True)
        handler = RichHandler(config=config)
        handler.write(_make_loguru_message(file_name="app.py", line=99))
        output = mock_console.print.call_args[0][0]
        assert "app.py" in output

    @patch(_RICH_CONSOLE)
    def test_show_context(self, mock_console: MagicMock) -> None:
        config = ConsoleConfig(show_context=True)
        handler = RichHandler(config=config)
        msg = _make_loguru_message()
        msg.record["extra"]["request_id"] = 123
        handler.write(msg)
        output = mock_console.print.call_args[0][0]
        assert "request_id=123" in output

    @patch(_RICH_CONSOLE)
    def test_icons_disabled(self, mock_console: MagicMock) -> None:
        config = ConsoleConfig(show_icons=False)
        handler = RichHandler(config=config)
        handler.write(_make_loguru_message(level="INFO"))
        output = mock_console.print.call_args[0][0]
        assert "INFO" in output

    @patch(_RICH_CONSOLE)
    def test_format_time_hms_ms(self, mock_console: MagicMock) -> None:
        config = ConsoleConfig(time_format="HH:MM:SS.ms")
        handler = RichHandler(config=config)
        handler.write(_make_loguru_message())
        output = mock_console.print.call_args[0][0]
        assert "12:00:00" in output

    @patch(_RICH_CONSOLE)
    def test_format_level_includes_icon(self, mock_console: MagicMock) -> None:
        config = ConsoleConfig(show_level=True)
        handler = RichHandler(config=config)
        handler.write(_make_loguru_message(level="ERROR"))
        output = mock_console.print.call_args[0][0]
        assert "ERROR" in output

    @patch(_RICH_CONSOLE)
    def test_time_width_padding(self, mock_console: MagicMock) -> None:
        config = ConsoleConfig(time_width=20)
        handler = RichHandler(config=config)
        handler.write(_make_loguru_message())
        mock_console.print.assert_called_once()


class TestJSONHandlerClose:
    def test_close_closes_handle(self, tmp_path: Path) -> None:
        fp = tmp_path / "test.log.jsonl"
        handler = JSONHandler(fp)
        handler.write(_make_loguru_message())
        handler.close()
        assert handler._file_handle is None

    def test_close_idempotent(self, tmp_path: Path) -> None:
        fp = tmp_path / "test.log.jsonl"
        handler = JSONHandler(fp)
        handler.close()
        handler.close()

    def test_write_after_close_reopens(self, tmp_path: Path) -> None:
        fp = tmp_path / "test.log.jsonl"
        handler = JSONHandler(fp)
        handler.write(_make_loguru_message(message="first"))
        handler.close()
        handler.write(_make_loguru_message(message="second"))
        lines = fp.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
