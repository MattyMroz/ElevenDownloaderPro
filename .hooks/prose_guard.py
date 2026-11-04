"""Reject comments and bare string literals in Python and JS/TS test files.

A test states its intent in its name. Tool directives stay allowed: # noqa,
# type:, # pragma, # pyright:, # ruff: noqa, # fmt: and a shebang on the
first line in Python; eslint, @ts, prettier, biome and coverage markers in
JS/TS. In Python every bare string statement counts, docstrings included, at
any depth. In JS/TS strings and regex literals are skipped. An apostrophe or
slash opens a literal only where an expression may start, judged by the last
character or keyword before it outside comments, so an apostrophe in JSX text
opens no string. A double quote always opens one, and a quoted string ends at
its line at the latest. A file that is not UTF-8 or not valid Python is
reported as unparsable.

A file is a test by convention, never by substring: conftest.py, test_*,
*_test, *.test.*, *.spec.*, or any file inside a test directory. Paths come
from argv.
"""

import ast
import io
import sys
import tokenize
from pathlib import Path
from typing import Final

PY_ALLOWED: Final[tuple[str, ...]] = (
    "# noqa",
    "# type:",
    "# pragma",
    "# pyright:",
    "# ruff: noqa",
    "# fmt:",
)
"""Python comment prefixes that are tool directives."""

SHEBANG: Final[str] = "#!"
"""Prefix of the interpreter line, allowed as the first line of a Python file."""

JS_ALLOWED: Final[tuple[str, ...]] = (
    "eslint",
    "@ts",
    "prettier",
    "biome",
    "c8",
    "istanbul",
    "v8",
)
"""Substrings that mark a JS/TS comment as a tool directive."""

PY_SUFFIXES: Final[frozenset[str]] = frozenset({".py"})
"""Extensions checked as Python."""

JS_SUFFIXES: Final[frozenset[str]] = frozenset(
    {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts"}
)
"""Extensions checked as JS/TS."""

TEST_DIRS: Final[frozenset[str]] = frozenset(
    {"test", "tests", "__tests__", "spec", "specs"}
)
"""Directory names whose files are tests whatever they are called."""

TEST_INFIXES: Final[tuple[str, ...]] = (".test.", ".spec.")
"""File name infixes of the *.test.* and *.spec.* conventions."""

TEMPLATE_QUOTE: Final[str] = "`"
"""Opener of a template literal, the only literal that spans lines."""

ALWAYS_OPEN: Final[frozenset[str]] = frozenset({'"', TEMPLATE_QUOTE})
"""Quotes that open a literal anywhere: after a tag, or paired in JSX text."""

APOSTROPHE: Final[str] = "'"
"""Quote that JSX text uses as an apostrophe, so its context decides."""

EXPRESSION_PRECEDERS: Final[frozenset[str]] = frozenset("(,=:[!&|?{};+-*%~^<>.")
"""Characters after which an apostrophe or slash opens a literal."""

EXPRESSION_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "return",
        "typeof",
        "case",
        "in",
        "of",
        "do",
        "else",
        "void",
        "delete",
        "new",
        "yield",
        "await",
        "throw",
        "from",
        "import",
        "extends",
        "as",
        "default",
        "satisfies",
        "module",
    }
)
"""Keywords after which an apostrophe or slash opens a literal."""


def _is_test_file(path: Path) -> bool:
    """Return whether the path is a test file by naming convention."""
    if {part.lower() for part in path.parts} & TEST_DIRS:
        return True
    name = path.name.lower()
    stem = name.split(".")[0]
    return (
        name == "conftest.py"
        or stem.startswith("test_")
        or stem.endswith("_test")
        or any(infix in name for infix in TEST_INFIXES)
    )


def _cannot_parse(path: Path, data: bytes, exc: SyntaxError | ValueError) -> str:
    """Return the report line for a file that is not UTF-8 or not valid Python."""
    if isinstance(exc, UnicodeDecodeError):
        line = data.count(b"\n", 0, exc.start) + 1
        return f"{path}:{line}: cannot parse: not UTF-8"
    if isinstance(exc, SyntaxError):
        return f"{path}:{exc.lineno or 1}: cannot parse: {exc.msg}"
    return f"{path}:1: cannot parse: {exc}"


def _is_python_directive(token: tokenize.TokenInfo) -> bool:
    """Return whether a Python comment token is a tool directive or the shebang."""
    comment = token.string.strip()
    shebang = token.start == (1, 0) and comment.startswith(SHEBANG)
    return shebang or comment.startswith(PY_ALLOWED)


def _check_python(path: Path) -> list[str]:
    """Return a message for every comment and bare string in a Python file."""
    data = path.read_bytes()
    try:
        src = data.decode("utf-8-sig")
        tree = ast.parse(src, filename=str(path))
    except (SyntaxError, ValueError) as exc:
        return [_cannot_parse(path, data, exc)]
    problems: list[str] = []
    for token in tokenize.generate_tokens(io.StringIO(src).readline):
        if token.type == tokenize.COMMENT and not _is_python_directive(token):
            problems.append(
                f"{path}:{token.start[0]}: comment not allowed in tests: "
                f"{token.string.strip()}"
            )
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            problems.append(f"{path}:{node.lineno}: docstring not allowed in tests")
    return problems


def _line_of(src: str, index: int) -> int:
    """Return the 1-based line number of the character at the index."""
    return src.count("\n", 0, index) + 1


def _is_directive(body: str) -> bool:
    """Return whether a JS/TS comment body is a tool directive."""
    return any(mark in body for mark in JS_ALLOWED)


def _skip_string(src: str, start: int) -> int:
    """Return the index just past the string that opens at start.

    A quoted string never spans lines, so one left open ends at its newline; a
    template literal runs to its closing backtick.
    """
    quote = src[start]
    i = start + 1
    while i < len(src):
        if src[i] == "\\":
            i += 2
        elif src[i] == quote:
            return i + 1
        elif src[i] == "\n" and quote != TEMPLATE_QUOTE:
            return i
        else:
            i += 1
    return len(src)


def _opens_literal(src: str, last: int) -> bool:
    """Return whether an apostrophe or slash after src[last] opens a literal.

    Args:
        src: The whole source.
        last: Index of the last character before it that is neither whitespace
            nor inside a comment, or -1 at the start of the file.

    Returns:
        True where an expression may start: at the start of the file, after a
        character of EXPRESSION_PRECEDERS or after a keyword of
        EXPRESSION_KEYWORDS.
    """
    if last < 0 or src[last] in EXPRESSION_PRECEDERS:
        return True
    j = last
    while j >= 0 and (src[j].isalnum() or src[j] in "_$"):
        j -= 1
    return src[j + 1 : last + 1] in EXPRESSION_KEYWORDS


def _skip_regex(src: str, start: int) -> int:
    """Return the index just past the regex literal at start.

    A regex that never closes on its line is a division after all, so the
    index after the slash comes back.
    """
    i = start + 1
    in_class = False
    while i < len(src):
        ch = src[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "\n":
            return start + 1
        if in_class:
            in_class = ch != "]"
        elif ch == "[":
            in_class = True
        elif ch == "/":
            return i + 1
        i += 1
    return start + 1


def _check_js(path: Path) -> list[str]:
    """Return a message for every comment in a JS/TS file outside its literals."""
    data = path.read_bytes()
    try:
        src = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        return [_cannot_parse(path, data, exc)]
    problems: list[str] = []
    last = -1
    i = 0
    while i < len(src):
        ch = src[i]
        pair = src[i : i + 2]
        if pair == "//":
            end = src.find("\n", i)
            end = len(src) if end == -1 else end
            body = src[i + 2 : end]
            if not _is_directive(body):
                problems.append(
                    f"{path}:{_line_of(src, i)}: comment not allowed in tests: "
                    f"//{body.strip()}"
                )
            i = end
            continue
        if pair == "/*":
            end = src.find("*/", i + 2)
            end = len(src) if end == -1 else end
            if not _is_directive(src[i + 2 : end]):
                problems.append(
                    f"{path}:{_line_of(src, i)}: block comment not allowed in tests"
                )
            i = end + 2
            continue
        if ch in ALWAYS_OPEN or (ch == APOSTROPHE and _opens_literal(src, last)):
            i = _skip_string(src, i)
        elif ch == "/" and _opens_literal(src, last):
            i = _skip_regex(src, i)
        else:
            i += 1
        if not ch.isspace():
            last = i - 1
    return problems


def main() -> int:
    """Report prose in the argv test files; return 1 if there is any."""
    problems: list[str] = []
    for arg in sys.argv[1:]:
        path = Path(arg)
        if not path.is_file() or not _is_test_file(path):
            continue
        if path.suffix in PY_SUFFIXES:
            problems.extend(_check_python(path))
        elif path.suffix in JS_SUFFIXES:
            problems.extend(_check_js(path))

    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
