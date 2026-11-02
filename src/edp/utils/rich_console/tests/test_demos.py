from __future__ import annotations

from .. import (
    RICH_THEME,
    Colors,
    ProgressBarManager,
    __version__,
    console,
    format_bytes,
    format_duration,
    format_percentage,
    get_progress_color,
    get_status_icon,
)
from ..examples.demo_colors import demo_colors
from ..examples.demo_progress import run_all_demos as progress_demos
from ..examples.demo_theme import run_all_demos as theme_demos
from ..examples.demo_utilities import run_all_demos as utility_demos
from ..examples.run_demos import main


class TestDemoImports:
    def test_demo_colors_callable(self) -> None:
        assert callable(demo_colors)

    def test_demo_theme_callable(self) -> None:
        assert callable(theme_demos)

    def test_demo_utilities_callable(self) -> None:
        assert callable(utility_demos)

    def test_demo_progress_callable(self) -> None:
        assert callable(progress_demos)

    def test_run_demos_main_callable(self) -> None:
        assert callable(main)


class TestModulePublicAPI:
    def test_console_import(self) -> None:
        assert console is not None

    def test_progress_bar_manager_import(self) -> None:
        assert ProgressBarManager is not None

    def test_theme_import(self) -> None:
        assert RICH_THEME is not None
        assert Colors is not None

    def test_utilities_import(self) -> None:
        assert all(
            callable(f) for f in [format_bytes, format_duration, format_percentage, get_progress_color, get_status_icon]
        )

    def test_version(self) -> None:
        assert __version__ == "1.0.0"
