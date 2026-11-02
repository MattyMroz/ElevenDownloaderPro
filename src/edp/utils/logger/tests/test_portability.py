from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def test_utils_import_and_retry_work_under_another_package_name(tmp_path: Path) -> None:
    source: Path = Path(__file__).resolve().parents[2]
    shutil.copytree(source, tmp_path / "portable_utils", ignore=shutil.ignore_patterns("__pycache__"))
    script: str = """
import asyncio
import sys
sys.path.insert(0, sys.argv[1])
from portable_utils import _portable
from portable_utils._retry import build_retry
from portable_utils.logger import get_logger
from portable_utils.rich_console import console
from portable_utils.timer import Timer

assert not any(name == sys.argv[2] or name.startswith(sys.argv[2] + '.') for name in sys.modules)
assert _portable.MIN_PYTHON == '3.14'
assert 'tenacity' in _portable.MODULE_DEPS['_retry']
attempts = 0
async def flaky():
    global attempts
    attempts += 1
    if attempts == 1:
        raise TimeoutError('temporary failure')
    return 'recovered'

retrying = build_retry(max_attempts=2, backoff='linear', base_s=0, retry_on=TimeoutError)
assert asyncio.run(retrying(flaky)) == 'recovered'
assert attempts == 2
assert get_logger('portable') is not None
timer = Timer('portable', auto_start=True)
assert timer.stop() >= 0
console.print('PORTABLE_UTILS_OK: retry recovered after 2 attempts')
"""

    result: subprocess.CompletedProcess[str] = subprocess.run(  # noqa: S603
        [sys.executable, "-I", "-c", script, str(tmp_path), __package__.split(".")[0]],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "PORTABLE_UTILS_OK: retry recovered after 2 attempts" in result.stdout
