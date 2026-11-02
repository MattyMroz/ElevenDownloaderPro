from __future__ import annotations

import time

import pytest
from loguru import logger

from ...timer import Timer
from ..timing import log_duration

_BOOM_MSG = "boom"


class TestTimerInit:
    def test_default_state(self) -> None:
        t = Timer()
        assert t.name == "Timer"
        assert not t.is_running
        assert t.duration_ns == 0
        assert t.start_date is None
        assert t.end_date is None

    def test_custom_name(self) -> None:
        t = Timer("custom")
        assert t.name == "custom"

    def test_auto_start(self) -> None:
        t = Timer("task", auto_start=True)
        assert t.is_running
        assert t.start_date is not None
        assert t.duration_ns > 0
        t.stop()


class TestTimerStartStop:
    def test_start_sets_running(self) -> None:
        t = Timer()
        t.start()
        assert t.is_running
        assert t.start_date is not None
        t.stop()

    def test_stop_returns_positive_ns(self) -> None:
        t = Timer(auto_start=True)
        time.sleep(0.01)
        ns = t.stop()
        assert ns > 0
        assert not t.is_running
        assert t.end_date is not None

    def test_stop_when_not_running_returns_zero(self) -> None:
        t = Timer()
        assert t.stop() == 0

    def test_duration_ns_while_running(self) -> None:
        t = Timer(auto_start=True)
        time.sleep(0.01)
        live_ns = t.duration_ns
        assert live_ns > 0
        assert t.is_running
        t.stop()

    def test_duration_ns_after_stop_is_frozen(self) -> None:
        t = Timer(auto_start=True)
        time.sleep(0.01)
        t.stop()
        d1 = t.duration_ns
        time.sleep(0.01)
        d2 = t.duration_ns
        assert d1 == d2


class TestTimerReset:
    def test_reset_clears_state(self) -> None:
        t = Timer(auto_start=True)
        time.sleep(0.01)
        t.stop()
        t.reset()
        assert not t.is_running
        assert t.duration_ns == 0
        assert t.start_date is None
        assert t.end_date is None


class TestTimerPrecision:
    def test_measures_at_least_10ms(self) -> None:
        t = Timer(auto_start=True)
        time.sleep(0.01)
        ns = t.stop()
        assert ns >= 5_000_000


class TestLogDuration:
    def test_yields_timer(self) -> None:
        with log_duration("test_op") as t:
            assert isinstance(t, Timer)
            assert t.is_running

    def test_timer_stopped_after_exit(self) -> None:
        with log_duration("test_op") as t:
            time.sleep(0.01)
        assert not t.is_running
        assert t.duration_ns > 0

    def test_logs_message(self, capfd: pytest.CaptureFixture[str]) -> None:
        sink_messages: list[str] = []
        handler_id = logger.add(sink_messages.append, format="{message}")
        try:
            with log_duration("my_operation"):
                time.sleep(0.01)
        finally:
            logger.remove(handler_id)

        assert len(sink_messages) == 1
        assert "my_operation completed in" in sink_messages[0]

    def test_custom_level(self) -> None:
        sink_messages: list[dict[str, str]] = []
        handler_id = logger.add(
            lambda m: sink_messages.append({"level": m.record["level"].name}),
            format="{message}",
            level="DEBUG",
        )
        try:
            with log_duration("op", level="DEBUG"):
                pass
        finally:
            logger.remove(handler_id)

        assert sink_messages[0]["level"] == "DEBUG"

    def test_timer_stopped_on_exception(self) -> None:
        with pytest.raises(ValueError, match="boom"), log_duration("failing") as timer_ref:
            raise ValueError(_BOOM_MSG)
        assert not timer_ref.is_running
        assert timer_ref.duration_ns > 0
