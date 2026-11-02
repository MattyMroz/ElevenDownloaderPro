"""Restriction of a private directory to the current account."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Final

from edp.errors import ErrorCode, ErrorContext, FatalError

__all__ = ["PrivateDirectoryError", "restrict_directory"]

# ── Constants ─────────────────────────────────────────────────────────────────

_ICACLS_TIMEOUT_S: Final[float] = 15.0
"""Deadline for the one ``icacls`` call restricting the directory."""

_POSIX_MODE: Final[int] = 0o700
"""Owner-only permissions applied outside Windows."""

_NO_ACCOUNT_MESSAGE: Final[str] = "The current Windows account is unknown, so the directory stays unrestricted"
"""Refusal stated when the session names no account or system root."""

_ICACLS_FAILED_MESSAGE: Final[str] = "icacls could not restrict the directory to the current account"
"""Refusal stated when the ACL utility fails, times out or cannot start."""


class PrivateDirectoryError(FatalError):
    """Raised when a private directory cannot be restricted to the current account."""


def is_windows() -> bool:
    """Return ``True`` when running on Windows."""
    return sys.platform == "win32"


def restrict_directory(root: Path) -> None:
    """Grant the current account sole, inherited full control of the existing *root*."""
    if not is_windows():
        root.chmod(_POSIX_MODE)
        return
    username: str = os.environ.get("USERNAME", "")
    domain: str = os.environ.get("USERDOMAIN", "")
    system_root: str = os.environ.get("SYSTEMROOT", "")
    if not username or not system_root:
        raise _refused(_NO_ACCOUNT_MESSAGE)
    account: str = f"{domain}\\{username}" if domain else username
    executable: Path = Path(system_root) / "System32" / "icacls.exe"
    try:
        result: subprocess.CompletedProcess[bytes] = subprocess.run(  # noqa: S603 - system ACL utility, own argv
            [str(executable), str(root), "/inheritance:r", "/grant:r", f"{account}:(OI)(CI)F"],
            capture_output=True,
            check=False,
            timeout=_ICACLS_TIMEOUT_S,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise _refused(_ICACLS_FAILED_MESSAGE) from error
    if result.returncode != 0:
        raise _refused(_ICACLS_FAILED_MESSAGE, exit_code=result.returncode)


def _refused(message: str, *, exit_code: int | None = None) -> PrivateDirectoryError:
    details: dict[str, int] = {} if exit_code is None else {"exit_code": exit_code}
    return PrivateDirectoryError(context=ErrorContext(code=ErrorCode.IO_ERROR, message=message, details=details))
