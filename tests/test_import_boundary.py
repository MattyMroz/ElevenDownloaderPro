from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_playwright_module_level_import_only_in_engine_browser() -> None:
    package_root = Path(__file__).parents[1] / "src" / "edp"
    importers: list[str] = []

    for path in package_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            module_names: tuple[str, ...] = ()
            if isinstance(node, ast.Import):
                module_names = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                module_names = (node.module,)
            if any(name.split(".")[0] == "playwright" for name in module_names):
                importers.append(path.relative_to(package_root).as_posix())

    assert sorted(set(importers)) == ["engine/browser.py"]


def test_package_import_does_not_load_playwright() -> None:
    script = (
        "import sys\n"
        "import edp.engine\n"
        "loaded = [name for name in sys.modules if name.startswith('playwright')]\n"
        "if loaded:\n"
        "    raise SystemExit(','.join(loaded))\n"
    )

    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script],
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
