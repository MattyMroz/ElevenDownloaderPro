from __future__ import annotations

import importlib


def _reload() -> object:
    module = importlib.import_module("..console", package=__package__)
    return importlib.reload(module)


def test_build_console_default_does_not_force_terminal(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    module = _reload()
    assert module.console._force_terminal is None  # type: ignore[attr-defined]


def test_build_console_force_color_enables_truecolor(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("FORCE_COLOR", "1")
    module = _reload()
    try:
        assert module.console._force_terminal is True  # type: ignore[attr-defined]
        assert module.console._color_system is not None  # type: ignore[attr-defined]
        assert module.console._color_system.name == "TRUECOLOR"  # type: ignore[attr-defined]
    finally:
        monkeypatch.delenv("FORCE_COLOR", raising=False)
        _reload()
