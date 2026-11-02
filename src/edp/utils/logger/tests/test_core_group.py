from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest
from loguru import logger
from pydantic import ValidationError

from .. import config as _config_mod
from .. import core as _core_mod
from .. import modes as _modes_mod
from ..config import (
    ConsoleConfig,
    FileConfig,
    LoggerConfig,
    LoggerMode,
    PresetConfig,
    get_level_priority,
)
from ..core import (
    InterceptHandler,
    setup_mode,
    setup_mode_from_env,
    shutdown_logger,
)
from ..modes import get_mode_config

_CORE_SETUP_MODE = f"{_core_mod.__name__}.setup_mode"


class TestLoggerMode:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            pytest.param("DEV", LoggerMode.DEV, id="dev"),
            pytest.param("PRODUCTION", LoggerMode.PRODUCTION, id="production"),
            pytest.param("SILENT", LoggerMode.SILENT, id="silent"),
        ],
    )
    def test_from_string(self, value: str, expected: LoggerMode) -> None:
        assert LoggerMode(value) == expected

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="is not a valid"):
            LoggerMode("INVALID")

    def test_is_str(self) -> None:
        assert isinstance(LoggerMode.DEV, str)
        assert LoggerMode.DEV == "DEV"


class TestConsoleConfig:
    def test_defaults(self) -> None:
        cfg = ConsoleConfig()
        assert cfg.show_time is True
        assert cfg.show_level is True
        assert cfg.show_logger_name is True
        assert cfg.show_icons is True
        assert cfg.separator == " | "

    def test_override(self) -> None:
        cfg = ConsoleConfig(show_time=False, separator=" :: ")
        assert cfg.show_time is False
        assert cfg.separator == " :: "

    def test_extra_forbid(self) -> None:
        with pytest.raises(ValidationError, match="nonexistent_field"):
            ConsoleConfig(nonexistent_field="x")  # type: ignore[call-arg]


class TestFileConfig:
    def test_defaults(self) -> None:
        cfg = FileConfig()
        assert cfg.enable is True
        assert cfg.compression == "zip"
        assert cfg.rotation == "100 MB"
        assert cfg.retention == "30 days"
        assert cfg.indent is None

    def test_custom_path(self) -> None:
        cfg = FileConfig(path=Path("logs/custom.log"))
        assert cfg.path == Path("logs/custom.log")


class TestLoggerConfig:
    def test_defaults(self) -> None:
        cfg = LoggerConfig()
        assert cfg.name == "app"
        assert cfg.level == "INFO"
        assert cfg.console_enabled is True
        assert isinstance(cfg.console, ConsoleConfig)
        assert isinstance(cfg.file, FileConfig)

    def test_level_override(self) -> None:
        cfg = LoggerConfig(level="DEBUG", console_level="WARNING")
        assert cfg.level == "DEBUG"
        assert cfg.console_level == "WARNING"

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        original = LoggerConfig(name="test", level="DEBUG")
        json_path = tmp_path / "config.json"

        original.save_to_json(json_path)
        loaded = LoggerConfig.load_from_json(json_path)

        assert loaded.name == original.name
        assert loaded.level == original.level

    def test_save_creates_valid_json(self, tmp_path: Path) -> None:
        cfg = LoggerConfig()
        json_path = tmp_path / "config.json"
        cfg.save_to_json(json_path)

        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["name"] == "app"
        assert data["level"] == "INFO"

    def test_load_nonexistent_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            LoggerConfig.load_from_json(tmp_path / "nope.json")

    def test_load_invalid_json_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{invalid", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            LoggerConfig.load_from_json(bad)

    def test_save_to_str_path(self, tmp_path: Path) -> None:
        cfg = LoggerConfig()
        path_str = str(tmp_path / "str_config.json")
        cfg.save_to_json(path_str)
        loaded = LoggerConfig.load_from_json(path_str)
        assert loaded.name == "app"


class TestGetLevelPriority:
    @pytest.mark.parametrize(
        ("level", "expected"),
        [
            pytest.param("DEBUG", 10, id="debug"),
            pytest.param("INFO", 20, id="info"),
            pytest.param("WARNING", 30, id="warning"),
            pytest.param("ERROR", 40, id="error"),
            pytest.param("CRITICAL", 50, id="critical"),
        ],
    )
    def test_known_levels(self, level: str, expected: int) -> None:
        assert get_level_priority(level) == expected  # type: ignore[arg-type]

    def test_unknown_returns_zero(self) -> None:
        assert get_level_priority("GARBAGE") == 0  # type: ignore[arg-type]


class TestPresetConfig:
    def test_valid_preset(self) -> None:
        preset = PresetConfig(
            name="standard",
            description="Standard logging",
            config=LoggerConfig(level="INFO"),
        )
        assert preset.name == "standard"


class TestGetModeConfig:
    @pytest.mark.parametrize(
        ("mode", "expected_name", "expected_console"),
        [
            pytest.param(LoggerMode.DEV, "dev", True, id="dev"),
            pytest.param(LoggerMode.PRODUCTION, "app", True, id="production"),
            pytest.param(LoggerMode.SILENT, "silent", False, id="silent"),
        ],
    )
    def test_mode_defaults(
        self,
        mode: LoggerMode,
        expected_name: str,
        expected_console: bool,
    ) -> None:
        cfg = get_mode_config(mode)
        assert cfg.name == expected_name
        assert cfg.console_enabled == expected_console

    def test_dev_mode_details(self) -> None:
        cfg = get_mode_config(LoggerMode.DEV)
        assert cfg.level == "DEBUG"
        assert cfg.console.show_location is True
        assert cfg.file.enable is True

    def test_production_mode_details(self) -> None:
        cfg = get_mode_config(LoggerMode.PRODUCTION)
        assert cfg.level == "INFO"
        assert cfg.console.show_location is False

    def test_silent_mode_details(self) -> None:
        cfg = get_mode_config(LoggerMode.SILENT)
        assert cfg.level == "ERROR"
        assert cfg.console_enabled is False
        assert cfg.file.enable is True

    def test_override_level(self) -> None:
        cfg = get_mode_config(LoggerMode.DEV, level="WARNING")
        assert cfg.level == "WARNING"

    def test_override_file_path(self) -> None:
        custom = Path("logs/custom.log.jsonl")
        cfg = get_mode_config(LoggerMode.PRODUCTION, file_path=custom)
        assert cfg.file.path == custom


class TestInterceptHandler:
    def test_is_logging_handler(self) -> None:
        handler = InterceptHandler()
        assert isinstance(handler, logging.Handler)

    def test_emit_forwards_record(self) -> None:
        messages: list[str] = []
        handler_id = logger.add(lambda msg: messages.append(msg.rstrip()), format="{message}")

        try:
            handler = InterceptHandler()
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="hello from stdlib",
                args=(),
                exc_info=None,
            )
            handler.emit(record)

            assert any("hello from stdlib" in m for m in messages)
        finally:
            logger.remove(handler_id)


class TestSetupMode:
    def test_setup_dev_mode(self) -> None:
        setup_mode(LoggerMode.DEV)
        shutdown_logger()

    def test_setup_production_mode(self) -> None:
        setup_mode(LoggerMode.PRODUCTION)
        shutdown_logger()

    def test_setup_silent_mode(self) -> None:
        setup_mode(LoggerMode.SILENT)
        shutdown_logger()

    def test_setup_with_overrides(self) -> None:
        setup_mode(LoggerMode.DEV, level="WARNING")
        shutdown_logger()

    def test_vendor_loggers_set_to_warning(self) -> None:
        setup_mode(LoggerMode.PRODUCTION)
        try:
            for name in ("torch", "httpx", "transformers"):
                assert logging.getLogger(name).level == logging.WARNING
        finally:
            shutdown_logger()

    def test_dev_mode_scrubs_message_extra_and_exception(self, tmp_path: Path) -> None:
        log_path = tmp_path / "application.log.jsonl"
        sensitive_value = "value-that-must-not-appear"
        setup_mode(
            LoggerMode.DEV,
            console_enabled=False,
            file_path=log_path,
        )
        try:
            logger.bind(
                api_key=sensitive_value,
                request={"token": sensitive_value},
            ).info("api_key={value}", value=sensitive_value)

            def _fail() -> None:
                msg = f"token={sensitive_value}"
                raise RuntimeError(msg)

            try:
                _fail()
            except RuntimeError:
                logger.exception("Provider request failed")
        finally:
            shutdown_logger()

        payload = log_path.read_text(encoding="utf-8")
        assert sensitive_value not in payload
        assert "***" in payload


class TestSetupModeFromEnv:
    def test_default_is_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LOGGER_MODE", raising=False)
        setup_mode_from_env()
        shutdown_logger()

    def test_env_dev_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOGGER_MODE", "DEV")
        setup_mode_from_env()
        shutdown_logger()

    def test_env_level_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOGGER_MODE", "PRODUCTION")
        monkeypatch.setenv("LOGGER_LEVEL", "debug")
        setup_mode_from_env()
        shutdown_logger()

    def test_env_disable_console(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOGGER_DISABLE_CONSOLE", "true")
        setup_mode_from_env()
        shutdown_logger()

    def test_env_disable_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOGGER_DISABLE_FILE", "true")
        setup_mode_from_env()
        shutdown_logger()

    def test_env_custom_file_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOGGER_FILE_PATH", "logs/custom.log.jsonl")
        setup_mode_from_env()
        shutdown_logger()

    def test_invalid_mode_falls_back_to_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOGGER_MODE", "GARBAGE")
        setup_mode_from_env()
        shutdown_logger()

    def test_user_overrides_take_priority(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOGGER_LEVEL", "DEBUG")
        with patch(_CORE_SETUP_MODE) as mock_setup:
            mock_setup.return_value = None
            setup_mode_from_env(level="ERROR")
            _, kwargs = mock_setup.call_args
            assert kwargs.get("level") == "ERROR"


class TestShutdownLogger:
    def test_shutdown_removes_handlers(self) -> None:
        setup_mode(LoggerMode.DEV)
        shutdown_logger()
        logger.info("This should be a no-op after shutdown")


class TestExports:
    def test_config_all(self) -> None:
        assert hasattr(_config_mod, "__all__")
        assert "LoggerConfig" in _config_mod.__all__
        assert "LoggerMode" in _config_mod.__all__

    def test_modes_all(self) -> None:
        assert hasattr(_modes_mod, "__all__")
        assert "get_mode_config" in _modes_mod.__all__

    def test_core_all(self) -> None:
        assert hasattr(_core_mod, "__all__")
        assert "setup_mode" in _core_mod.__all__
        assert "InterceptHandler" in _core_mod.__all__
