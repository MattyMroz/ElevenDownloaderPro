from __future__ import annotations

import time
from datetime import datetime
from unittest.mock import patch

import pytest

from .. import (
    DisplayMode,
    ExecutionTimer,
    Timer,
    format_duration,
    timed,
)

_TIMER_CONSOLE = f"{ExecutionTimer.__module__}.console"


class TestTimer:
    def test_init_defaults(self) -> None:
        t = Timer("test")
        assert t.name == "test"
        assert not t.is_running
        assert t.duration_ns == 0
        assert t.start_date is None
        assert t.end_date is None

    def test_init_default_name(self) -> None:
        t = Timer()
        assert t.name == "Timer"

    def test_auto_start(self) -> None:
        t = Timer("t", auto_start=True)
        assert t.is_running
        assert t.start_date is not None
        assert t.duration_ns > 0

    def test_start_stop(self) -> None:
        t = Timer("t")
        t.start()
        assert t.is_running
        time.sleep(0.001)
        ns = t.stop()
        assert not t.is_running
        assert ns > 0
        assert t.end_date is not None

    def test_stop_when_not_running_returns_zero(self) -> None:
        t = Timer("t")
        assert t.stop() == 0

    def test_duration_while_running(self) -> None:
        t = Timer("t", auto_start=True)
        d1 = t.duration_ns
        time.sleep(0.001)
        d2 = t.duration_ns
        assert d2 > d1

    def test_duration_after_stop_is_frozen(self) -> None:
        t = Timer("t", auto_start=True)
        t.stop()
        d1 = t.duration_ns
        time.sleep(0.001)
        d2 = t.duration_ns
        assert d1 == d2

    def test_duration_unit_conversions(self) -> None:
        with patch(
            f"{Timer.__module__}.perf_counter_ns",
            side_effect=(1_000_000_000, 2_500_000_000),
        ):
            t: Timer = Timer("t", auto_start=True)
            t.stop()

        assert t.duration_ms == 1_500.0
        assert t.duration_s == 1.5

    def test_reset(self) -> None:
        t = Timer("t", auto_start=True)
        t.stop()
        t.reset()
        assert not t.is_running
        assert t.duration_ns == 0
        assert t.start_date is None
        assert t.end_date is None

    def test_restart_after_stop(self) -> None:
        t = Timer("t", auto_start=True)
        t.stop()
        t.start()
        assert t.is_running
        assert t.end_date is None
        time.sleep(0.001)
        t.stop()
        assert t.duration_ns > 0


class TestExecutionTimer:
    def test_context_manager_basic(self) -> None:
        with ExecutionTimer("test", display_mode="none") as et:
            time.sleep(0.001)
        assert et.get_duration_ns() > 0

    def test_timer_property(self) -> None:
        et = ExecutionTimer("test")
        assert isinstance(et.timer, Timer)
        assert et.timer.name == "test"

    def test_display_mode_none_no_console(self) -> None:
        with patch(_TIMER_CONSOLE) as mock_console:
            with ExecutionTimer("test", display_mode="none"):
                pass
            mock_console.print.assert_not_called()

    @pytest.mark.parametrize(
        "mode",
        [
            pytest.param("minimal", id="minimal"),
            pytest.param("standard", id="standard"),
            pytest.param("verbose", id="verbose"),
        ],
    )
    def test_display_mode_records_duration(self, mode: DisplayMode) -> None:
        with patch(_TIMER_CONSOLE):
            with ExecutionTimer("test", display_mode=mode) as et:
                pass
            assert et.get_duration_ns() > 0

    def test_exception_still_stops_timer(self) -> None:
        et = ExecutionTimer("test", display_mode="none")
        with pytest.raises(ValueError, match="boom"), et:
            raise ValueError("boom")
        assert et.get_duration_ns() > 0


class TestTimedDecorator:
    def test_basic(self) -> None:
        @timed(display_mode="none")
        def add(a: int, b: int) -> int:
            return a + b

        assert add(2, 3) == 5

    def test_preserves_function_name(self) -> None:
        @timed(display_mode="none")
        def my_func() -> None:
            pass

        assert my_func.__name__ == "my_func"

    def test_preserves_return_value(self) -> None:
        @timed(display_mode="none")
        def get_list() -> list[int]:
            return [1, 2, 3]

        assert get_list() == [1, 2, 3]

    def test_exception_propagates(self) -> None:
        @timed(display_mode="none")
        def fail() -> None:
            msg = "oops"
            raise RuntimeError(msg)

        with pytest.raises(RuntimeError, match="oops"):
            fail()

    def test_kwargs(self) -> None:
        @timed(display_mode="none")
        def greet(name: str, greeting: str = "Hello") -> str:
            return f"{greeting}, {name}!"

        assert greet("World", greeting="Hi") == "Hi, World!"

    def test_display_mode_prints(self) -> None:
        with patch(_TIMER_CONSOLE):

            @timed(display_mode="minimal")
            def noop() -> None:
                pass

            noop()


class TestFormatDuration:
    def test_none_mode_returns_none(self) -> None:
        assert format_duration(1000, mode="none") is None

    @pytest.mark.parametrize(
        ("ns", "mode", "expected"),
        [
            pytest.param(0, "minimal", "00:00:00:000:000:000", id="zero-minimal"),
            pytest.param(0, "minimal", "00:00:00:000:000:000", id="zero-duration"),
            pytest.param(500_000_000, "standard", "00:00:00:500:000:000", id="standard-no-dates"),
            pytest.param(1_000_000_000, "verbose", "00:00:01:000:000:000", id="verbose-no-dates"),
            pytest.param(
                3_661_001_002_003,
                "verbose",
                "01:01:01:001:002:003",
                id="verbose-1h1m1s",
            ),
            pytest.param(
                (2 * 3600 + 30 * 60 + 45) * 1_000_000_000 + 123_456_789,
                "minimal",
                "02:30:45:123:456:789",
                id="decomposition-accuracy",
            ),
        ],
    )
    def test_format_returns_expected(self, ns: int, mode: DisplayMode, expected: str) -> None:
        with patch(_TIMER_CONSOLE):
            result = format_duration(ns, mode=mode)
        assert result == expected

    def test_standard_with_dates(self) -> None:
        start = datetime(2026, 1, 1, 12, 0, 0)
        end = datetime(2026, 1, 1, 12, 0, 1)
        with patch(_TIMER_CONSOLE):
            result = format_duration(1_000_000_000, start, end, mode="standard")
        assert result == "00:00:01:000:000:000"
