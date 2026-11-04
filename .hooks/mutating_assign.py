"""Reject an assignment whose value mutates the container its target indexes.

items[-2] += items.pop() reads the target, shortens the list, then writes to
an index that no longer exists. Any plain, augmented or annotated assignment
whose subscript target indexes the same object the value calls a mutating
method on depends on evaluation order this way; the fix is to mutate in a
statement of its own first. Attribute targets are not checked. A file that is
not UTF-8 or not valid Python is reported as unparsable. Paths come from argv.
"""

import ast
import sys
from pathlib import Path
from typing import Final

MUTATING_METHODS: Final[frozenset[str]] = frozenset(
    {
        "add",
        "append",
        "clear",
        "discard",
        "extend",
        "insert",
        "pop",
        "popitem",
        "remove",
        "reverse",
        "setdefault",
        "sort",
        "update",
    }
)
"""Methods of built-in containers that change the container they are called on."""


def _indexed_objects(target: ast.expr) -> set[str]:
    """Return the source text of every object a subscript in the target indexes."""
    return {
        ast.unparse(node.value)
        for node in ast.walk(target)
        if isinstance(node, ast.Subscript)
    }


def _mutated_objects(value: ast.expr) -> set[str]:
    """Return the source text of every object the value calls a mutating method on."""
    return {
        ast.unparse(node.func.value)
        for node in ast.walk(value)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in MUTATING_METHODS
    }


def _cannot_parse(path: Path, data: bytes, exc: SyntaxError | ValueError) -> str:
    """Return the report line for a file that is not UTF-8 or not valid Python."""
    if isinstance(exc, UnicodeDecodeError):
        line = data.count(b"\n", 0, exc.start) + 1
        return f"{path}:{line}: cannot parse: not UTF-8"
    if isinstance(exc, SyntaxError):
        return f"{path}:{exc.lineno or 1}: cannot parse: {exc.msg}"
    return f"{path}:1: cannot parse: {exc}"


def _check_file(path: Path) -> list[str]:
    """Return a message for every assignment that mutates what its target indexes."""
    data = path.read_bytes()
    try:
        tree = ast.parse(data.decode("utf-8-sig"), filename=str(path))
    except (SyntaxError, ValueError) as exc:
        return [_cannot_parse(path, data, exc)]
    problems: list[str] = []
    for node in ast.walk(tree):
        targets: list[ast.expr]
        value: ast.expr
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif (
            isinstance(node, (ast.AugAssign, ast.AnnAssign)) and node.value is not None
        ):
            targets, value = [node.target], node.value
        else:
            continue
        indexed = {name for target in targets for name in _indexed_objects(target)}
        for name in sorted(indexed & _mutated_objects(value)):
            problems.append(
                f"{path}:{node.lineno}: '{name}' is mutated "
                "by the value assigned into it"
            )
    return problems


def main() -> int:
    """Report clashing assignments in the argv Python files; return 1 if any."""
    problems: list[str] = []
    for arg in sys.argv[1:]:
        path = Path(arg)
        if path.suffix == ".py" and path.is_file():
            problems.extend(_check_file(path))

    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
