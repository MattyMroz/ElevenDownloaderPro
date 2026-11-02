from __future__ import annotations

import json
from datetime import datetime

from ..formatters import JSONFormatter, LogRecordMeta


class TestJSONFormatter:
    def test_basic_format(self) -> None:
        fmt = JSONFormatter()
        result = fmt.format_record(
            level="INFO",
            message="hello",
            context={},
            timestamp=datetime(2024, 1, 15, 12, 0, 0),
        )
        data = json.loads(result)
        assert data["level"] == "INFO"
        assert data["message"] == "hello"
        assert data["timestamp"] == "2024-01-15T12:00:00"

    def test_with_context(self) -> None:
        fmt = JSONFormatter()
        result = fmt.format_record(
            level="ERROR",
            message="failure",
            context={"request_id": 42, "user": "test"},
            timestamp=datetime(2024, 1, 1),
        )
        data = json.loads(result)
        assert data["context"] == {"request_id": 42, "user": "test"}

    def test_empty_context_omitted(self) -> None:
        fmt = JSONFormatter()
        result = fmt.format_record(
            level="DEBUG",
            message="msg",
            context={},
            timestamp=datetime(2024, 1, 1),
        )
        data = json.loads(result)
        assert "context" not in data

    def test_with_location(self) -> None:
        fmt = JSONFormatter()
        result = fmt.format_record(
            level="INFO",
            message="test",
            context={},
            timestamp=datetime(2024, 1, 1),
            meta=LogRecordMeta(file_path="app.py", function_name="main", line_number=42),
        )
        data = json.loads(result)
        assert data["location"]["file"] == "app.py"
        assert data["location"]["function"] == "main"
        assert data["location"]["line"] == 42

    def test_location_omitted_when_empty(self) -> None:
        fmt = JSONFormatter()
        result = fmt.format_record(
            level="INFO",
            message="test",
            context={},
            timestamp=datetime(2024, 1, 1),
        )
        data = json.loads(result)
        assert "location" not in data

    def test_with_exception(self) -> None:
        fmt = JSONFormatter()
        result = fmt.format_record(
            level="ERROR",
            message="crash",
            context={},
            timestamp=datetime(2024, 1, 1),
            meta=LogRecordMeta(exception="ValueError: bad value"),
        )
        data = json.loads(result)
        assert data["exception"] == "ValueError: bad value"

    def test_exception_omitted_when_none(self) -> None:
        fmt = JSONFormatter()
        result = fmt.format_record(
            level="INFO",
            message="ok",
            context={},
            timestamp=datetime(2024, 1, 1),
        )
        data = json.loads(result)
        assert "exception" not in data

    def test_with_logger_name(self) -> None:
        fmt = JSONFormatter()
        result = fmt.format_record(
            level="INFO",
            message="test",
            context={},
            timestamp=datetime(2024, 1, 1),
            meta=LogRecordMeta(logger_name="myapp"),
        )
        data = json.loads(result)
        assert data["logger"] == "myapp"

    def test_logger_name_omitted_when_empty(self) -> None:
        fmt = JSONFormatter()
        result = fmt.format_record(
            level="INFO",
            message="test",
            context={},
            timestamp=datetime(2024, 1, 1),
        )
        data = json.loads(result)
        assert "logger" not in data

    def test_indent_option(self) -> None:
        fmt = JSONFormatter(indent=2)
        result = fmt.format_record(
            level="INFO",
            message="test",
            context={},
            timestamp=datetime(2024, 1, 1),
        )
        assert "\n" in result

    def test_compact_by_default(self) -> None:
        fmt = JSONFormatter()
        result = fmt.format_record(
            level="INFO",
            message="test",
            context={},
            timestamp=datetime(2024, 1, 1),
        )
        assert "\n" not in result

    def test_ensure_ascii(self) -> None:
        fmt = JSONFormatter(ensure_ascii=True)
        result = fmt.format_record(
            level="INFO",
            message="zażółć",
            context={},
            timestamp=datetime(2024, 1, 1),
        )
        assert "\\u" in result
