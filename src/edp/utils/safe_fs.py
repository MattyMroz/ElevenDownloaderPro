"""Safe filesystem operations — retry-on-lock for Windows.

Windows antivirus scanners and filesystem indexers can hold file locks
briefly after creation/modification, causing ``PermissionError`` on
``shutil.rmtree`` / ``shutil.move``.  These wrappers add exponential
backoff retries to handle transient locks.

Usage:
    >>> from <pkg>.utils.safe_fs import safe_rmtree, safe_move
    >>> safe_rmtree("workspace/tmp")
    >>> safe_move("old/dir", "new/dir")
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Final

from .logger import get_logger

logger = get_logger(__name__)

__all__ = ["safe_move", "safe_rmtree"]

_MAX_RETRIES: Final[int] = 3
"""Maximum retry attempts for transient filesystem lock errors."""

_BASE_DELAY_S: Final[float] = 0.5
"""Initial backoff delay in seconds (doubles each retry: 0.5 → 1.0 → 2.0)."""


def safe_rmtree(path: str | Path, *, retries: int = _MAX_RETRIES) -> None:
    """Remove directory tree with retry on ``PermissionError``.

    Args:
        path: Directory to remove.
        retries: Max retry attempts (exponential backoff).

    Raises:
        PermissionError: If removal fails after all retries.
        FileNotFoundError: If *path* does not exist.
    """
    path = Path(path)
    for attempt in range(retries + 1):
        try:
            shutil.rmtree(path)
        except PermissionError:
            if attempt == retries:
                raise
            delay = _BASE_DELAY_S * (2**attempt)
            logger.debug(
                "PermissionError removing {name}, retrying in {delay:.1f}s ({attempt}/{retries})",
                name=path.name,
                delay=delay,
                attempt=attempt + 1,
                retries=retries,
            )
            time.sleep(delay)
        else:
            return


def safe_move(src: str | Path, dst: str | Path, *, retries: int = _MAX_RETRIES) -> Path:
    """Move file/directory with retry on ``PermissionError``.

    Args:
        src: Source path.
        dst: Destination path.
        retries: Max retry attempts (exponential backoff).

    Returns:
        Destination path.

    Raises:
        PermissionError: If move fails after all retries.
        FileNotFoundError: If *src* does not exist.
    """
    src, dst = Path(src), Path(dst)
    for attempt in range(retries + 1):
        try:
            shutil.move(str(src), str(dst))
        except PermissionError:
            if attempt == retries:
                raise
            delay = _BASE_DELAY_S * (2**attempt)
            logger.debug(
                "PermissionError moving {src} → {dst}, retrying in {delay:.1f}s ({attempt}/{retries})",
                src=src.name,
                dst=dst.name,
                delay=delay,
                attempt=attempt + 1,
                retries=retries,
            )
            time.sleep(delay)
        else:
            return dst
    # Unreachable — loop always returns or raises; guard satisfies type checker.
    msg = f"Failed to move {src} → {dst} after {retries} retries"
    raise PermissionError(msg)
