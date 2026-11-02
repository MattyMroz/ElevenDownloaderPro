from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from edp import private_dir
from edp.errors import ErrorCode
from edp.private_dir import PrivateDirectoryError, restrict_directory

pytestmark = pytest.mark.unit


class _Icacls:
    def __init__(self, *, returncode: int = 0, error: Exception | None = None) -> None:
        self.returncode: int = returncode
        self.error: Exception | None = error
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **_options: object) -> subprocess.CompletedProcess[bytes]:
        self.commands.append(command)
        if self.error is not None:
            raise self.error
        return subprocess.CompletedProcess(command, self.returncode, b"", b"")


def _windows(monkeypatch: pytest.MonkeyPatch, icacls: _Icacls, *, domain: str = "DESKTOP") -> None:
    monkeypatch.setattr(private_dir, "is_windows", lambda: True)
    monkeypatch.setattr(subprocess, "run", icacls)
    monkeypatch.setenv("USERNAME", "owner")
    monkeypatch.setenv("SYSTEMROOT", "C:\\Windows")
    if domain:
        monkeypatch.setenv("USERDOMAIN", domain)
    else:
        monkeypatch.delenv("USERDOMAIN", raising=False)


def test_restrict_directory_windows_grants_only_the_domain_account(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    icacls: _Icacls = _Icacls()
    _windows(monkeypatch, icacls)

    restrict_directory(tmp_path)

    assert icacls.commands == [
        [
            str(Path("C:\\Windows") / "System32" / "icacls.exe"),
            str(tmp_path),
            "/inheritance:r",
            "/grant:r",
            "DESKTOP\\owner:(OI)(CI)F",
        ]
    ]


def test_restrict_directory_windows_without_domain_grants_the_bare_account(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    icacls: _Icacls = _Icacls()
    _windows(monkeypatch, icacls, domain="")

    restrict_directory(tmp_path)

    assert icacls.commands[0][-1] == "owner:(OI)(CI)F"


@pytest.mark.parametrize("variable", ["USERNAME", "SYSTEMROOT"])
def test_restrict_directory_windows_without_account_refuses_before_icacls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, variable: str
) -> None:
    icacls: _Icacls = _Icacls()
    _windows(monkeypatch, icacls)
    monkeypatch.delenv(variable)

    with pytest.raises(PrivateDirectoryError):
        restrict_directory(tmp_path)

    assert icacls.commands == []


def test_restrict_directory_icacls_failure_raises_with_exit_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _windows(monkeypatch, _Icacls(returncode=5))

    with pytest.raises(PrivateDirectoryError) as caught:
        restrict_directory(tmp_path)

    assert caught.value.context.code is ErrorCode.IO_ERROR
    assert caught.value.context.details == {"exit_code": 5}


@pytest.mark.parametrize(
    "error", [FileNotFoundError("icacls"), subprocess.TimeoutExpired("icacls", 15.0)], ids=["missing", "timeout"]
)
def test_restrict_directory_icacls_that_cannot_finish_raises_typed_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, error: Exception
) -> None:
    _windows(monkeypatch, _Icacls(error=error))

    with pytest.raises(PrivateDirectoryError) as caught:
        restrict_directory(tmp_path)

    assert caught.value.__cause__ is error


def test_restrict_directory_outside_windows_sets_owner_only_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    modes: list[int] = []
    monkeypatch.setattr(private_dir, "is_windows", lambda: False)
    monkeypatch.setattr(Path, "chmod", lambda _self, mode: modes.append(mode))

    restrict_directory(tmp_path)

    assert modes == [0o700]
