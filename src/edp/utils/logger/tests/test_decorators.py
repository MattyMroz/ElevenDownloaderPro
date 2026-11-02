from __future__ import annotations

import pytest

from ..decorators import (
    timed,
    timed_debug,
    timed_if,
    timed_in_dev,
    timed_when_debug,
)


class TestTimed:
    def test_returns_original_value(self) -> None:
        @timed()
        def add(a: int, b: int) -> int:
            return a + b

        assert add(2, 3) == 5

    def test_preserves_function_name(self) -> None:
        @timed()
        def my_func() -> None: ...

        assert my_func.__name__ == "my_func"

    def test_custom_operation_name(self) -> None:
        @timed("custom_op")
        def work() -> str:
            return "done"

        assert work() == "done"

    def test_custom_level(self) -> None:
        @timed(level="DEBUG")
        def work() -> int:
            return 42

        assert work() == 42

    def test_propagates_exception(self) -> None:
        @timed()
        def fail() -> None:
            msg = "boom"
            raise ValueError(msg)

        with pytest.raises(ValueError, match="boom"):
            fail()


class TestTimedIf:
    def test_condition_true_still_returns_value(self) -> None:
        @timed_if(True)
        def work() -> int:
            return 7

        assert work() == 7

    def test_condition_false_still_returns_value(self) -> None:
        @timed_if(False)
        def work() -> int:
            return 7

        assert work() == 7

    def test_callable_condition_true(self) -> None:
        @timed_if(lambda: True)
        def work() -> str:
            return "ok"

        assert work() == "ok"

    def test_callable_condition_false(self) -> None:
        @timed_if(lambda: False)
        def work() -> str:
            return "ok"

        assert work() == "ok"

    def test_preserves_function_name(self) -> None:
        @timed_if(True)
        def named() -> None: ...

        assert named.__name__ == "named"

    def test_propagates_exception_when_timed(self) -> None:
        @timed_if(True)
        def fail() -> None:
            raise RuntimeError

        with pytest.raises(RuntimeError):
            fail()

    def test_propagates_exception_when_not_timed(self) -> None:
        @timed_if(False)
        def fail() -> None:
            raise RuntimeError

        with pytest.raises(RuntimeError):
            fail()


class TestTimedDebug:
    def test_returns_value(self) -> None:
        @timed_debug()
        def compute() -> int:
            return 99

        assert compute() == 99

    def test_custom_name(self) -> None:
        @timed_debug("my_op")
        def compute() -> int:
            return 1

        assert compute() == 1


class TestTimedInDev:
    def test_returns_value_in_dev(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOGGER_MODE", "DEV")
        dec = timed_if(True)

        @dec
        def work() -> int:
            return 10

        assert work() == 10

    def test_returns_value_in_production(self) -> None:
        @timed_in_dev()
        def work() -> int:
            return 20

        assert work() == 20


class TestTimedWhenDebug:
    def test_returns_value(self) -> None:
        @timed_when_debug()
        def work() -> str:
            return "result"

        assert work() == "result"

    def test_callable_condition_evaluated_at_call_time(self, monkeypatch: pytest.MonkeyPatch) -> None:
        @timed_when_debug()
        def work() -> int:
            return 5

        assert work() == 5

        monkeypatch.setenv("DEBUG", "true")
        assert work() == 5
