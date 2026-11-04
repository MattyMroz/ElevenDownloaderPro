"""Reject lines that carry U+FFFD or, with --ascii, any byte above 0x7F.

Lines are matched as bytes, so the file encoding does not matter. Paths come
from argv; prek passes them intact on Windows, unlike pygrep hooks.
"""

import argparse
import sys
from pathlib import Path
from typing import Final

REPLACEMENT_CHAR: Final[bytes] = b"\xef\xbf\xbd"
"""U+FFFD in UTF-8, the trace a broken decode leaves behind."""


def _problem(line: bytes, *, ascii_only: bool) -> str | None:
    """Return what is wrong with the line under the selected rule, or None."""
    if ascii_only:
        return None if line.isascii() else "non-ASCII byte"
    return (
        "U+FFFD replacement character (broken encoding)"
        if REPLACEMENT_CHAR in line
        else None
    )


def main() -> int:
    """Report every offending line of the argv files; return 1 if there is one."""
    parser = argparse.ArgumentParser(prog="text_guard")
    parser.add_argument(
        "--ascii", action="store_true", help="reject every non-ASCII byte"
    )
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args()
    paths: list[Path] = args.paths
    ascii_only: bool = args.ascii

    problems: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_bytes().splitlines(), start=1):
            problem = _problem(line, ascii_only=ascii_only)
            if problem is not None:
                problems.append(f"{path}:{number}: {problem}")

    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
