"""Single-instance lock held by the operating system on one region of a file."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Final

from edp.utils.logger import get_logger

if TYPE_CHECKING:
    from pathlib import Path

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

__all__ = ["ProcessLock"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_REGION_BYTES: Final[int] = 1
"""Length of the file region the operating system lock covers."""

_LOCK_FILE_MODE: Final[int] = 0o644
"""Permission bits applied when the lock file is created."""


class ProcessLock:
    """Advisory lock on one file, owned by this process until it is released."""

    def __init__(self, path: Path) -> None:
        """Bind the lock to *path*, without creating or opening anything yet."""
        self._path: Path = path
        self._descriptor: int | None = None

    @property
    def held(self) -> bool:
        """Whether this instance currently owns the lock."""
        return self._descriptor is not None

    def acquire(self) -> bool:
        """Take the lock without blocking; ``False`` when another process holds it."""
        if self._descriptor is not None:
            return True
        self._path.parent.mkdir(parents=True, exist_ok=True)
        descriptor: int = os.open(self._path, os.O_RDWR | os.O_CREAT, _LOCK_FILE_MODE)
        if not _lock_region(descriptor):
            os.close(descriptor)
            return False
        self._descriptor = descriptor
        return True

    def release(self) -> None:
        """Release the lock and close the handle, leaving the lock file in place."""
        descriptor: int | None = self._descriptor
        if descriptor is None:
            return
        self._descriptor = None
        try:
            _unlock_region(descriptor)
        finally:
            os.close(descriptor)


def _lock_region(descriptor: int) -> bool:
    """Lock the first byte of *descriptor*, reporting whether the attempt won."""
    _ensure_region(descriptor)
    try:
        if sys.platform == "win32":
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, _REGION_BYTES)
        else:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock_region(descriptor: int) -> None:
    """Unlock the first byte of *descriptor*, tolerating a handle the OS already freed."""
    try:
        if sys.platform == "win32":
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, _REGION_BYTES)
        else:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    except OSError:
        logger.debug("Process lock was already released by the operating system")


def _ensure_region(descriptor: int) -> None:
    """Give the file its first byte, because Windows cannot lock past the end."""
    if os.lseek(descriptor, 0, os.SEEK_END) == 0:
        os.write(descriptor, b"\0")
    os.lseek(descriptor, 0, os.SEEK_SET)
