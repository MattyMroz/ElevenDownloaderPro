from __future__ import annotations

from ..stats import LoggerStats, get_logger_stats, increment_stat, reset_stats


class TestLoggerStats:
    def test_initial_state(self) -> None:
        stats = LoggerStats()
        assert stats.total_logged == 0
        assert stats.by_level == {}
        assert stats.by_logger == {}
        assert stats.last_log_time is None

    def test_increment_basic(self) -> None:
        stats = LoggerStats()
        stats.increment("INFO")
        assert stats.total_logged == 1
        assert stats.by_level == {"INFO": 1}
        assert stats.last_log_time is not None

    def test_increment_with_logger_name(self) -> None:
        stats = LoggerStats()
        stats.increment("ERROR", "mylogger")
        assert stats.by_logger == {"mylogger": 1}

    def test_increment_multiple_levels(self) -> None:
        stats = LoggerStats()
        stats.increment("INFO")
        stats.increment("INFO")
        stats.increment("ERROR")
        assert stats.total_logged == 3
        assert stats.by_level == {"INFO": 2, "ERROR": 1}

    def test_to_dict(self) -> None:
        stats = LoggerStats()
        stats.increment("INFO", "app")
        d = stats.to_dict()
        assert d["total_logged"] == 1
        assert d["by_level"] == {"INFO": 1}
        assert d["by_logger"] == {"app": 1}
        assert d["last_log_time"] is not None
        assert d["started_at"] is not None
        assert d["uptime_seconds"] >= 0

    def test_to_dict_no_logs(self) -> None:
        stats = LoggerStats()
        d = stats.to_dict()
        assert d["total_logged"] == 0
        assert d["last_log_time"] is None

    def test_reset(self) -> None:
        stats = LoggerStats()
        stats.increment("INFO", "app")
        stats.increment("ERROR", "db")
        stats.reset()
        assert stats.total_logged == 0
        assert stats.by_level == {}
        assert stats.by_logger == {}
        assert stats.last_log_time is None


class TestModuleFunctions:
    def test_get_logger_stats_singleton(self) -> None:
        s1 = get_logger_stats()
        s2 = get_logger_stats()
        assert s1 is s2

    def test_increment_and_reset(self) -> None:
        reset_stats()
        increment_stat("WARNING", "test_logger")
        stats = get_logger_stats()
        assert stats.total_logged >= 1
        reset_stats()
        assert stats.total_logged == 0
