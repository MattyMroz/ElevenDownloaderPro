from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Final

from edp.process_lock import ProcessLock

_CHILD_PROBE: Final[str] = """
import sys
from pathlib import Path

from edp.process_lock import ProcessLock

lock = ProcessLock(Path(sys.argv[1]))
print("acquired" if lock.acquire() else "busy")
lock.release()
"""

_CHILD_TIMEOUT: Final[int] = 30


def _child_verdict(path: Path) -> str:
    child: subprocess.CompletedProcess[str] = subprocess.run(  # noqa: S603 - fixed probe on this interpreter
        [sys.executable, "-c", _CHILD_PROBE, str(path)],
        capture_output=True,
        text=True,
        timeout=_CHILD_TIMEOUT,
        check=False,
    )
    assert child.returncode == 0, child.stderr
    return child.stdout.strip()


def test_acquire_creates_the_missing_lock_file_and_its_parent(tmp_path: Path) -> None:
    path: Path = tmp_path / "state" / "daemon.lock"
    lock: ProcessLock = ProcessLock(path)

    assert lock.acquire() is True
    lock.release()

    assert path.is_file()


def test_held_follows_acquire_and_release(tmp_path: Path) -> None:
    lock: ProcessLock = ProcessLock(tmp_path / "daemon.lock")

    assert lock.held is False
    assert lock.acquire() is True
    assert lock.held is True
    lock.release()
    assert lock.held is False


def test_a_second_acquire_while_held_reuses_the_same_handle(tmp_path: Path) -> None:
    lock: ProcessLock = ProcessLock(tmp_path / "daemon.lock")

    assert lock.acquire() is True
    assert lock.acquire() is True
    lock.release()

    assert lock.held is False


def test_releasing_twice_is_harmless(tmp_path: Path) -> None:
    lock: ProcessLock = ProcessLock(tmp_path / "daemon.lock")
    lock.acquire()

    lock.release()
    lock.release()

    assert lock.held is False


def test_release_keeps_the_lock_file_in_place(tmp_path: Path) -> None:
    path: Path = tmp_path / "daemon.lock"
    lock: ProcessLock = ProcessLock(path)
    lock.acquire()

    lock.release()

    assert path.is_file()


def test_another_process_sees_the_lock_busy_only_while_it_is_held(tmp_path: Path) -> None:
    path: Path = tmp_path / "daemon.lock"
    lock: ProcessLock = ProcessLock(path)
    assert lock.acquire() is True

    busy: str = _child_verdict(path)
    lock.release()
    free: str = _child_verdict(path)

    assert busy == "busy"
    assert free == "acquired"
