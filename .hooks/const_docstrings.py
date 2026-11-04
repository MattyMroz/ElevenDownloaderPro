"""Require a docstring under every module-level constant and type alias.

Ruff checks docstrings of modules, classes and functions only, so a bare
NAME: Final = ... slips through. A constant is a Final annotation or an
UPPER_CASE name; a type alias is a value with Literal[ or TypeAlias, or a
capitalised name bound to a union. Dunder names, test files and files under
tests/ or examples/ are skipped. Files may start with a BOM. A file that is
not UTF-8 or not valid Python is reported as unparsable. Paths come from argv.
"""

import ast
import sys
from pathlib import Path
from typing import Final

SKIP_DIRS: Final[frozenset[str]] = frozenset({"tests", "examples"})
"""Directory names whose files are exempt: tests carry no prose, examples teach."""


def _defined_name(node: ast.stmt) -> str | None:
    """Return the constant or type alias name a module-level statement defines."""
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id if "Final" in ast.unparse(node.annotation) else None
    if not (
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    ):
        return None
    name = node.targets[0].id
    value = ast.unparse(node.value)
    is_alias = (
        "Literal[" in value
        or "TypeAlias" in value
        or (" | " in value and name[0].isupper())
    )
    return name if is_alias or name.isupper() else None


def _is_docstring(node: ast.stmt | None) -> bool:
    """Return whether the statement is a bare string literal."""
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _cannot_parse(path: Path, data: bytes, exc: SyntaxError | ValueError) -> str:
    """Return the report line for a file that is not UTF-8 or not valid Python."""
    if isinstance(exc, UnicodeDecodeError):
        line = data.count(b"\n", 0, exc.start) + 1
        return f"{path}:{line}: cannot parse: not UTF-8"
    if isinstance(exc, SyntaxError):
        return f"{path}:{exc.lineno or 1}: cannot parse: {exc.msg}"
    return f"{path}:1: cannot parse: {exc}"


def _check_file(path: Path) -> list[str]:
    """Return a message for every constant and type alias without a docstring."""
    data = path.read_bytes()
    try:
        body = ast.parse(data.decode("utf-8-sig"), filename=str(path)).body
    except (SyntaxError, ValueError) as exc:
        return [_cannot_parse(path, data, exc)]
    problems: list[str] = []
    for index, node in enumerate(body):
        name = _defined_name(node)
        if name is None or name.startswith("__"):
            continue
        following = body[index + 1] if index + 1 < len(body) else None
        if not _is_docstring(following):
            problems.append(
                f"{path}:{node.lineno}: constant '{name}' needs a docstring below it"
            )
    return problems


def _is_exempt(path: Path) -> bool:
    """Return whether the path is a test or an example."""
    return bool(set(path.parts) & SKIP_DIRS) or path.name.startswith("test_")


def main() -> int:
    """Report undocumented constants in the argv Python files; return 1 if any."""
    problems: list[str] = []
    for arg in sys.argv[1:]:
        path = Path(arg)
        if path.suffix == ".py" and path.is_file() and not _is_exempt(path):
            problems.extend(_check_file(path))

    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
