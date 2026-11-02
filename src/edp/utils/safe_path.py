"""Protect against path traversal attacks (Koharu K2 pattern).

Usage:
    >>> from <pkg>.utils.safe_path import safe_resolve
    >>> safe_resolve("subdir/file.txt", "/srv/data")
    PosixPath('/srv/data/subdir/file.txt')
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["PathTraversalError", "safe_resolve"]


class PathTraversalError(Exception):
    """Raised when a path escapes its allowed root directory."""


def safe_resolve(path: str | Path, root: str | Path) -> Path:
    """Resolve *path* ensuring it stays under *root*.

    Args:
        path: User-supplied path (may be relative or contain ``..``).
        root: Trusted root directory the result must live inside.

    Returns:
        Fully resolved ``Path`` under *root*.

    Raises:
        PathTraversalError: If the resolved path escapes *root*.
    """
    root_resolved = Path(root).resolve()
    full = (root_resolved / Path(path)).resolve()

    if not full.is_relative_to(root_resolved):
        msg = f"Path escapes root: {path!r}"
        raise PathTraversalError(msg)

    return full
